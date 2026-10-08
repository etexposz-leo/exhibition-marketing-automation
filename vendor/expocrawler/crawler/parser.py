"""Generic page parser for exhibition/public news pages.

The parser is intentionally conservative: it extracts common metadata from
arbitrary public pages and leaves room for site-specific parsers later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".m4v", ".avi", ".m3u8")


@dataclass
class ParsedPage:
    source_site: str
    page_title: str
    event_name: str
    publish_date: str
    text_content: str
    article_title: str = ""
    category: str = ""
    keywords: str = ""
    image_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    source_url: str = ""
    company_name: str = ""
    booth_number: str = ""
    country: str = ""
    website: str = ""
    email: str = ""
    phone: str = ""
    description: str = ""
    product_category: str = ""
    instagram_url: str = ""
    tiktok_url: str = ""
    social_caption: str = ""
    hashtags: str = ""
    post_time: str = ""
    top_comments: str = ""
    original_social_url: str = ""


class BaseParser:
    """Interface for future site-specific parsers."""

    def can_parse(self, url: str, html: str, crawl_task: str = "") -> bool:
        return False

    def parse(self, url: str, html: str, crawl_task: str = "") -> ParsedPage:
        raise NotImplementedError


class GenericParser(BaseParser):
    """Generic parser for pages with unknown structure."""

    def can_parse(self, url: str, html: str, crawl_task: str = "") -> bool:
        return True

    def parse(self, url: str, html: str, crawl_task: str = "") -> ParsedPage:
        soup = BeautifulSoup(html or "", "html.parser")
        self._remove_noise(soup)

        title = self._first_text(
            soup,
            [
                ("meta", {"property": "og:title"}, "content"),
                ("meta", {"name": "twitter:title"}, "content"),
                ("h1", {}, None),
                ("title", {}, None),
            ],
        )
        event_name = self._guess_event_name(soup, title)
        publish_date = self._first_text(
            soup,
            [
                ("meta", {"property": "article:published_time"}, "content"),
                ("meta", {"name": "pubdate"}, "content"),
                ("meta", {"name": "publishdate"}, "content"),
                ("meta", {"name": "date"}, "content"),
                ("time", {}, "datetime"),
                ("time", {}, None),
            ],
        )
        text_content = self._extract_text(soup)
        image_urls = self._extract_images(soup, url)
        video_urls = self._extract_videos(soup, url)
        instagram_url, tiktok_url = self._extract_social_links(soup, url)
        category = self._extract_category(soup)
        keywords = self._extract_keywords(soup, title, text_content)
        description = self._extract_description(soup, text_content)

        return ParsedPage(
            source_site=self._source_site(url),
            page_title=title,
            article_title=title,
            category=category,
            keywords=keywords,
            event_name=event_name,
            publish_date=publish_date,
            text_content=text_content,
            image_urls=image_urls,
            video_urls=video_urls,
            source_url=url,
            description=description,
            instagram_url=instagram_url,
            tiktok_url=tiktok_url,
        )

    @staticmethod
    def _remove_noise(soup: BeautifulSoup) -> None:
        for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "header", "aside"]):
            tag.decompose()

    @staticmethod
    def _source_site(url: str) -> str:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    def _first_text(self, soup: BeautifulSoup, selectors: Iterable[tuple[str, dict, str | None]]) -> str:
        for tag_name, attrs, attr_name in selectors:
            tag = soup.find(tag_name, attrs=attrs)
            if not tag:
                continue
            value = tag.get(attr_name) if attr_name else tag.get_text(" ", strip=True)
            value = self._clean(str(value or ""))
            if value:
                return value
        return ""

    def _guess_event_name(self, soup: BeautifulSoup, fallback_title: str) -> str:
        for selector in [
            {"property": "og:site_name"},
            {"name": "application-name"},
            {"name": "twitter:site"},
        ]:
            tag = soup.find("meta", attrs=selector)
            if tag and tag.get("content"):
                return self._clean(str(tag["content"]))
        return fallback_title[:120]

    def _extract_text(self, soup: BeautifulSoup) -> str:
        candidates = []
        scope = self._content_scope(soup)
        if scope:
            candidates.append(scope.get_text(" ", strip=True))
        if not candidates:
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            candidates.append(" ".join(paragraphs))
        if not candidates or not self._clean(candidates[0]):
            candidates = [soup.get_text(" ", strip=True)]
        text = self._clean(max(candidates, key=len, default=""))
        return text[:50000]

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        scope = self._content_scope(soup) or soup
        for img in scope.find_all("img"):
            src = self._best_image_src(img)
            if src:
                absolute = urljoin(base_url, str(src))
                if absolute.startswith(("http://", "https://")) and absolute not in urls:
                    urls.append(absolute)
            srcset = img.get("srcset")
            if srcset:
                best_srcset = self._best_srcset_url(str(srcset))
                if best_srcset:
                    absolute = urljoin(base_url, best_srcset)
                    if absolute.startswith(("http://", "https://")) and absolute not in urls:
                        urls.append(absolute)
        for meta in soup.find_all("meta", attrs={"property": "og:image"}):
            content = meta.get("content")
            if content and not urls:
                absolute = urljoin(base_url, str(content))
                if absolute not in urls:
                    urls.append(absolute)
        return urls[:80]

    def _extract_videos(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        scope = self._content_scope(soup) or soup
        for tag in scope.find_all(["video", "source", "iframe", "a"]):
            src = tag.get("src") or tag.get("href")
            if not src:
                continue
            absolute = urljoin(base_url, str(src))
            if self._looks_like_video(absolute) and absolute not in urls:
                urls.append(absolute)
        for meta in soup.find_all("meta", attrs={"property": "og:video"}):
            content = meta.get("content")
            if content:
                absolute = urljoin(base_url, str(content))
                if absolute not in urls:
                    urls.append(absolute)
        return urls[:50]

    def _extract_category(self, soup: BeautifulSoup) -> str:
        for selector in [
            ("meta", {"property": "article:section"}, "content"),
            ("meta", {"name": "category"}, "content"),
        ]:
            value = self._first_text(soup, [selector])
            if value:
                return value[:200]
        for attrs in (
            {"class": re.compile(r"breadcrumb|category|cat", re.I)},
            {"id": re.compile(r"breadcrumb|category|cat", re.I)},
        ):
            tag = soup.find(attrs=attrs)
            if tag:
                value = self._clean(tag.get_text(" / ", strip=True))
                if value:
                    return value[:200]
        return ""

    def _extract_keywords(self, soup: BeautifulSoup, title: str, text: str) -> str:
        meta = self._first_text(soup, [("meta", {"name": "keywords"}, "content")])
        if meta:
            return meta[:500]
        seed_terms = (
            "exhibition",
            "expo",
            "booth",
            "trade show",
            "stand",
            "展会",
            "展台",
            "展厅",
            "案例",
            "设计",
            "3D",
            "video",
        )
        combined = f"{title} {text}".lower()
        hits = [term for term in seed_terms if term.lower() in combined]
        return ", ".join(hits)

    def _extract_description(self, soup: BeautifulSoup, text: str) -> str:
        for selector in [
            ("meta", {"name": "description"}, "content"),
            ("meta", {"property": "og:description"}, "content"),
        ]:
            value = self._first_text(soup, [selector])
            if value:
                return value[:1000]
        return text[:1000]

    def _content_scope(self, soup: BeautifulSoup):
        for tag_name in ("article", "main"):
            tag = soup.find(tag_name)
            if tag:
                return tag
        patterns = re.compile(
            r"content|article|post|entry|case|gallery|detail|news|body|portfolio|project|showcase",
            re.I,
        )
        candidates = soup.find_all(attrs={"class": patterns}) + soup.find_all(attrs={"id": patterns})
        if candidates:
            return max(candidates, key=lambda tag: len(tag.get_text(" ", strip=True)))
        return soup.body or soup

    def _best_image_src(self, img) -> str:
        for attr in (
            "data-original",
            "data-full",
            "data-large",
            "data-zoom",
            "data-src",
            "data-lazy-src",
            "data-url",
            "src",
        ):
            value = img.get(attr)
            if value:
                return str(value)
        return ""

    @staticmethod
    def _best_srcset_url(srcset: str) -> str:
        best_url = ""
        best_width = -1
        for candidate in srcset.split(","):
            parts = candidate.strip().split()
            if not parts:
                continue
            url = parts[0]
            width = 0
            if len(parts) > 1 and parts[1].endswith("w"):
                try:
                    width = int(parts[1][:-1])
                except ValueError:
                    width = 0
            if width >= best_width:
                best_width = width
                best_url = url
        return best_url

    def _extract_social_links(self, soup: BeautifulSoup, base_url: str) -> tuple[str, str]:
        instagram_url = ""
        tiktok_url = ""
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, str(href))
            lowered = absolute.lower()
            if "instagram.com" in lowered and not instagram_url:
                instagram_url = absolute
            if "tiktok.com" in lowered and not tiktok_url:
                tiktok_url = absolute
        return instagram_url, tiktok_url

    @staticmethod
    def _looks_like_image(url: str) -> bool:
        path = urlparse(url).path.lower()
        return path.endswith(IMAGE_EXTENSIONS)

    @staticmethod
    def _looks_like_video(url: str) -> bool:
        lowered = url.lower()
        path = urlparse(url).path.lower()
        return path.endswith(VIDEO_EXTENSIONS) or any(
            token in lowered for token in ("youtube.com", "youtu.be", "vimeo.com")
        )


class DtwExhibitorParser(GenericParser):
    """Heuristic exhibitor parser for dtw.net and exhibitor-directory tasks."""

    FIELD_LABELS = {
        "booth_number": ("booth", "booth no", "booth number", "stand", "stand no", "展位号"),
        "country": ("country", "location", "国家"),
        "product_category": ("category", "product category", "products", "industry", "分类"),
        "phone": ("phone", "tel", "telephone", "电话"),
        "email": ("email", "e-mail", "邮箱"),
        "website": ("website", "web site", "官网", "site"),
    }

    def can_parse(self, url: str, html: str, crawl_task: str = "") -> bool:
        host = urlparse(url).netloc.lower()
        task = crawl_task.lower()
        return "dtw.net" in host or "exhibitor" in task or "参展商" in crawl_task

    def parse(self, url: str, html: str, crawl_task: str = "") -> ParsedPage:
        parsed = super().parse(url, html, crawl_task)
        soup = BeautifulSoup(html or "", "html.parser")
        self._remove_noise(soup)
        text = parsed.text_content

        parsed.company_name = self._company_name(soup, parsed.page_title)
        parsed.booth_number = self._label_value(soup, text, "booth_number")
        parsed.country = self._label_value(soup, text, "country")
        parsed.website = self._website(soup, url) or self._label_value(soup, text, "website")
        parsed.email = self._email(soup, text)
        parsed.phone = self._phone(soup, text) or self._label_value(soup, text, "phone")
        parsed.description = self._description(soup, text)
        parsed.product_category = self._label_value(soup, text, "product_category")
        instagram_url, tiktok_url = self._extract_social_links(soup, url)
        parsed.instagram_url = instagram_url or parsed.instagram_url
        parsed.tiktok_url = tiktok_url or parsed.tiktok_url
        return parsed

    def _company_name(self, soup: BeautifulSoup, fallback_title: str) -> str:
        for selector in [
            ("h1", {}),
            ("meta", {"property": "og:title"}),
            ("meta", {"name": "title"}),
        ]:
            tag = soup.find(selector[0], attrs=selector[1])
            if not tag:
                continue
            value = tag.get("content") or tag.get_text(" ", strip=True)
            value = self._clean(str(value or ""))
            if value:
                return value[:200]
        return fallback_title[:200]

    def _label_value(self, soup: BeautifulSoup, text: str, field_name: str) -> str:
        labels = sorted(self.FIELD_LABELS[field_name], key=len, reverse=True)
        for label in labels:
            value = self._same_tag_label_value(soup, label)
            if value:
                return value[:300]
        for label in labels:
            value = self._near_label_value(soup, label)
            if value:
                return value[:300]
        for label in labels:
            pattern = re.compile(rf"{re.escape(label)}\s*[:：#]?\s*([^\n|,;]+)", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                return self._clean(match.group(1))[:300]
        return ""

    def _same_tag_label_value(self, soup: BeautifulSoup, label: str) -> str:
        pattern = re.compile(rf"^\s*{re.escape(label)}\s*[:：#]\s*(.+)$", re.IGNORECASE)
        for tag in soup.find_all(["p", "li", "div", "span", "td", "th", "dt", "dd"]):
            value = self._clean(tag.get_text(" ", strip=True))
            match = pattern.match(value)
            if match:
                return self._clean(match.group(1))
        return ""

    def _near_label_value(self, soup: BeautifulSoup, label: str) -> str:
        pattern = re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)
        tag = soup.find(string=pattern)
        if not tag:
            return ""
        parent = getattr(tag, "parent", None)
        if not parent:
            return ""
        for sibling in parent.find_next_siblings(limit=3):
            value = self._clean(sibling.get_text(" ", strip=True))
            if value and value.lower() != label.lower():
                return value
        value = self._clean(parent.get_text(" ", strip=True))
        value = re.sub(rf"^{re.escape(label)}\s*[:：#]?\s*", "", value, flags=re.IGNORECASE)
        return value if value.lower() != label.lower() else ""

    def _website(self, soup: BeautifulSoup, page_url: str) -> str:
        page_host = urlparse(page_url).netloc.lower()
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue
            absolute = urljoin(page_url, str(href))
            parsed = urlparse(absolute)
            host = parsed.netloc.lower()
            if parsed.scheme in ("http", "https") and host and host != page_host:
                if not any(social in host for social in ("instagram", "tiktok", "facebook", "linkedin", "youtube")):
                    return absolute
        return ""

    def _email(self, soup: BeautifulSoup, text: str) -> str:
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            if href.lower().startswith("mailto:"):
                return href.split(":", 1)[1].split("?", 1)[0]
        match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
        return match.group(0) if match else ""

    def _phone(self, soup: BeautifulSoup, text: str) -> str:
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            if href.lower().startswith("tel:"):
                return href.split(":", 1)[1]
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
        return self._clean(match.group(0)) if match else ""

    def _description(self, soup: BeautifulSoup, text: str) -> str:
        for selector in [
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
        ]:
            tag = soup.find(selector[0], attrs=selector[1])
            if tag and tag.get("content"):
                return self._clean(str(tag["content"]))[:3000]
        paragraphs = [self._clean(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
        useful = [p for p in paragraphs if len(p) > 50]
        if useful:
            return max(useful, key=len)[:3000]
        return text[:3000]


def parse_public_social_page(url: str, html: str) -> dict[str, str | list[str]]:
    """Extract only public metadata visible in the returned social page HTML."""

    parser = GenericParser()
    soup = BeautifulSoup(html or "", "html.parser")
    parser._remove_noise(soup)
    title = parser._first_text(
        soup,
        [
            ("meta", {"property": "og:title"}, "content"),
            ("meta", {"name": "twitter:title"}, "content"),
            ("title", {}, None),
        ],
    )
    description = parser._first_text(
        soup,
        [
            ("meta", {"property": "og:description"}, "content"),
            ("meta", {"name": "description"}, "content"),
            ("meta", {"name": "twitter:description"}, "content"),
        ],
    )
    text = parser._extract_text(soup)
    caption = description or title or text[:500]
    hashtags = " ".join(sorted(set(re.findall(r"#[\w\u4e00-\u9fff-]+", caption + " " + text))))[:1000]
    post_time = parser._first_text(
        soup,
        [
            ("meta", {"property": "article:published_time"}, "content"),
            ("time", {}, "datetime"),
            ("time", {}, None),
        ],
    )
    comments = []
    for selector in ({"class": re.compile("comment", re.I)}, {"data-e2e": re.compile("comment", re.I)}):
        for tag in soup.find_all(attrs=selector):
            value = parser._clean(tag.get_text(" ", strip=True))
            if value and value not in comments:
                comments.append(value[:300])
            if len(comments) >= 5:
                break
    return {
        "social_caption": caption[:2000],
        "hashtags": hashtags,
        "post_time": post_time,
        "top_comments": "\n".join(comments),
        "image_urls": parser._extract_images(soup, url),
        "video_urls": parser._extract_videos(soup, url),
        "original_social_url": url,
    }


class ParserRegistry:
    """Small registry so custom site parsers can be plugged in later."""

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = [DtwExhibitorParser()]
        self.generic = GenericParser()

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)

    def parse(self, url: str, html: str, crawl_task: str = "") -> ParsedPage:
        for parser in self._parsers:
            if parser.can_parse(url, html, crawl_task):
                return parser.parse(url, html, crawl_task)
        return self.generic.parse(url, html, crawl_task)
