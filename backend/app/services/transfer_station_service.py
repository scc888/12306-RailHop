"""Source-backed station catalog, separate from the 12306 station-name dictionary."""
import json
from pathlib import Path
from ..models.transfer_schemas import TransferStation
from .station_service import station_service


class TransferStationService:
    def __init__(self, entries=None, directory=None):
        self.directory = directory or station_service
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
        return [self.station(code) for code in codes]

    def station(self, code: str) -> TransferStation:
        """Resolve identity independently of whether convenience has been verified."""
        reference = self.entries.get(code)
        if reference and reference.convenient_transfer_confirmed and reference.conditions_supported and reference.source_url:
            return reference
        self.directory.ensure_loaded()
        identity = next((s for s in self.directory.stations if s.telecode == code), None)
        if identity is None:
            raise ValueError(f'无法识别中转站 {code}，请从车站字典选择')
        return TransferStation(station_name=identity.name, station_code=code,
            pinyin=identity.pinyin, pinyin_abbr=identity.pinyin_abbr,
            convenient_transfer_confirmed=False,
            applicable_conditions='便捷换乘状态未核实，可能需要出站重新安检进站；请核对车站开放时段与检票截止时间。')

    def candidates(self, required_codes: list[str], limit: int) -> list[TransferStation]:
        required = self.validate_via(required_codes)
        return (required + [s for s in self._available() if s.station_code not in required_codes])[:max(limit, len(required))]
