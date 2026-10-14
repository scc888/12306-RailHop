"""Bounded upstream metadata; never log bodies, cookies or exception values."""
import logging
import re
import time
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit
from uuid import uuid4


def safe_endpoint(value):
    if not isinstance(value, str) or not value:
        return '-'
    try:
        parts = urlsplit(value)
        # Unexpected paths can themselves contain credentials or verification tokens.
        path = parts.path if re.fullmatch(
            r'/otn/leftTicket/(?:init|query[A-Za-z]*)|/otn/czxx/queryByTrainNo|'
            r'/mormhweb/logFiles/error\.html|/otn/login/init', parts.path) else '/<other-path>'
        return f'{parts.hostname or ""}{path}'
    except ValueError:
        return '<invalid-url>'


class RailwayDiagnostics:
    def __init__(self, logger, operation, **context):
        self.logger, self.operation, self.context = logger, operation, context
        self.request_id = uuid4().hex[:12]
        self.started = time.monotonic()
        self.stage, self.endpoint, self.response = operation, '', None
        self.json_status = None

    def begin(self, stage, endpoint):
        self.stage, self.endpoint, self.response = stage, endpoint, None
        self.json_status = None

    def observe(self, response, level=logging.DEBUG):
        self.response = response
        if self.logger.isEnabledFor(level):
            self.logger.log(level, '12306 response: %s', self.metadata())

    def parsed(self, payload):
        status = payload.get('status') if isinstance(payload, dict) else None
        self.json_status = status if isinstance(status, bool) else 'missing_or_invalid'

    def metadata(self):
        result = dict(request_id=self.request_id, operation=self.operation, stage=self.stage,
            **self.context, elapsed_ms=round((time.monotonic() - self.started) * 1000),
            endpoint=safe_endpoint(self.endpoint), json_status=self.json_status)
        response = self.response
        if response is None:
            return result
        headers = response.headers if isinstance(response.headers, Mapping) else {}
        content_type = headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if not re.fullmatch(r'[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+', content_type):
            content_type = 'unknown'
        body = response.content if isinstance(response.content, bytes) else b''
        prefix = body[:256].lstrip()[:64].lower()
        kind = 'empty' if not body else 'html' if prefix.startswith(b'<') else (
            'json_like' if prefix.startswith((b'{', b'[')) else 'other')
        url = response.url if isinstance(response.url, str) and response.url else self.endpoint
        location = headers.get('Location', '')
        retry_after = headers.get('Retry-After', '')
        # Keep only standard Retry-After forms; arbitrary header values stay out of logs.
        if not re.fullmatch(r'\d{1,8}|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT', retry_after):
            retry_after = '-'
        history = response.history if isinstance(response.history, (list, tuple)) else []
        result.update(http_status=response.status_code, content_type=content_type,
            body_bytes=len(body), body_kind=kind, url=safe_endpoint(url),
            redirect=safe_endpoint(urljoin(url, location)) if location else '-',
            retry_after=retry_after, redirect_count=len(history),
            redirect_chain=[dict(http_status=item.status_code, url=safe_endpoint(item.url),
                location=safe_endpoint(urljoin(item.url or url, item.headers.get('Location', '')))
                    if item.headers.get('Location') else '-') for item in history[:4]])
        return result

    def failure(self, error):
        types, seen, current = [], set(), error
        while current is not None and id(current) not in seen and len(types) < 8:
            seen.add(id(current))
            types.append(type(current).__name__)
            current = current.__cause__ or current.__context__
        # requests exceptions can embed proxy credentials and query strings. Keep the
        # original call stack, but substitute a value-free exception for formatting.
        safe_error = RuntimeError(' -> '.join(types))
        self.logger.error('12306 request failed: %s error_types=%s', self.metadata(), types,
            exc_info=(RuntimeError, safe_error, error.__traceback__))

    def recovered(self):
        self.logger.info('12306 query recovered: %s', self.metadata())
