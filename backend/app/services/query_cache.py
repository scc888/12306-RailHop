"""Bounded cache of public railway data; PostgreSQL is an optional shared store."""
import copy
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from ..config import settings

logger = logging.getLogger(__name__)


class QueryCache:
    def __init__(self, dsn='', max_entries=2048, clock=time.time):
        self.clock = clock
        self.max_entries = max_entries
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._database_lock = threading.Lock()
        self._pool = None
        self._dsn = dsn
        self._schema_ready = False
        self._retry_at = 0
        self._cleanup_at = 0

    @staticmethod
    def _key(kind, parts):
        encoded = json.dumps(['v1', kind, *parts], ensure_ascii=True, separators=(',', ':'))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _remember(self, key, payload, expires_at):
        with self._lock:
            self._entries[key] = (expires_at, copy.deepcopy(payload))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def _connection_pool(self):
        if self._schema_ready:
            return self._pool
        if not self._database_lock.acquire(blocking=False):
            return None
        try:
            if time.monotonic() < self._retry_at:
                return None
            if self._pool is None:
                from psycopg_pool import ConnectionPool
                self._pool = ConnectionPool(self._dsn, min_size=0, max_size=4,
                    timeout=1, kwargs={'connect_timeout':2, 'options':'-c statement_timeout=250'},
                    open=True)
            if not self._schema_ready:
                with self._pool.connection() as conn:
                    conn.execute('CREATE SCHEMA IF NOT EXISTS railhop_cache')
                    conn.execute('''CREATE TABLE IF NOT EXISTS railhop_cache.query_entries (
                        cache_key text PRIMARY KEY, payload jsonb NOT NULL, expires_at double precision NOT NULL)''')
                    conn.execute('CREATE INDEX IF NOT EXISTS query_entries_expiry ON railhop_cache.query_entries (expires_at)')
                self._schema_ready = True
                logger.info('PostgreSQL railway query cache ready')
        finally:
            self._database_lock.release()
        return self._pool

    def _database(self, operation):
        if not self._dsn or time.monotonic() < self._retry_at:
            return None

        try:
            pool = self._connection_pool()
            if pool is None:
                return None
            with pool.connection() as conn:
                return operation(conn)
        except Exception as exc:
            # A failed database must not turn public ticket queries into failures,
            # or add a connection timeout to every interval in a large search.
            self._retry_at = time.monotonic() + 15
            logger.warning('PostgreSQL query cache unavailable; using memory cache: error_type=%s', type(exc).__name__)
            return None

    def close(self):
        with self._database_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
                self._schema_ready = False

    def get(self, kind, parts):
        key, now = self._key(kind, parts), self.clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > now:
                self._entries.move_to_end(key)
                return copy.deepcopy(cached[1])
            self._entries.pop(key, None)
        row = self._database(lambda conn: conn.execute(
            'SELECT payload, expires_at FROM railhop_cache.query_entries WHERE cache_key=%s AND expires_at>%s',
            (key, now)).fetchone())
        if row and row[1] > self.clock():
            self._remember(key, row[0], row[1])
            return copy.deepcopy(row[0])
        return None

    def set(self, kind, parts, payload, ttl):
        if ttl <= 0:
            return
        key, now = self._key(kind, parts), self.clock()
        expires_at = now + ttl
        self._remember(key, payload, expires_at)
        def save(conn):
            from psycopg.types.json import Jsonb
            conn.execute('''INSERT INTO railhop_cache.query_entries (cache_key, payload, expires_at)
                VALUES (%s, %s, %s) ON CONFLICT (cache_key)
                DO UPDATE SET payload=EXCLUDED.payload, expires_at=EXCLUDED.expires_at''',
                (key, Jsonb(payload), expires_at))
            if now >= self._cleanup_at:
                conn.execute('DELETE FROM railhop_cache.query_entries WHERE expires_at<=%s', (now,))
                self._cleanup_at = now + 60
        self._database(save)


query_cache = QueryCache(settings.QUERY_CACHE_DATABASE_URL, settings.QUERY_CACHE_SIZE)
