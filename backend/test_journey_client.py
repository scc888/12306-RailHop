import unittest
from unittest.mock import Mock
from app.services.client_12306 import Ticket12306Client, RailwayQueryError
from test_transfer_gateway import row, railway_response


class JourneyClientTests(unittest.TestCase):
    def test_zero_waitlist_and_closed_train_are_not_available(self):
        client = Ticket12306Client()
        for seat, bookable in [('0','Y'), ('候补','Y'), ('未开售','Y'), ('有','N')]:
            ticket = client._parse_ticket_results([row(seat=seat,can_buy=bookable)], {})[0]
            self.assertFalse(ticket.seats.has_any_ticket)

    def test_strict_stops_reports_failure_and_uses_bounded_verified_requests(self):
        client = Ticket12306Client()
        client.ensure_init = Mock()
        client.session.get = Mock(return_value=railway_response({'status':False}))
        with self.assertRaises(RailwayQueryError):
            client.query_train_stops_strict('train','SHH','BJP','2026-10-11',timeout_seconds=2)
        client.session.get.return_value = railway_response({'status':True,'data':{'data':[
            {'station_no':'01','station_name':'上海','arrive_time':'----','start_time':'23:00','stopover_time':'----'},
            {'station_no':'02','station_name':'北京','arrive_time':'08:00','start_time':'----','stopover_time':'----'}]}})
        self.assertEqual(len(client.query_train_stops_strict('train','SHH','BJP','2026-10-11',timeout_seconds=2)),2)
        self.assertTrue(client.session.get.call_args.kwargs['verify'])
        self.assertLessEqual(client.session.get.call_args.kwargs['timeout'],2)


if __name__ == '__main__':
    unittest.main()
