"""
车站数据管理服务: 负责下载、解析 12306 车站字典, 提供拼音/汉字毫秒级检索
"""
import os
import re
import time
import logging
import requests
import urllib3
from typing import List, Dict, Optional
from ..config import settings
from ..models.schemas import StationInfo

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

class StationService:
    def __init__(self):
        self.stations: List[StationInfo] = []
        self.name_to_code: Dict[str, str] = {}
        self.code_to_name: Dict[str, str] = {}
        self.last_load_time: float = 0
        self._data_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        os.makedirs(self._data_cache_dir, exist_ok=True)
        self._cache_file = os.path.join(self._data_cache_dir, "station_name.js")

    def ensure_loaded(self) -> None:
        """确保车站数据已加载至内存"""
        if self.stations and (time.time() - self.last_load_time < settings.STATION_CACHE_HOURS * 3600):
            return
        self.load_stations()

    def load_stations(self) -> None:
        """从本地缓存或 12306 官方下载并解析车站字典"""
        raw_text = ""
        # 1. 尝试从本地缓存读取
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                logger.info(f"Loaded stations raw text from cache: {self._cache_file}")
            except Exception as e:
                logger.warning(f"Failed to read local stations cache: {e}")

        # 2. 若本地无缓存或内容为空，向 12306 发起请求
        if not raw_text or "@" not in raw_text:
            try:
                headers = {"User-Agent": settings.DEFAULT_USER_AGENT}
                res = requests.get(
                    settings.STATION_NAME_URL,
                    headers=headers,
                    verify=False,
                    timeout=settings.REQUEST_TIMEOUT
                )
                if res.status_code == 200:
                    raw_text = res.text
                    with open(self._cache_file, "w", encoding="utf-8") as f:
                        f.write(raw_text)
                    logger.info("Successfully fetched and cached station_name.js from 12306")
            except Exception as e:
                logger.error(f"Error fetching station_name.js: {e}")
                if not raw_text:
                    raise RuntimeError(f"无法初始化车站字典: {e}")

        # 3. 解析文本格式: @shh|上海|SHH|shanghai|sh|2...
        self._parse_station_text(raw_text)

    def _parse_station_text(self, text: str) -> None:
        stations_list: List[StationInfo] = []
        name_to_code: Dict[str, str] = {}
        code_to_name: Dict[str, str] = {}

        items = text.split("@")
        for item in items:
            if not item:
                continue
            parts = item.split("|")
            if len(parts) >= 5:
                name = parts[1].strip()
                telecode = parts[2].strip()
                pinyin = parts[3].strip().lower()
                pinyin_abbr = parts[4].strip().lower()

                info = StationInfo(
                    name=name,
                    telecode=telecode,
                    pinyin=pinyin,
                    pinyin_abbr=pinyin_abbr
                )
                stations_list.append(info)
                name_to_code[name] = telecode
                code_to_name[telecode] = name

        self.stations = stations_list
        self.name_to_code = name_to_code
        self.code_to_name = code_to_name
        self.last_load_time = time.time()
        logger.info(f"Loaded {len(self.stations)} stations successfully.")

    def search(self, keyword: str, limit: int = 20) -> List[StationInfo]:
        """按汉字、全拼、拼音简拼多维度检索"""
        self.ensure_loaded()
        if not keyword:
            # 默认返回主要城市热门站
            popular = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆", "西安"]
            res = [s for s in self.stations if s.name in popular]
            return res[:limit]

        kw = keyword.strip().lower()
        exact_matches = []
        prefix_matches = []
        fuzzy_matches = []

        for s in self.stations:
            if s.name == kw or s.pinyin == kw or s.pinyin_abbr == kw:
                exact_matches.append(s)
            elif s.name.startswith(kw) or s.pinyin.startswith(kw) or s.pinyin_abbr.startswith(kw):
                prefix_matches.append(s)
            elif kw in s.name or kw in s.pinyin or kw in s.pinyin_abbr:
                fuzzy_matches.append(s)

        combined = exact_matches + prefix_matches + fuzzy_matches
        # 去重保持顺序
        seen = set()
        result = []
        for item in combined:
            if item.telecode not in seen:
                seen.add(item.telecode)
                result.append(item)
            if len(result) >= limit:
                break
        return result

    def get_code(self, name: str) -> Optional[str]:
        self.ensure_loaded()
        return self.name_to_code.get(name)

    def get_name(self, code: str) -> Optional[str]:
        self.ensure_loaded()
        return self.code_to_name.get(code, code)

station_service = StationService()
