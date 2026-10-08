#!/usr/bin/env python3
"""
ET EXPO Universal Email Invoice Downloader.

Phase 1 focus:
- Multi-account config.
- Universal IMAP dry-run and guarded download mode.
- Supplier classification.
- SQLite duplicate index.

Security:
- No passwords, app passwords, API keys, or OAuth tokens are stored in code.
- Secrets are read only from .env or the process environment.
- IMAP uses BODY.PEEK[] so messages should not be marked read.
- This script never deletes, moves, marks read, sends, or uploads email.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email
import email.header
import email.policy
import hashlib
import imaplib
import json
import logging
import os
import re
import sqlite3
import ssl
import sys
from email.message import EmailMessage, Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_KEYWORDS = [
    "invoice",
    "receipt",
    "bill",
    "statement",
    "payment",
    "order",
    "purchase",
    "tax invoice",
    "发票",
    "收据",
    "账单",
    "付款",
]

DEFAULT_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png", ".zip"]
WINDOWS_FORBIDDEN_CHARS = r'<>:"/\|?*'
MARKETPLACE_PLATFORMS = {"amazon", "bestbuy", "homedepot", "walmart"}
MARKETPLACE_ALL = "all"
MARKETPLACE_RULES = {
    "amazon": {
        "supplier": "Amazon",
        "from": ["amazon.com", "marketplace.amazon.com", "no-reply@amazon.com", "auto-confirm@amazon.com", "shipment-tracking@amazon.com"],
        "text": ["amazon", "your amazon order", "order confirmation", "invoice", "receipt", "order details", "shipped", "delivered"],
        "order_patterns": [r"\b\d{3}-\d{7}-\d{7}\b"],
    },
    "bestbuy": {
        "supplier": "BestBuy",
        "from": ["bestbuy.com", "bestbuy", "bestbuyinfo@emailinfo.bestbuy.com", "orders@bestbuy.com"],
        "text": ["best buy", "bestbuy", "receipt", "invoice", "order", "purchase", "ready for pickup", "shipped", "delivered"],
        "order_patterns": [r"\bBBY[0-9A-Z-]{6,}\b", r"\border\s*(?:number|#|no\.?)?\s*[:#]?\s*([A-Z0-9-]{6,})"],
    },
    "homedepot": {
        "supplier": "HomeDepot",
        "from": ["homedepot.com", "homedepot", "home depot"],
        "text": ["home depot", "homedepot", "receipt", "invoice", "order", "purchase", "pickup", "delivered"],
        "order_patterns": [r"\bW[0-9]{6,}\b", r"\border\s*(?:number|#|no\.?)?\s*[:#]?\s*([A-Z0-9-]{6,})"],
    },
    "walmart": {
        "supplier": "Walmart",
        "from": ["walmart.com", "walmart"],
        "text": ["walmart", "receipt", "invoice", "order", "purchase", "pickup", "delivered"],
        "order_patterns": [r"\b[0-9]{7,}-[0-9]{6,}\b", r"\border\s*(?:number|#|no\.?)?\s*[:#]?\s*([A-Z0-9-]{6,})"],
    },
}
AMOUNT_PATTERNS = [r"\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", r"\bUSD\s*([0-9][0-9,]*(?:\.[0-9]{2})?)"]
COMMON_MAIL_HOST_PARTS = {"mail", "email", "smtp", "imap", "mx", "m", "secure", "server"}
COMMON_DOMAIN_SUFFIXES = {
    "com",
    "net",
    "org",
    "co",
    "us",
    "cn",
    "edu",
    "gov",
    "io",
    "ai",
    "biz",
    "info",
    "mail",
}


@dataclasses.dataclass
class AttachmentPlan:
    account: str
    message_id: str
    email_date: dt.datetime
    sender: str
    subject: str
    supplier: str
    original_filename: str
    extension: str
    save_path: Path
    duplicate: bool
    hash_sha256: str = ""
    platform: str = ""
    order_number: str = ""
    amount: str = ""
    source_id: str = ""
    saved: bool = False
    error: str = ""


@dataclasses.dataclass
class BatchMonthResult:
    month: int
    planned: int = 0
    saved: int = 0
    duplicates: int = 0
    errors: int = 0
    status: str = "PENDING"
    supplier_summary: dict[str, int] = dataclasses.field(default_factory=dict)
    output_folder: str = ""
    message: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ET EXPO Universal Email Invoice Downloader")
    script_dir = Path(__file__).resolve().parent
    parser.add_argument("--config", default=str(script_dir / "config.yaml"), help="Path to config YAML")
    parser.add_argument("--env-file", default=str(script_dir / ".env"), help="Path to local .env file")
    parser.add_argument("--account", action="append", help="Account name to scan. Repeatable.")
    parser.add_argument("--all-accounts", action="store_true", help="Scan all enabled accounts in the config.")
    parser.add_argument("--year", type=int, help="Scan one year, for example 2026")
    parser.add_argument("--month", help="Scan one month, 1-12 with --year, or YYYY-MM such as 2026-06.")
    parser.add_argument("--months", help="Scan a month range such as 5-12. Use with --year.")
    parser.add_argument("--platform", choices=["amazon", "bestbuy", "homedepot", "walmart", "all"], help="Marketplace platform filter. Omit to keep original generic invoice rules.")
    parser.add_argument("--retry-failed", action="store_true", help="Retry marketplace failed tasks recorded in E:\\Invoice\\_logs\\marketplace_failed_tasks.jsonl.")
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD, inclusive")
    parser.add_argument("--max-messages", type=int, default=200, help="Safety cap per account")
    parser.add_argument("--dry-run", action="store_true", help="List matching attachments without saving them.")
    parser.add_argument("--run", action="store_true", help="Save matching attachments locally. Alias for confirmed run mode.")
    parser.add_argument("--batch", action="store_true", help="Run selected months sequentially and write batch state/summary.")
    parser.add_argument("--resume", action="store_true", help="Resume a batch by skipping completed months and continuing after failures.")
    parser.add_argument("--force-month", type=int, action="append", help="Re-run one month even if it is marked completed. Repeatable.")
    parser.add_argument("--execute", action="store_true", help="Actually save attachments")
    parser.add_argument(
        "--i-understand-download",
        action="store_true",
        help="Required with --execute to confirm local attachment download. --run also confirms local download.",
    )
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if os.environ.get("ET_EXPO_SKIP_ENV_FILE") == "1":
        return
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError("Config root must be a mapping.")
        return data
    except ModuleNotFoundError:
        return load_simple_yaml(path)


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Small YAML subset parser for this tool's example config."""
    root: dict[str, Any] = {}
    current_list_name: str | None = None
    current_item: dict[str, Any] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if indent == 0 and line.endswith(":"):
            key = line[:-1].strip()
            root[key] = []
            current_list_name = key
            current_item = None
            continue

        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            root[key.strip()] = value.strip()
            current_list_name = None
            current_item = None
            continue

        if current_list_name and line.startswith("- "):
            rest = line[2:].strip()
            if ":" in rest:
                key, value = rest.split(":", 1)
                current_item = {key.strip(): parse_scalar(value.strip())}
                root[current_list_name].append(current_item)
            else:
                current_item = None
                root[current_list_name].append(parse_scalar(rest))
            continue

        if current_item is not None and ":" in line:
            key, value = line.split(":", 1)
            current_item[key.strip()] = parse_scalar(value.strip())

    return root


