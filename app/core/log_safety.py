"""Prevent OAuth callback query material leaking through default server logs."""
import logging
import re


class OAuthQueryFilter(logging.Filter):
    def filter(self, record):
        def redact(value):
            if not isinstance(value, str):
                return value
            return re.sub(r'([?&](?:code|state|input_token|access_token|refresh_token|client_secret)=)[^\s&"]*', r'\1[REDACTED]', value, flags=re.I)
        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def install():
    logging.getLogger('uvicorn.access').addFilter(OAuthQueryFilter())
    # Provider payloads are never logged. Avoid informational transport URL logs.
    logging.getLogger('httpx').addFilter(OAuthQueryFilter())
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
