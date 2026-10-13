import unittest
from datetime import date
from unittest.mock import Mock
from app.services.client_12306 import Ticket12306Client, RailwayQueryError
from test_transfer_gateway import row, railway_response


class JourneyClientTests(unittest.TestCase):
    def test_d_train_sleeper_fares_reach_ticket_and_plan_seats(self):
        from app.services.transfer_ticket_gateway import ticket_to_leg
        # Public Beijing -> Shanghai responses captured on 2026-10-13 for 2026-10-14.
        samples = [
            ('D7', 'J044000021O036100021I060100021O036103036', '¥601', '¥440', '¥361'),
            ('D17', 'J044700021O036700021I061000021O036703036', '¥610', '¥447', '¥367'),
            ('D9', 'J047600021O031700021I060300021', '¥603', '¥476', '¥317'),
        ]
        client = Ticket12306Client()
        for train, encoded, first, second, seat in samples:
            with self.subTest(train=train):
                parts = row().split('|')
                parts[3], parts[23], parts[28], parts[39] = train, '有', '有', encoded
                ticket = client._parse_ticket_results(['|'.join(parts)], {})[0]
                self.assertEqual(ticket.prices.get('rw'), first)
                self.assertEqual(ticket.prices.get('yw'), second)
                self.assertEqual(ticket.prices.get('ze'), seat)
                planned = ticket_to_leg(ticket, date(2026, 10, 14), ['rw', 'yw'])
                self.assertEqual([s.price_fen for s in planned.seats],
                                 [int(first[1:]) * 100, int(second[1:]) * 100])

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
