import unittest
from pydantic import ValidationError
from app.models.transfer_schemas import TransferQueryRequest, TransferStation
from app.services.transfer_station_service import TransferStationService


class StationTests(unittest.TestCase):
    def test_request_defaults_and_invalid_inputs(self):
        base = dict(from_station='SHH', to_station='BJP', train_date='2026-10-11')
        request = TransferQueryRequest(**base)
        self.assertEqual((request.transfer_count, request.min_transfer_minutes, request.allowed_seats, request.train_type), (1, None, ['ze', 'zy','yz','yw','rw'], 'all'))
        self.assertIsNone(TransferQueryRequest(**base, min_transfer_minutes=None).min_transfer_minutes)
        for change in [dict(transfer_count=0), dict(transfer_count=4), dict(min_transfer_minutes=0),
                       dict(min_transfer_minutes=-1), dict(min_transfer_minutes=1441),
                       dict(allowed_seats=[]), dict(allowed_seats=['bad']), dict(train_type='bad'),
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

    def test_unknown_conditions_are_not_advertised_as_convenient_but_dictionary_station_is_allowed(self):
        from app.services.station_service import StationService
        common = dict(station_name='测试站', station_code='AAA', pinyin='ceshi', pinyin_abbr='cs',
                      source_url='https://www.12306.cn/', source_published_at='2026-01-01', verified_at='2026-10-10')
        entries = [TransferStation(**common, convenient_transfer_confirmed=False),
                   TransferStation(**(common | dict(station_code='BBB')), applicable_conditions='仅部分站场', conditions_supported=False)]
        directory = StationService()
        directory._parse_station_text('@a|甲|AAA|jia|j|0|a|甲城@b|乙|BBB|yi|y|0|b|乙城')
        service = TransferStationService(entries=entries, directory=directory)
        self.assertEqual(service.search(''), [])
        for code in ['AAA', 'BBB']:
            station = service.validate_via([code])[0]
            self.assertFalse(station.convenient_transfer_confirmed)
            self.assertIsNone(station.source_url)

    def test_official_time_values_and_separate_provenance(self):
        service = TransferStationService()
        for code, minutes in [('NKH',15),('AOH',15),('SHH',30),('ZAF',60)]:
            with self.subTest(code=code):
                station=service.validate_via([code])[0]
                self.assertEqual(station.reference_min_minutes,minutes)
                self.assertIn('12306.cn',station.reference_time_source_url)
                self.assertEqual(station.reference_time_checked_at.isoformat(),'2026-10-10')


if __name__ == '__main__':
    unittest.main()
