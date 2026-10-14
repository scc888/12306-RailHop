"""Failure evidence must remain useful without exposing upstream secrets."""
import unittest
from unittest.mock import Mock

import requests

from app.services.client_12306 import RailwayQueryError, Ticket12306Client
from test_transfer_gateway import railway_response


LOGGER = 'app.services.client_12306'
SECRET = 'diagnostic-secret-value'


def response(body, status=200, content_type='application/json'):
    result = railway_response(body, status)
    result.url = f'https://kyfw.12306.cn/otn/leftTicket/queryG?token={SECRET}'
    result.headers.update({'Content-Type': content_type, 'Set-Cookie': f'JSESSIONID={SECRET}'})
    return result


class RailwayDiagnosticTests(unittest.TestCase):
    def client(self, result=None):
        client = Ticket12306Client()
        client.ensure_init = Mock()
        client.session.cookies.set('JSESSIONID', SECRET)
        client.session.get = Mock(return_value=result)
        return client

    def test_http_failure_logs_metadata_and_retry_after_without_secrets(self):
        result = response(f'<html>{SECRET}</html>', 429, 'text/html; charset=utf-8')
        result.headers['Retry-After'] = '60'
        result.headers['Location'] = f'https://user:{SECRET}@www.12306.cn/mormhweb/logFiles/error.html?token={SECRET}#{SECRET}'
        client = self.client(result)
        with self.assertLogs(LOGGER, level='ERROR') as captured, self.assertRaises(RailwayQueryError):
            client.query_tickets_strict('2026-10-13', 'SHH', 'BJP')
        logs = '\n'.join(captured.output)
        for expected in ('tickets_http_status', "'http_status': 429", "'retry_after': '60'",
                         'text/html', 'html', 'www.12306.cn/mormhweb/logFiles/error.html', 'request_id'):
            self.assertIn(expected, logs)
        self.assertNotIn(SECRET, logs)
        self.assertNotIn('Set-Cookie', logs)
        self.assertNotIn('user:', logs)

    def test_json_and_schema_failures_are_distinguishable(self):
        cases = [(f'<html>{SECRET}</html>', 'text/html', 'tickets_parse_json'),
                 ({'status': False, 'messages': [SECRET]}, 'application/json', 'tickets_business_status'),
                 ({'status': True, 'data': {}}, 'application/json', 'tickets_schema'),
                 ({'status': True, 'data': {'result': [SECRET]}}, 'application/json', 'tickets_rows')]
        for body, content_type, stage in cases:
            with self.subTest(stage=stage):
                client = self.client(response(body, content_type=content_type))
                with self.assertLogs(LOGGER, level='ERROR') as captured, self.assertRaises(RailwayQueryError):
                    client.query_tickets_strict('2026-10-13', 'SHH', 'BJP')
                logs = '\n'.join(captured.output)
                self.assertIn(stage, logs)
                self.assertIn("'http_status': 200", logs)
                self.assertNotIn(SECRET, logs)
                if stage == 'tickets_business_status':
                    self.assertIn("'json_status': False", logs)

    def test_network_failure_keeps_type_and_traceback_but_redacts_exception_values(self):
        client = self.client()
        cause = requests.exceptions.SSLError(f'https://user:{SECRET}@proxy.invalid/?token={SECRET}')
        cause.__cause__ = ValueError(SECRET)
        client.session.get.side_effect = cause
        with self.assertLogs(LOGGER, level='ERROR') as captured, self.assertRaises(RailwayQueryError) as raised:
            client.query_tickets_strict('2026-10-13', 'SHH', 'BJP')
        logs = '\n'.join(captured.output)
        self.assertIn('tickets_request', logs)
        self.assertIn('SSLError', logs)
        self.assertIn('ValueError', logs)
        self.assertIn('Traceback', logs)
        self.assertNotIn(SECRET, logs)
        self.assertIs(raised.exception.__cause__, cause)

    def test_session_initialization_failure_is_logged(self):
        client = Ticket12306Client()
        client.session.get = Mock(return_value=response('unavailable', 503, 'text/plain'))
        with self.assertLogs(LOGGER, level='ERROR') as captured, self.assertRaises(RailwayQueryError):
            client.ensure_init(strict=True)
        logs = '\n'.join(captured.output)
        self.assertIn('session_init', logs)
        self.assertIn("'http_status': 503", logs)
        self.assertNotIn(SECRET, logs)

    def test_redirect_probe_failure_records_the_probe_response(self):
        client = self.client()
        redirect = response('', 302)
        redirect.headers['Location'] = f'/mormhweb/logFiles/error.html?token={SECRET}'
        probe = response(f'<html>{SECRET}</html>', content_type='text/html')
        probe.url = 'https://kyfw.12306.cn/otn/leftTicket/query'
        client.session.get.side_effect = [redirect, probe]
        with self.assertLogs(LOGGER, level='WARNING') as captured, self.assertRaises(RailwayQueryError):
            client.query_tickets_strict('2026-10-13', 'SHH', 'BJP')
        logs = '\n'.join(captured.output)
        self.assertIn("'http_status': 302", logs)
        self.assertIn('tickets_probe_parse_json', logs)
        self.assertIn('kyfw.12306.cn/otn/leftTicket/query', logs)
        self.assertNotIn(SECRET, logs)

    def test_redirect_recovery_preserves_existing_contract_and_logs_recovery(self):
        client = self.client()
        client.session.get.side_effect = [response('', 302), response({'c_url': 'leftTicket/queryA'}, 302),
            response({'status': True, 'data': {'result': [], 'map': {}}})]
        with self.assertLogs(LOGGER, level='INFO') as captured:
            self.assertEqual(client.query_tickets_strict('2026-10-13', 'SHH', 'BJP'), [])
        logs = '\n'.join(captured.output)
        self.assertIn('12306 query recovered', logs)
        self.assertIn('leftTicket/queryA', logs)
        self.assertNotIn(SECRET, logs)
        self.assertEqual(client.session.get.call_count, 3)

    def test_stops_failure_records_followed_redirects(self):
        result = response(f'<html>{SECRET}</html>', content_type='text/html')
        result.url = f'https://www.12306.cn/mormhweb/logFiles/error.html?token={SECRET}'
        result.history = [response('', 302)]
        result.history[0].headers['Location'] = result.url
        client = self.client(result)
        with self.assertLogs(LOGGER, level='ERROR') as captured, self.assertRaises(RailwayQueryError):
            client.query_train_stops_strict('private-train-number', 'SHH', 'BJP', '2026-10-13')
        logs = '\n'.join(captured.output)
        self.assertIn('stops_parse_json', logs)
        self.assertIn("'redirect_count': 1", logs)
        self.assertIn('www.12306.cn/mormhweb/logFiles/error.html', logs)
        self.assertNotIn(SECRET, logs)
        self.assertNotIn('private-train-number', logs)

    def test_successful_ordinary_queries_do_not_emit_info_logs(self):
        client = self.client(response({'status': True, 'data': {'result': [], 'map': {}}}))
        with self.assertNoLogs(LOGGER, level='INFO'):
            self.assertEqual(client.query_tickets_strict('2026-10-13', 'SHH', 'BJP'), [])


if __name__ == '__main__':
    unittest.main()
