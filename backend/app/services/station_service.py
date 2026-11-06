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
    PRIORITY_STATION_NAMES = (
        "北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆", "西安",
        "天津", "苏州", "郑州", "长沙", "青岛", "宁波", "东莞", "无锡", "佛山", "合肥",
        "福州", "厦门", "济南", "沈阳", "大连", "昆明", "哈尔滨", "长春", "南宁", "贵阳",
        "石家庄", "太原", "南昌", "兰州", "乌鲁木齐", "海口", "三亚", "呼和浩特", "银川", "西宁",
        "拉萨", "徐州", "温州", "金华", "洛阳", "宜昌", "襄阳", "桂林", "柳州", "赣州",
        "上饶", "九江", "株洲", "衡阳", "怀化", "汕头", "湛江", "珠海", "惠州", "中山",
        "常州", "南通", "扬州", "盐城", "连云港", "淮安", "绍兴", "嘉兴", "湖州", "台州",
        "芜湖", "蚌埠", "安庆", "黄山", "阜阳", "泉州", "漳州", "龙岩", "莆田", "南平",
        "烟台", "潍坊", "威海", "临沂", "济宁", "泰安", "淄博", "日照", "商丘", "新乡",
        "安阳", "南阳", "信阳", "绵阳", "宜宾", "乐山", "泸州", "达州", "南充", "遵义",
        "大理", "丽江", "曲靖", "宝鸡", "汉中", "延安", "榆林", "唐山", "保定", "秦皇岛",
        "邯郸", "大同", "运城", "临汾", "包头", "赤峰", "通辽", "锦州", "丹东", "营口",
        "鞍山", "吉林", "延吉", "齐齐哈尔", "牡丹江", "佳木斯", "大庆", "天水", "张掖", "敦煌",
        "酒泉", "格尔木", "喀什", "伊宁", "吐鲁番", "库尔勒", "香港西九龙",
    )
    _PRIORITY_RANK = {name: idx for idx, name in enumerate(PRIORITY_STATION_NAMES)}

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
                    pinyin_abbr=pinyin_abbr,
                    city_code=(parts[6].strip() or None) if len(parts) > 7 else None,
                    city_name=(parts[7].strip() or None) if len(parts) > 7 else None,
                )
                stations_list.append(info)
                name_to_code[name] = telecode
                code_to_name[telecode] = name

        self.stations = stations_list
        self.name_to_code = name_to_code
        self.code_to_name = code_to_name
        self.last_load_time = time.time()
        logger.info(f"Loaded {len(self.stations)} stations successfully.")

    @classmethod
    def _station_rank(cls, s: StationInfo) -> tuple:
        if s.name in cls._PRIORITY_RANK:
            return (0, cls._PRIORITY_RANK[s.name], len(s.name))
        if s.city_name and s.name == s.city_name:
            return (1, cls._PRIORITY_RANK.get(s.city_name, 9999), len(s.name))
        if s.city_name in cls._PRIORITY_RANK:
            return (2, cls._PRIORITY_RANK[s.city_name], len(s.name))
        return (3, 9999, len(s.name))

    def search(self, keyword: str, limit: int = 20) -> List[StationInfo]:
        """按汉字、全拼、拼音简拼多维度检索"""
        self.ensure_loaded()
        if not keyword:
            # 默认返回主要城市热门站
            popular = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆", "西安"]
            res = [s for s in self.stations if s.name in popular]
            res.sort(key=self._station_rank)
            return res[:limit]

        kw = keyword.strip().lower()
        kw_compact = kw.replace(' ', '')
        kw_stripped = re.sub(r'[站市]$', '', kw_compact) if len(kw_compact) > 1 else kw_compact
        terms = {kw, kw_compact, kw_stripped} - {''}
        name_exact = []
        exact_matches = []
        prefix_matches = []
        fuzzy_matches = []

        for s in self.stations:
            if s.name in terms or s.telecode.lower() in terms:
                name_exact.append(s)
            elif s.pinyin in terms or s.pinyin_abbr in terms or (s.city_name and s.city_name in terms):
                exact_matches.append(s)
            elif any(s.name.startswith(t) or s.pinyin.startswith(t) or s.pinyin_abbr.startswith(t) or (s.city_name or '').startswith(t) for t in terms):
                prefix_matches.append(s)
            elif any(t in s.name or t in s.pinyin or t in s.pinyin_abbr for t in terms):
                fuzzy_matches.append(s)

        name_exact.sort(key=self._station_rank)
        exact_matches.sort(key=self._station_rank)
        prefix_matches.sort(key=self._station_rank)
        combined = name_exact + exact_matches + prefix_matches + fuzzy_matches
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
        if not name:
            return None
        cleaned = name.strip()
        if cleaned in self.name_to_code:
            return self.name_to_code[cleaned]
        if len(cleaned) > 1 and cleaned[-1] in ('站', '市') and cleaned[:-1] in self.name_to_code:
            return self.name_to_code[cleaned[:-1]]
        return None

    def city_stations(self, anchor_code: str) -> List[StationInfo]:
        """Use the official dictionary city ID, never a station-name prefix guess.

        Older dictionary entries without city metadata remain station-only.
        """
        self.ensure_loaded()
        anchor = next((s for s in self.stations if s.telecode == anchor_code), None)
        if anchor is None:
            return []
        if not anchor.city_code:
            return [anchor]
        return [s for s in self.stations if s.city_code == anchor.city_code]

    def get_name(self, code: str) -> Optional[str]:
        self.ensure_loaded()
        return self.code_to_name.get(code, code)

    def station_scope(self, anchor_code: str) -> dict:
        """Expose the official city group with a smaller, editable initial choice.

        Names only inform initial selection; they never establish city membership
        or claim that a station is geographically central.
        """
        choices = self.city_stations(anchor_code)
        anchor = next((s for s in choices if s.telecode == anchor_code), None)
        if anchor is None:
            raise ValueError('无法识别车站，请从站点提示中选择')
        city = anchor.city_name or anchor.name
        aliases = {
            '武汉': {'汉口', '武昌'},
            '北京': {'清河'},
            '深圳': {'福田', '光明城'},
            '重庆': {'沙坪坝'},
            '广州': {'新塘', '庆盛'},
        }.get(city, set())
        defaults = [s.telecode for s in choices if s.telecode == anchor_code
                    or s.name.startswith(city) or s.name in aliases]
        return dict(city_name=city, stations=choices, default_station_codes=defaults)

    def resolve_scope(self, anchor_code: str, scope: str, selected=None) -> set[str]:
        choices = self.city_stations(anchor_code)
        if not choices:
            raise ValueError('无法识别车站，请从站点提示中选择')
        allowed = {s.telecode for s in choices} if scope == 'city' else {anchor_code}
        if selected is None:
            return allowed
        values = set(selected)
        if not values or anchor_code not in values or not values.issubset(allowed):
            raise ValueError('所选车站不属于当前范围，请重新选择出发和到达车站')
        return values

station_service = StationService()
