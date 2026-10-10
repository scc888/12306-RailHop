"""Source-backed station catalog, separate from the 12306 station-name dictionary."""
import json
from pathlib import Path
from ..models.transfer_schemas import TransferStation


class TransferStationService:
    def __init__(self, entries=None):
        if entries is None:
            path = Path(__file__).resolve().parents[2] / 'data' / 'transfer_stations.json'
            entries = [TransferStation(**item) for item in json.loads(path.read_text(encoding='utf-8'))]
        self.entries = {item.station_code: item for item in entries}

    def _available(self):
        return sorted((s for s in self.entries.values() if s.convenient_transfer_confirmed
                       and s.conditions_supported and s.source_url), key=lambda s: (s.priority, s.station_code))

    def search(self, keyword: str = '', limit: int = 20) -> list[TransferStation]:
        word = keyword.strip().lower()
        return [s for s in self._available() if not word or any(word in value.lower() for value in
                (s.station_name, s.station_code, s.pinyin, s.pinyin_abbr))][:limit]

    def validate_via(self, codes: list[str]) -> list[TransferStation]:
        available = {s.station_code: s for s in self._available()}
        for code in codes:
            if code not in available:
                raise ValueError(f'{code} 尚无适用的便捷换乘资料，请选择已收录车站')
        return [available[code] for code in codes]

    def candidates(self, required_codes: list[str], limit: int) -> list[TransferStation]:
        required = self.validate_via(required_codes)
        return (required + [s for s in self._available() if s.station_code not in required_codes])[:max(limit, len(required))]
