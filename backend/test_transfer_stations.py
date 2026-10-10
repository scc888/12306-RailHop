import unittest
from pydantic import ValidationError
from app.models.transfer_schemas import TransferQueryRequest, TransferStation
from app.services.transfer_station_service import TransferStationService


class StationTests(unittest.TestCase):
    def test_request_defaults_and_invalid_inputs(self):
        base = dict(from_station='SHH', to_station='BJP', train_date='2026-10-11')
        request = TransferQueryRequest(**base)
        self.assertEqual((request.transfer_count, request.min_transfer_minutes, request.allowed_seats), (1, 15, ['ze', 'zy']))
        for change in [dict(transfer_count=0), dict(transfer_count=4), dict(min_transfer_minutes=14),
                       dict(allowed_seats=[]), dict(allowed_seats=['bad']),
                       dict(ordered_via_stations=['NJH', 'NJH']), dict(ordered_via_stations=['NJH', 'HGH']),
                       dict(to_station='SHH')]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                TransferQueryRequest(**(base | change))

    def test_catalog_search_and_required_station(self):
        service = TransferStationService()
        self.assertGreaterEqual(len(service.search('', 100)), 12)
        self.assertEqual(service.search('nanjingnan')[0].station_code, 'NKH')
        self.assertEqual(service.search('njn')[0].station_name, '南京南')
        self.assertIn('NKH', [x.station_code for x in service.candidates(['NKH'], 1)])
        with self.assertRaises(ValueError):
            service.validate_via(['BAD'])

    def test_unknown_or_unresolved_conditions_not_recommended(self):
        common = dict(station_name='测试站', station_code='AAA', pinyin='ceshi', pinyin_abbr='cs',
                      source_url='https://www.12306.cn/', source_published_at='2026-01-01', verified_at='2026-10-10')
        entries = [TransferStation(**common, convenient_transfer_confirmed=False),
                   TransferStation(**(common | dict(station_code='BBB')), applicable_conditions='仅部分站场', conditions_supported=False)]
        service = TransferStationService(entries=entries)
        self.assertEqual(service.search(''), [])
        for code in ['AAA', 'BBB']:
            with self.assertRaises(ValueError):
                service.validate_via([code])


if __name__ == '__main__':
    unittest.main()
