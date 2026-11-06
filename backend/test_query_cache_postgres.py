"""Optional integration against a dedicated cache database, never business tables."""
import os
import time
import unittest
from uuid import uuid4
from app.services.query_cache import QueryCache


@unittest.skipUnless(os.getenv('RAILHOP_TEST_POSTGRES_DSN'), 'Dedicated PostgreSQL integration DSN not configured')
class PostgresQueryCacheTests(unittest.TestCase):
    def test_independent_caches_share_empty_and_nonempty_data_without_extending_ttl(self):
        import psycopg
        dsn = os.environ['RAILHOP_TEST_POSTGRES_DSN']
        clock = [time.time()]
        first = QueryCache(dsn, clock=lambda:clock[0])
        second = QueryCache(dsn, clock=lambda:clock[0])
        parts = [str(uuid4())]
        empty_parts = [str(uuid4())]
        try:
            first.set('integration', parts, [{'run_date':'20261021','seat':'有'}], 15)
            first.set('integration', empty_parts, [], 15)
            self.assertEqual(second.get('integration',parts), [{'run_date':'20261021','seat':'有'}])
            self.assertEqual(second.get('integration',empty_parts), [])
            clock[0] += 14
            self.assertIsNotNone(second.get('integration',parts))
            clock[0] += 1
            self.assertIsNone(second.get('integration',parts))
            third = QueryCache(dsn, clock=lambda:clock[0])
            try:
                self.assertIsNone(third.get('integration',parts))
            finally:
                third.close()
        finally:
            first.close()
            second.close()
            with psycopg.connect(dsn) as conn:
                conn.execute('DELETE FROM railhop_cache.query_entries WHERE cache_key=ANY(%s)',
                    ([QueryCache._key('integration',parts),QueryCache._key('integration',empty_parts)],))


if __name__ == '__main__':
    unittest.main()