def parse_scalar(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.isdigit():
        return int(value)
    return value


def init_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            account_name TEXT,
            message_id TEXT NOT NULL,
            attachment_filename TEXT NOT NULL,
            hash_sha256 TEXT,
            save_path TEXT NOT NULL,
            saved_path TEXT,
            email_date TEXT,
            supplier TEXT,
            subject TEXT,
            marketplace_platform TEXT,
            order_number TEXT,
            amount TEXT,
            source_id TEXT,
            downloaded_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(account, message_id, attachment_filename, hash_sha256)
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(attachments)").fetchall()}
    migrations = {
        "account_name": "ALTER TABLE attachments ADD COLUMN account_name TEXT",
        "saved_path": "ALTER TABLE attachments ADD COLUMN saved_path TEXT",
        "downloaded_at": "ALTER TABLE attachments ADD COLUMN downloaded_at TEXT",
        "marketplace_platform": "ALTER TABLE attachments ADD COLUMN marketplace_platform TEXT",
        "order_number": "ALTER TABLE attachments ADD COLUMN order_number TEXT",
        "amount": "ALTER TABLE attachments ADD COLUMN amount TEXT",
        "source_id": "ALTER TABLE attachments ADD COLUMN source_id TEXT",
    }
    for column_name, ddl in migrations.items():
        if column_name not in existing_columns:
            conn.execute(ddl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(account, message_id, attachment_filename)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_marketplace_order ON attachments(account, marketplace_platform, order_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments(account, hash_sha256)"
    )
    conn.commit()
    return conn


def is_duplicate(
    conn: sqlite3.Connection,
    account: str,
    message_id: str,
    filename: str,
    sha256: str = "",
    platform: str = "",
    order_number: str = "",
) -> bool:
    if platform and order_number:
        row = conn.execute(
            """
            SELECT 1 FROM attachments
            WHERE account=? AND marketplace_platform=? AND order_number=?
            LIMIT 1
            """,
            (account, platform, order_number),
        ).fetchone()
        if row is not None:
            return True
    if sha256:
        row = conn.execute(
            """
            SELECT 1 FROM attachments
            WHERE account=? AND hash_sha256=?
            LIMIT 1
            """,
            (account, sha256),
        ).fetchone()
        if row is not None:
            return True
    if sha256:
        row = conn.execute(
            """
            SELECT 1 FROM attachments
            WHERE account=? AND message_id=? AND attachment_filename=? AND hash_sha256=?
            LIMIT 1
            """,
            (account, message_id, filename, sha256),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT 1 FROM attachments
            WHERE account=? AND message_id=? AND attachment_filename=?
            LIMIT 1
            """,
            (account, message_id, filename),
        ).fetchone()
    return row is not None


def record_attachment(conn: sqlite3.Connection, plan: AttachmentPlan) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO attachments
        (account, account_name, message_id, attachment_filename, hash_sha256, save_path, saved_path, email_date, supplier, subject, marketplace_platform, order_number, amount, source_id, downloaded_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan.account,
            plan.account,
            plan.message_id,
            plan.original_filename,
            plan.hash_sha256,
            str(plan.save_path),
            str(plan.save_path),
            plan.email_date.isoformat(),
            plan.supplier,
            plan.subject,
            plan.platform,
            plan.order_number,
            plan.amount,
            plan.source_id,
            dt.datetime.now(dt.timezone.utc).isoformat(),
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded: list[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded).strip()


def clean_windows_name(value: str, fallback: str = "untitled", max_len: int = 120) -> str:
    cleaned = "".join("_" if ch in WINDOWS_FORBIDDEN_CHARS else ch for ch in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_len].rstrip(" .") or fallback


def supplier_from_domain(sender: str) -> str:
    addresses = getaddresses([sender])
    if not addresses:
        return ""
    _, addr = addresses[0]
    if "@" not in addr:
        return ""
    domain = addr.split("@", 1)[1].lower()
    parts = [p for p in domain.split(".") if p and p not in COMMON_MAIL_HOST_PARTS]
    core = [p for p in parts if p not in COMMON_DOMAIN_SUFFIXES]
    if not core:
        return ""
    return format_supplier(core[-1])


def format_supplier(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", " ", value).strip()
    if not value:
        return ""
    words = value.split()
    return "".join(word[:1].upper() + word[1:] for word in words)


def supplier_from_name(sender: str) -> str:
    addresses = getaddresses([sender])
    if not addresses:
        return ""
    display_name, _ = addresses[0]
    display_name = decode_mime(display_name)
    display_name = re.sub(r"\b(no.?reply|do.?not.?reply|billing|invoice|receipts?)\b", " ", display_name, flags=re.I)
    return format_supplier(display_name)


def supplier_from_text(*values: str) -> str:
    combined = " ".join(v for v in values if v)
    patterns = [
        r"\b(Amazon|Home\s*Depot|Uline|Costco|Walmart|FedEx|UPS|DHL|Adobe|Google|Microsoft|Apple|Zoom)\b",
        r"([\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9 &.-]{1,40})\s+(invoice|receipt|bill|statement)",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.I)
        if match:
            return format_supplier(match.group(1))
    return ""


def identify_supplier(sender: str, subject: str, filename: str) -> str:
    return (
        supplier_from_domain(sender)
        or supplier_from_name(sender)
        or supplier_from_text(subject)
        or supplier_from_text(filename)
        or "Unknown_Supplier"
    )


def parse_message_date(message: Message) -> dt.datetime:
    raw_date = message.get("Date")
    if raw_date:
        try:
            parsed = parsedate_to_datetime(raw_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except (TypeError, ValueError):
            pass
    return dt.datetime.now(dt.timezone.utc)


def build_date_range(args: argparse.Namespace) -> tuple[dt.date | None, dt.date | None]:
    if args.start_date or args.end_date:
        start = dt.date.fromisoformat(args.start_date) if args.start_date else None
        end = dt.date.fromisoformat(args.end_date) if args.end_date else None
        return start, end
    if args.month and re.fullmatch(r"\d{4}-\d{2}", str(args.month)):
        year, month = parse_year_month(str(args.month))
        return dt.date(year, month, 1), month_end(year, month)
    if args.year and args.months:
        months = parse_months(args.months)
        start = dt.date(args.year, months[0], 1)
        end = month_end(args.year, months[-1])
        return start, end
    if args.year and args.month:
        month = parse_month_value(args.month)
        start = dt.date(args.year, month, 1)
        return start, month_end(args.year, month)
    if args.year:
        return dt.date(args.year, 1, 1), dt.date(args.year, 12, 31)
    return None, None


def month_end(year: int, month: int) -> dt.date:
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def parse_months(value: str) -> list[int]:
    value = value.strip()
    if not value:
        raise ValueError("--months cannot be empty")
    if "-" in value:
        start_text, end_text = value.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        if start > end:
            raise ValueError("--months start must be <= end")
        months = list(range(start, end + 1))
    else:
        months = [int(part.strip()) for part in value.split(",") if part.strip()]
    invalid = [month for month in months if month < 1 or month > 12]
    if invalid:
        raise ValueError(f"Invalid month values: {invalid}")
    return months


def parse_month_value(value: str | int) -> int:
    month = int(value)
    if month < 1 or month > 12:
        raise ValueError("--month must be between 1 and 12, or use YYYY-MM")
    return month


def parse_year_month(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", value.strip())
    if not match:
        raise ValueError("--month must be 1-12 with --year, or YYYY-MM")
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        raise ValueError("--month YYYY-MM has invalid month")
    return year, month


def selected_months(args: argparse.Namespace) -> list[int]:
    if args.months:
        return parse_months(args.months)
    if args.month:
        if re.fullmatch(r"\d{4}-\d{2}", str(args.month)):
            return [parse_year_month(str(args.month))[1]]
        return [parse_month_value(args.month)]
    return list(range(1, 13))


def imap_date(value: dt.date) -> str:
    return value.strftime("%d-%b-%Y")


def build_imap_search(start: dt.date | None, end: dt.date | None) -> list[str]:
    criteria = ["ALL"]
    if start:
        criteria.extend(["SINCE", imap_date(start)])
    if end:
        criteria.extend(["BEFORE", imap_date(end + dt.timedelta(days=1))])
    return criteria


def text_parts_from_message(message: Message, limit: int = 12000) -> str:
    parts: list[str] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except Exception:  # noqa: BLE001
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            else:
                content = str(payload or "")
        parts.append(str(content))
        if sum(len(item) for item in parts) >= limit:
            break
    return " ".join(parts)[:limit]


def message_search_text(message: Message) -> str:
    sender = decode_mime(message.get("From"))
    subject = decode_mime(message.get("Subject"))
    filenames = " ".join(decode_mime(part.get_filename()) for part in message.walk() if part.get_filename())
    body = text_parts_from_message(message)
    return f"{sender} {subject} {filenames} {body}"


def contains_keyword(message: Message, keywords: Iterable[str]) -> bool:
    haystack = message_search_text(message).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def normalize_platform(value: str | None) -> str:
    return (value or "").strip().lower()


def active_platforms(platform: str | None) -> list[str]:
    platform = normalize_platform(platform)
    if not platform:
        return []
    if platform == MARKETPLACE_ALL:
        return sorted(MARKETPLACE_PLATFORMS)
    if platform not in MARKETPLACE_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    return [platform]


def detect_marketplace(message: Message, platform: str | None) -> str:
    platforms = active_platforms(platform)
    if not platforms:
        return ""
    sender = decode_mime(message.get("From")).lower()
    haystack = message_search_text(message).lower()
    for candidate in platforms:
        rule = MARKETPLACE_RULES[candidate]
        from_hit = any(token.lower() in sender for token in rule["from"])
        text_hit = any(token.lower() in haystack for token in rule["text"])
        if from_hit or text_hit:
            return candidate
    return ""


def extract_order_number(platform: str, text: str) -> str:
    if not platform:
        return ""
    for pattern in MARKETPLACE_RULES.get(platform, {}).get("order_patterns", []):
        match = re.search(pattern, text, flags=re.I)
        if match:
            return (match.group(1) if match.groups() else match.group(0)).strip(" .:#")
    return ""


def extract_amount(text: str) -> str:
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).replace(",", "")
    return ""


def short_source_id(message_id: str) -> str:
    return hashlib.sha1(message_id.encode("utf-8", errors="ignore")).hexdigest()[:10]


def marketplace_supplier(platform: str) -> str:
    return str(MARKETPLACE_RULES.get(platform, {}).get("supplier") or "")


def iter_attachments(message: Message, allowed_extensions: set[str]) -> Iterable[tuple[str, bytes]]:
    for part in message.walk():
        filename = decode_mime(part.get_filename())
        if not filename:
            continue
        ext = Path(filename).suffix.lower()
        if ext not in allowed_extensions:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        yield filename, payload


def build_save_path(
    output_dir: Path,
    account_name: str,
    email_date: dt.datetime,
    supplier: str,
    subject: str,
    original_filename: str,
    platform: str = "",
    order_number: str = "",
    amount: str = "",
    source_id: str = "",
) -> Path:
    yyyy = f"{email_date.year:04d}"
    mm = f"{email_date.month:02d}"
    date_part = email_date.strftime("%Y-%m-%d")
    account_part = clean_windows_name(account_name, "Unknown_Account", max_len=80)
    if platform:
        supplier = marketplace_supplier(platform) or supplier
    supplier_part = clean_windows_name(supplier, "Unknown_Supplier", max_len=80)
    if platform:
        order_part = f"Order_{clean_windows_name(order_number, 'missing_order_number', max_len=80)}"
        amount_part = clean_windows_name(amount, "missing_amount", max_len=40)
        source_part = clean_windows_name(source_id, "source", max_len=40)
        ext = Path(original_filename).suffix or ".pdf"
        final_name = clean_windows_name(f"{supplier_part}_{date_part}_{order_part}_{amount_part}_{source_part}", "attachment", 210) + ext
    else:
        subject_part = clean_windows_name(subject, "No_Subject", max_len=100)
        filename_part = clean_windows_name(original_filename, "attachment", max_len=120)
        final_name = clean_windows_name(f"{date_part}_{supplier_part}_{subject_part}_{filename_part}", "attachment", 220)
    return output_dir / account_part / yyyy / mm / supplier_part / final_name


def ensure_unique_path(path: Path, reserved_paths: set[str] | None = None) -> Path:
    reserved_paths = reserved_paths if reserved_paths is not None else set()
    reserved_key = str(path).casefold()
    if not path.exists() and reserved_key not in reserved_paths:
        reserved_paths.add(reserved_key)
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i:03d}{suffix}"
        candidate_key = str(candidate).casefold()
        if not candidate.exists() and candidate_key not in reserved_paths:
            reserved_paths.add(candidate_key)
            return candidate
    raise RuntimeError(f"Unable to find unique path for {path}")


def scan_imap_account(
    account: dict[str, Any],
    config: dict[str, Any],
    conn: sqlite3.Connection,
    start: dt.date | None,
    end: dt.date | None,
    execute: bool,
    max_messages: int,
    platform: str | None = None,
) -> list[AttachmentPlan]:
    account_name = str(account["name"])
    host = str(account["host"])
    port = int(account.get("port", 993))
    username_env = str(account["username_env"])
    password_env = str(account["password_env"])
    username = os.environ.get(username_env)
    password = os.environ.get(password_env)

    if not username or not password:
        raise RuntimeError(f"Missing environment variables for account {account_name}: {username_env}/{password_env}")

    output_dir = Path(os.environ.get("INVOICE_OUTPUT_DIR") or config.get("output_dir") or r"E:\Invoice")
    keywords = config.get("keywords") or DEFAULT_KEYWORDS
    allowed_extensions = {str(ext).lower() for ext in (config.get("allowed_extensions") or DEFAULT_EXTENSIONS)}

    plans: list[AttachmentPlan] = []
    reserved_save_paths: set[str] = set()
    logging.info("Scanning IMAP account %s at %s:%s", account_name, host, port)

    context = ssl.create_default_context()
    with imaplib.IMAP4_SSL(host, port, ssl_context=context) as mailbox:
        mailbox.login(username, password)
        mailbox.select("INBOX", readonly=True)
        status, data = mailbox.search(None, *build_imap_search(start, end))
        if status != "OK":
            raise RuntimeError(f"IMAP search failed for account {account_name}: {status}")

        message_nums = data[0].split()
        if max_messages:
            message_nums = message_nums[-max_messages:]

        for num in message_nums:
            status, fetch_data = mailbox.fetch(num, "(BODY.PEEK[])")
            if status != "OK" or not fetch_data:
                logging.warning("Failed to fetch message %s in account %s", num.decode(errors="ignore"), account_name)
                continue
            raw_message = next((item[1] for item in fetch_data if isinstance(item, tuple)), None)
            if not raw_message:
                continue
            message = email.message_from_bytes(raw_message, policy=email.policy.default)
            if not contains_keyword(message, keywords):
                continue
            detected_platform = detect_marketplace(message, platform)
            if platform and not detected_platform:
                continue

            email_date = parse_message_date(message)
            subject = decode_mime(message.get("Subject")) or "No Subject"
            sender = decode_mime(message.get("From"))
            message_id = decode_mime(message.get("Message-ID")) or f"{account_name}-{num.decode(errors='ignore')}"
            message_text = message_search_text(message)
            order_number = extract_order_number(detected_platform, message_text) if detected_platform else ""
            amount = extract_amount(message_text) if detected_platform else ""
            source_id = short_source_id(message_id)
            supplier_override = marketplace_supplier(detected_platform) if detected_platform else ""
            if detected_platform and not order_number:
                logging.info("missing_order_number platform=%s account=%s message_id=%s subject=%s", detected_platform, account_name, source_id, subject)
            if detected_platform and not amount:
                logging.info("missing_amount platform=%s account=%s message_id=%s subject=%s", detected_platform, account_name, source_id, subject)

            for original_filename, payload in iter_attachments(message, allowed_extensions):
                supplier = supplier_override or identify_supplier(sender, subject, original_filename)
                save_path = build_save_path(
                    output_dir,
                    account_name,
                    email_date,
                    supplier,
                    subject,
                    original_filename,
                    platform=detected_platform,
                    order_number=order_number,
                    amount=amount,
                    source_id=source_id,
                )
                save_path = ensure_unique_path(save_path, reserved_save_paths)
                sha256 = hashlib.sha256(payload).hexdigest() if payload else ""
                duplicate = is_duplicate(conn, account_name, message_id, original_filename, sha256, detected_platform, order_number)
                plan = AttachmentPlan(
                    account=account_name,
                    message_id=message_id,
                    email_date=email_date,
                    sender=sender,
                    subject=subject,
                    supplier=supplier,
                    original_filename=original_filename,
                    extension=Path(original_filename).suffix.lower(),
                    save_path=save_path,
                    duplicate=duplicate,
                    hash_sha256=sha256,
                    platform=detected_platform,
                    order_number=order_number,
                    amount=amount,
                    source_id=source_id,
                )

                if execute and not duplicate:
                    try:
                        final_path = save_path
                        final_path.parent.mkdir(parents=True, exist_ok=True)
                        if final_path.exists():
                            final_path = ensure_unique_path(final_path, reserved_save_paths)
                        final_path.write_bytes(payload)
                        plan.save_path = final_path
                        plan.saved = True
                        record_attachment(conn, plan)
                    except Exception as exc:  # noqa: BLE001
                        plan.error = str(exc)
                        logging.exception("Failed to save attachment for account %s", account_name)

                plans.append(plan)

        mailbox.close()

    return plans


def write_report(report_file: Path, plans: list[AttachmentPlan], execute: bool, skipped: list[str]) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = "EXECUTE" if execute else "DRY-RUN"
    lines = [
        "# ET EXPO Invoice Download Report",
        "",
        f"- Generated: {now}",
        f"- Mode: {mode}",
        f"- Planned attachments: {len(plans)}",
        f"- Saved attachments: {sum(1 for p in plans if p.saved)}",
        f"- Duplicates: {sum(1 for p in plans if p.duplicate)}",
        f"- Errors: {sum(1 for p in plans if p.error)}",
        "",
    ]

    if skipped:
        lines.extend(["## Skipped Accounts", ""])
        lines.extend(f"- {item}" for item in skipped)
        lines.append("")

    lines.extend(["## Attachments", ""])
    if not plans:
        lines.append("No matching attachments found.")
    else:
        lines.append("| Account | Platform | Date | Supplier | Order | Amount | Subject | Attachment | Status | Save Path |")
        lines.append("|---|---|---:|---|---|---:|---|---|---|---|")
        for plan in plans:
            if plan.error:
                status = f"ERROR: {clean_windows_name(plan.error, 'error', 80)}"
            elif plan.duplicate:
                status = "DUPLICATE"
            elif plan.saved:
                status = "SAVED"
            else:
                status = "WOULD_DOWNLOAD"
            lines.append(
                "| {account} | {platform} | {date} | {supplier} | {order} | {amount} | {subject} | {file} | {status} | {path} |".format(
                    account=plan.account,
                    platform=plan.platform or "-",
                    date=plan.email_date.strftime("%Y-%m-%d"),
                    supplier=plan.supplier,
                    order=plan.order_number or "-",
                    amount=plan.amount or "-",
                    subject=clean_windows_name(plan.subject, "No_Subject", 80),
                    file=clean_windows_name(plan.original_filename, "attachment", 80),
                    status=status,
                    path=str(plan.save_path),
                )
            )
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def scan_config_accounts(
    config: dict[str, Any],
    conn: sqlite3.Connection,
    selected_accounts: set[str],
    start: dt.date | None,
    end: dt.date | None,
    execute: bool,
    max_messages: int,
    platform: str | None = None,
    output_dir: Path | None = None,
) -> tuple[list[AttachmentPlan], list[str]]:
    all_plans: list[AttachmentPlan] = []
    skipped: list[str] = []

    for account in config.get("accounts") or []:
        name = str(account.get("name", "unnamed"))
        if selected_accounts and name not in selected_accounts:
            continue
        if account.get("enabled") is False:
            skipped.append(f"{name}: disabled in config")
            continue
        provider = str(account.get("provider", "")).lower()
        try:
            if provider == "imap":
                all_plans.extend(
                    scan_imap_account(
                        account=account,
                        config=config,
                        conn=conn,
                        start=start,
                        end=end,
                        execute=execute,
                        max_messages=max_messages,
                        platform=platform,
                    )
                )
            elif provider in {"gmail_oauth", "microsoft_graph"}:
                skipped.append(f"{name}: provider {provider} is documented for future phase; Phase 1 scans IMAP only")
            else:
                skipped.append(f"{name}: unsupported provider {provider}")
        except Exception as exc:  # noqa: BLE001
            logging.exception("Account scan failed: %s", name)
            skipped.append(f"{name}: ERROR {exc}")
            if output_dir is not None:
                write_failed_task(
                    output_dir=output_dir,
                    platform=platform or "",
                    account=name,
                    start=start,
                    end=end,
                    message_id="",
                    subject="",
                    reason=f"{exc.__class__.__name__}: {exc}",
                )

    return all_plans, skipped


def failed_tasks_path(output_dir: Path) -> Path:
    return output_dir / "_logs" / "marketplace_failed_tasks.jsonl"


def write_failed_task(
    output_dir: Path,
    platform: str,
    account: str,
    start: dt.date | None,
    end: dt.date | None,
    message_id: str,
    subject: str,
    reason: str,
) -> None:
    output_dir.joinpath("_logs").mkdir(parents=True, exist_ok=True)
    record = {
        "platform": normalize_platform(platform) or "",
        "account": account,
        "year": start.year if start else None,
        "month": start.month if start else None,
        "date_start": start.isoformat() if start else "",
        "date_end": end.isoformat() if end else "",
        "message_id": message_id,
        "subject": subject,
        "reason": reason,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with failed_tasks_path(output_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def count_errors(plans: list[AttachmentPlan], skipped: list[str]) -> int:
    return sum(1 for plan in plans if plan.error) + sum(1 for item in skipped if "ERROR" in item.upper())


def supplier_summary(plans: list[AttachmentPlan]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for plan in plans:
        summary[plan.supplier] = summary.get(plan.supplier, 0) + 1
    return dict(sorted(summary.items()))


def month_output_folder(output_dir: Path, account_name: str, year: int, month: int) -> Path:
    return output_dir / clean_windows_name(account_name, "Unknown_Account", max_len=80) / f"{year:04d}" / f"{month:02d}"


def validate_plan_paths(plans: list[AttachmentPlan], output_dir: Path, account_name: str, year: int, month: int) -> tuple[bool, str]:
    expected_prefix = month_output_folder(output_dir, account_name, year, month)
    expected_prefix_text = str(expected_prefix).casefold()
    for plan in plans:
        if not str(plan.save_path).casefold().startswith(expected_prefix_text):
            return False, f"Invalid save path for {plan.original_filename}: {plan.save_path}"
    return True, ""


def batch_state_path(output_dir: Path, account_name: str, year: int) -> Path:
    return output_dir / "_index" / f"{clean_windows_name(account_name)}_{year}_batch_state.json"


def batch_summary_path(output_dir: Path, account_name: str, year: int) -> Path:
    return output_dir / f"{clean_windows_name(account_name)}_{year}_batch_summary.md"


def batch_log_path(output_dir: Path, account_name: str, year: int) -> Path:
    return output_dir / "_logs" / f"{clean_windows_name(account_name)}_{year}_batch.log"


def load_batch_state(path: Path, account_name: str, year: int) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}
    state.setdefault("account_name", account_name)
    state.setdefault("year", year)
    state.setdefault("completed_months", [])
    state.setdefault("failed_months", [])
    state.setdefault("last_completed_month", None)
    state.setdefault("last_error", "")
    state.setdefault("started_at", now)
    state.setdefault("updated_at", now)
    return state


def save_batch_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_batch_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} {message}\n")
    logging.info(message)


def write_batch_summary(path: Path, account_name: str, year: int, results: list[BatchMonthResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_planned = sum(item.planned for item in results)
    total_saved = sum(item.saved for item in results)
    total_duplicates = sum(item.duplicates for item in results)
    total_errors = sum(item.errors for item in results)
    completed = [item.month for item in results if item.status in {"COMPLETED_DRY_RUN", "COMPLETED_DOWNLOAD"}]
    failed = [item.month for item in results if item.status.startswith("FAILED")]
    skipped = [item.month for item in results if item.status.startswith("SKIPPED")]

    lines = [
        f"# {account_name} {year} Batch Summary",
        "",
        "| Month | Dry-run planned attachments | Saved attachments | Duplicates | Errors | Status | Supplier summary | Output folder |",
        "|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for result in results:
        suppliers = ", ".join(f"{name}: {count}" for name, count in result.supplier_summary.items()) or "-"
        lines.append(
            f"| {result.month:02d} | {result.planned} | {result.saved} | {result.duplicates} | "
            f"{result.errors} | {result.status} | {suppliers} | {result.output_folder} |"
        )
    lines.extend(
        [
            "",
            "## Totals",
            "",
            f"- Total planned: {total_planned}",
            f"- Total saved: {total_saved}",
            f"- Total duplicates: {total_duplicates}",
            f"- Total errors: {total_errors}",
            f"- Completed months: {', '.join(f'{m:02d}' for m in completed) or '-'}",
            f"- Failed months: {', '.join(f'{m:02d}' for m in failed) or '-'}",
            f"- Skipped months: {', '.join(f'{m:02d}' for m in skipped) or '-'}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_batch_mode(args: argparse.Namespace, config: dict[str, Any], conn: sqlite3.Connection, output_dir: Path) -> int:
    if not args.year and args.month and re.fullmatch(r"\d{4}-\d{2}", str(args.month)):
        year_from_month, month_from_month = parse_year_month(str(args.month))
        args.year = year_from_month
        args.month = str(month_from_month)
    if not args.year:
        print("--batch requires --year", file=sys.stderr)
        return 2
    if args.all_accounts or not args.account or len(args.account) != 1:
        print("--batch requires exactly one --account and does not support --all-accounts.", file=sys.stderr)
        return 2
    if args.start_date or args.end_date:
        print("--batch uses --year plus --month or --months, not --start-date/--end-date.", file=sys.stderr)
        return 2

    account_name = args.account[0]
    try:
        months = selected_months(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    forced_months = set(args.force_month or [])
    invalid_forced = [month for month in forced_months if month < 1 or month > 12]
    if invalid_forced:
        print(f"Invalid --force-month values: {invalid_forced}", file=sys.stderr)
        return 2

    current_mode = "download" if (args.execute or args.run) else "dry-run"
    state_file = batch_state_path(output_dir, account_name, args.year)
    summary_file = batch_summary_path(output_dir, account_name, args.year)
    log_file = batch_log_path(output_dir, account_name, args.year)
    state = load_batch_state(state_file, account_name, args.year)
    same_mode = state.get("last_mode") == current_mode
    completed_state = {int(month) for month in state.get("completed_months", [])}
    failed_state = {int(month) for month in state.get("failed_months", [])}
    results: list[BatchMonthResult] = []

    write_batch_log(log_file, f"BATCH START account={account_name} year={args.year} months={months} mode={current_mode}")
    state["last_mode"] = current_mode
    save_batch_state(state_file, state)

    for month in months:
        output_folder = str(month_output_folder(output_dir, account_name, args.year, month))
        if same_mode and month in completed_state and month not in forced_months:
            result = BatchMonthResult(month=month, status="SKIPPED_COMPLETED", output_folder=output_folder)
            results.append(result)
            write_batch_log(log_file, f"MONTH {month:02d} skipped: already completed")
            continue
        if month in failed_state and not args.resume and month not in forced_months:
            result = BatchMonthResult(month=month, status="FAILED_PREVIOUS", errors=1, output_folder=output_folder, message="Previous failure; use --resume or --force-month.")
            results.append(result)
            write_batch_log(log_file, f"MONTH {month:02d} stopped: previous failure requires --resume or --force-month")
            break
        if month in failed_state and args.resume and month not in forced_months:
            result = BatchMonthResult(month=month, status="SKIPPED_FAILED_RESUME", output_folder=output_folder)
            results.append(result)
            write_batch_log(log_file, f"MONTH {month:02d} skipped during resume: previously failed")
            continue

        start = dt.date(args.year, month, 1)
        end = month_end(args.year, month)
        write_batch_log(log_file, f"MONTH {month:02d} dry-run start")
        dry_plans, dry_skipped = scan_config_accounts(
            config=config,
            conn=conn,
            selected_accounts={account_name},
            start=start,
            end=end,
            execute=False,
            max_messages=args.max_messages,
            platform=args.platform,
            output_dir=output_dir,
        )
        dry_errors = count_errors(dry_plans, dry_skipped)
        paths_ok, path_error = validate_plan_paths(dry_plans, output_dir, account_name, args.year, month)
        result = BatchMonthResult(
            month=month,
            planned=len(dry_plans),
            duplicates=sum(1 for plan in dry_plans if plan.duplicate),
            errors=dry_errors + (0 if paths_ok else 1),
            supplier_summary=supplier_summary(dry_plans),
            output_folder=output_folder,
        )
        if dry_errors or not paths_ok:
            result.status = "FAILED_DRY_RUN"
            result.message = path_error or "; ".join(dry_skipped)
            results.append(result)
            failed_state.add(month)
            state["failed_months"] = sorted(failed_state)
            state["last_error"] = result.message
            save_batch_state(state_file, state)
            write_batch_log(log_file, f"MONTH {month:02d} dry-run failed: {result.message}")
            break
        write_batch_log(log_file, f"MONTH {month:02d} dry-run ok planned={len(dry_plans)} duplicates={result.duplicates}")

        if args.execute or args.run:
            write_batch_log(log_file, f"MONTH {month:02d} download start")
            download_plans, download_skipped = scan_config_accounts(
                config=config,
                conn=conn,
                selected_accounts={account_name},
                start=start,
                end=end,
                execute=True,
                max_messages=args.max_messages,
                platform=args.platform,
                output_dir=output_dir,
            )
            download_errors = count_errors(download_plans, download_skipped)
            result.saved = sum(1 for plan in download_plans if plan.saved)
            result.duplicates = sum(1 for plan in download_plans if plan.duplicate)
            result.errors = download_errors
            result.supplier_summary = supplier_summary(download_plans)
            if download_errors:
                result.status = "FAILED_DOWNLOAD"
                result.message = "; ".join(download_skipped)
                failed_state.add(month)
                state["failed_months"] = sorted(failed_state)
                state["last_error"] = result.message
                save_batch_state(state_file, state)
                results.append(result)
                write_batch_log(log_file, f"MONTH {month:02d} download failed: {result.message}")
                break
            result.status = "COMPLETED_DOWNLOAD"
            write_batch_log(log_file, f"MONTH {month:02d} download ok saved={result.saved} duplicates={result.duplicates}")
        else:
            result.status = "COMPLETED_DRY_RUN"
            write_batch_log(log_file, f"MONTH {month:02d} dry-run complete")

        completed_state.add(month)
        failed_state.discard(month)
        state["completed_months"] = sorted(completed_state)
        state["failed_months"] = sorted(failed_state)
        state["last_completed_month"] = month
        state["last_error"] = ""
        save_batch_state(state_file, state)
        results.append(result)

    write_batch_summary(summary_file, account_name, args.year, results)
    write_batch_log(log_file, f"BATCH END summary={summary_file} state={state_file}")
    print(f"Batch summary: {summary_file}")
    print(f"Batch state: {state_file}")
    print(f"Batch log: {log_file}")
    return 1 if any(result.status.startswith("FAILED") for result in results) else 0


def run_retry_failed(args: argparse.Namespace, config: dict[str, Any], conn: sqlite3.Connection, output_dir: Path) -> int:
    path = failed_tasks_path(output_dir)
    if not path.exists():
        print(f"No failed task file found: {path}")
        return 0
    tasks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        account = str(item.get("account") or "").strip()
        platform = normalize_platform(str(item.get("platform") or ""))
        year = item.get("year")
        month = item.get("month")
        if not account or not year or not month:
            continue
        if args.account and account not in set(args.account):
            continue
        if args.platform and normalize_platform(args.platform) not in {platform, MARKETPLACE_ALL}:
            continue
        tasks.append({"account": account, "platform": platform, "year": int(year), "month": int(month)})

    unique_tasks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for task in tasks:
        key = (task["account"], task["platform"], task["year"], task["month"])
        if key not in seen:
            seen.add(key)
            unique_tasks.append(task)

    if not unique_tasks:
        print("No failed tasks matched the retry filters.")
        return 0

    execute = bool(args.execute or args.run)
    failures = 0
    for task in unique_tasks:
        start = dt.date(task["year"], task["month"], 1)
        end = month_end(task["year"], task["month"])
        platform = task["platform"] or args.platform
        print(f"Retry failed task: account={task['account']} platform={platform or 'generic'} month={task['year']}-{task['month']:02d}")
        plans, skipped = scan_config_accounts(
            config=config,
            conn=conn,
            selected_accounts={task["account"]},
            start=start,
            end=end,
            execute=execute,
            max_messages=args.max_messages,
            platform=platform,
            output_dir=output_dir,
        )
        errors = count_errors(plans, skipped)
        if errors:
            failures += 1
            print(f"Retry failed with {errors} errors for {task['account']} {task['year']}-{task['month']:02d}")
        else:
            print(f"Retry OK planned={len(plans)} saved={sum(1 for plan in plans if plan.saved)} duplicates={sum(1 for plan in plans if plan.duplicate)}")
    return 1 if failures else 0


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    env_path = Path(args.env_file).resolve()
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2

    load_dotenv(env_path)
    config = load_config(config_path)

    output_dir = Path(os.environ.get("INVOICE_OUTPUT_DIR") or config.get("output_dir") or r"E:\Invoice")
    log_file = Path(config.get("log_file") or output_dir / "_logs" / "invoice_downloader.log")
    db_path = Path(config.get("index_db") or output_dir / "_index" / "invoice_index.sqlite3")
    report_file = Path(config.get("report_file") or output_dir / "invoice_download_report.md")

    init_logging(log_file)
    conn = init_db(db_path)

    if args.dry_run and (args.run or args.execute):
        print("Choose either --dry-run or download mode, not both.", file=sys.stderr)
        return 2

    if args.all_accounts and args.account:
        print("Use either --all-accounts or one or more --account values, not both.", file=sys.stderr)
        return 2
    if args.months and not args.year:
        print("--months requires --year", file=sys.stderr)
        return 2
    if args.platform:
        try:
            active_platforms(args.platform)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    execute = bool(args.execute or args.run)
    if args.execute and not args.i_understand_download:
        print("Refusing to download. Re-run with --execute --i-understand-download after confirming.", file=sys.stderr)
        return 2

    if args.retry_failed:
        return run_retry_failed(args, config, conn, output_dir)

    if args.batch:
        return run_batch_mode(args, config, conn, output_dir)

    selected_accounts = set(args.account or [])
    try:
        start, end = build_date_range(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    all_plans, skipped = scan_config_accounts(
        config=config,
        conn=conn,
        selected_accounts=selected_accounts,
        start=start,
        end=end,
        execute=execute,
        max_messages=args.max_messages,
        platform=args.platform,
        output_dir=output_dir,
    )

    write_report(report_file, all_plans, execute=execute, skipped=skipped)
    logging.info("Report written to %s", report_file)
    print(f"Report: {report_file}")
    print(f"Log: {log_file}")
    print(f"Index: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
