import unittest
from datetime import datetime
from app.services.route_policy import RoutePolicy
from app.services.station_service import station_service
from app.services.transfer_ticket_gateway import CST
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService
from app.models.transfer_schemas import TransferQueryRequest
from test_transfer_planner import station, leg, Samples, NOW


class RoutePolicyTests(unittest.TestCase):
    def test_beijing_shanghai_excludes_changchun_but_keeps_nanjing_and_zhengzhou(self):
        policy = RoutePolicy('BJP', 'SHH', station_service)
        self.assertFalse(policy.candidate('CCT'))
        self.assertFalse(policy.candidate('CRT'))
        self.assertTrue(policy.candidate('NKH'))
        self.assertTrue(policy.candidate('ZAF'))  # Not a north/south blacklist.
        self.assertTrue(RoutePolicy('BJP','SHH',station_service,allow_large_detour=True).candidate('CCT'))
        manual = RoutePolicy('BJP','SHH',station_service,required=['CCT'])
        self.assertTrue(manual.candidate('CCT'))

    def test_missing_coordinate_is_not_zero_and_expansion_discloses_it(self):
        class Stations:
            stations = []
            def ensure_loaded(self): pass
        normal = RoutePolicy('AAA','CCC',Stations())
        self.assertFalse(normal.candidate('BBB'))
        self.assertTrue(normal.notes)
        expanded = RoutePolicy('AAA','CCC',Stations(),allow_large_detour=True)
        self.assertTrue(expanded.candidate('BBB'))
        accepted, info = expanded.evaluate(['AAA','BBB','CCC'],120)
        self.assertTrue(accepted)
        self.assertTrue(info['warnings'])
        self.assertIsNone(info['geographic_km'])

    def test_whole_route_cumulative_distance_and_elapsed_time(self):
        policy = RoutePolicy('BJP','SHH',station_service)
        accepted, _ = policy.evaluate(['BJP','TXP','NKH','SHH'],600)
        self.assertTrue(accepted)
        accepted, _ = policy.evaluate(['BJP','NKH','TXP','SHH'],600)
        self.assertFalse(accepted)
        self.assertFalse(policy.evaluate(['BJP','NKH','SHH'],3000)[0])
        expanded = RoutePolicy('BJP','SHH',station_service,allow_large_detour=True)
        accepted, info = expanded.evaluate(['BJP','CCT','SHH'],2100)
        self.assertTrue(accepted)
        self.assertTrue(info['warnings'])
        self.assertEqual(info['mode'],'expanded')

    def test_manual_on_route_station_does_not_waive_automatic_backtracking(self):
        manual=RoutePolicy('BJP','SHH',station_service,required=['NKH'])
        self.assertTrue(manual.evaluate(['BJP','NKH','SHH'],600)[0])
        self.assertFalse(manual.evaluate(['BJP','NKH','TXP','SHH'],900)[0])
        explicit=RoutePolicy('BJP','SHH',station_service,required=['NKH','TXP'])
        self.assertTrue(explicit.evaluate(['BJP','NKH','TXP','SHH'],900)[0])

    def test_planner_filters_before_price_sort_and_manual_override_preserves_wait(self):
        legs = [leg('BJP','CCT','2026-10-10T08:00','2026-10-10T14:00','G1',100),
                leg('CCT','SHH','2026-10-10T14:15','2026-10-11T10:00','G2',100),
                leg('BJP','NKH','2026-10-10T08:00','2026-10-10T12:00','G3'),
                leg('NKH','SHH','2026-10-10T12:15','2026-10-10T14:00','G4')]
        planner = TransferPlanner(TransferStationService(entries=[station('CCT'),station('NKH')]), Samples(legs),sleep_fn=lambda s:None)
        request = TransferQueryRequest(from_station='BJP',to_station='SHH',train_date='2026-10-10',sort_by='price')
        found = planner.search(request,now=NOW,route_policy=RoutePolicy('BJP','SHH',station_service))
        self.assertEqual([p.legs[0].to_station for p in found.plans],['NKH'])
        request.ordered_via_stations=['CCT']
        found = planner.search(request,now=NOW,route_policy=RoutePolicy('BJP','SHH',station_service,required=['CCT']))
        self.assertEqual(found.plans[0].legs[0].to_station,'CCT')
        self.assertTrue(found.plans[0].route_assessment['warnings'])
        request.min_transfer_minutes=30
        self.assertEqual(planner.search(request,now=NOW,route_policy=RoutePolicy('BJP','SHH',station_service,required=['CCT'])).plans,[])
