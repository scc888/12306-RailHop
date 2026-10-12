"""
12306 逆向网络客户端: 负责免认证会话维护、动态路由自适应、余票解析与经停时刻表查询
"""
import time
import re
import logging
import requests
import urllib3
from typing import List, Dict, Optional, Tuple
from ..config import settings
from ..models.schemas import TrainTicketInfo, TrainSeatInfo, TrainStopInfo
from .station_service import station_service

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

class RailwayQueryError(RuntimeError):
    """An upstream failure, distinct from a successful empty ticket query."""

class Ticket12306Client:
    def __init__(self):
        self.session = requests.Session()
        self._setup_session()
        self._cached_c_url: str = "leftTicket/queryG"
        self._stops_cache: Dict[str, Tuple[float, List[TrainStopInfo]]] = {}
        self._initialized: bool = False

    def _setup_session(self) -> None:
        self.session.headers.update({
            "User-Agent": settings.DEFAULT_USER_AGENT,
            "Referer": settings.INIT_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def ensure_init(self, force: bool = False, timeout_seconds: float = None, strict: bool = False) -> None:
        """访问初始化页面获取会话基础 Cookie (若已存在有效 Cookie 则复用)"""
        if self._initialized and not force and "JSESSIONID" in self.session.cookies:
            return
        try:
            response = self.session.get(
                settings.INIT_URL,
                verify=True if strict else False,
                timeout=timeout_seconds or settings.REQUEST_TIMEOUT
            )
            if strict and response.status_code != 200:
                raise RailwayQueryError('铁路查询会话初始化失败')
            self._initialized = True
        except Exception as e:
            if strict:
                raise RailwayQueryError('铁路查询会话初始化失败，请稍后重试') from e
            logger.warning(f"Session init failed: {e}")

    def resolve_c_url(self, train_date: str, from_code: str, to_code: str) -> str:
        """动态探测 12306 当前有效的查询接口路径 (如 leftTicket/queryG)"""
        params = {
            "leftTicketDTO.train_date": train_date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT"
        }
        try:
            res = self.session.get(
                settings.QUERY_PROBE_URL,
                params=params,
                verify=False,
                allow_redirects=False,
                timeout=settings.REQUEST_TIMEOUT
            )
            # 12306 通常以 302 并在响应体中返回 {"c_url":"leftTicket/queryG"}
            if res.text and "c_url" in res.text:
                data = res.json()
                c_url = data.get("c_url")
                if c_url:
                    self._cached_c_url = c_url
                    return c_url
        except Exception as e:
            logger.debug(f"Probe c_url notice: {e}")
        return self._cached_c_url

    def query_tickets(
        self,
        train_date: str,
        from_code: str,
        to_code: str,
        purpose_codes: str = "ADULT"
    ) -> List[TrainTicketInfo]:
        """Legacy callers keep their successful-empty / failure-empty contract."""
        try:
            return self.query_tickets_strict(train_date, from_code, to_code, purpose_codes)
        except RailwayQueryError:
            logger.warning('铁路余票查询未成功')
            return []

    def query_tickets_strict(self, train_date: str, from_code: str, to_code: str,
                             purpose_codes: str = 'ADULT', timeout_seconds: float = None) -> List[TrainTicketInfo]:
        deadline = time.monotonic() + (timeout_seconds or settings.REQUEST_TIMEOUT)

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise RailwayQueryError('铁路余票查询超时，请稍后重试')
            return value

        params = {
            "leftTicketDTO.train_date": train_date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": purpose_codes
        }

        try:
            self.ensure_init(timeout_seconds=remaining(), strict=True)
            target_url = f"{settings.BASE_12306_URL}/{self._cached_c_url}"
            res = self.session.get(
                target_url,
                params=params,
                verify=True,
                allow_redirects=False,
                timeout=remaining()
            )
            # 若返回 302，重新初始化 Cookie 并重新探测 c_url
            if res.status_code == 302:
                self.ensure_init(force=True, timeout_seconds=remaining(), strict=True)
                probe = self.session.get(settings.QUERY_PROBE_URL, params=params, verify=True,
                                         allow_redirects=False, timeout=remaining())
                new_c_url = probe.json().get('c_url', '')
                if not re.fullmatch(r'leftTicket/query[A-Za-z]*', new_c_url):
                    raise RailwayQueryError('铁路查询路径暂不可用，请稍后重试')
                self._cached_c_url = new_c_url
                target_url = f"{settings.BASE_12306_URL}/{new_c_url}"
                res = self.session.get(
                    target_url,
                    params=params,
                    verify=True,
                    allow_redirects=False,
                    timeout=remaining()
                )

            if res.status_code != 200:
                raise RailwayQueryError(f'铁路余票查询返回 HTTP {res.status_code}，请稍后重试')

            res_json = res.json()
            if not isinstance(res_json, dict) or res_json.get('status') is not True:
                raise RailwayQueryError('铁路余票查询暂不可用，请稍后重试')

            data = res_json.get("data", {})
            if not isinstance(data, dict) or not isinstance(data.get('result'), list):
                raise RailwayQueryError('铁路余票查询响应格式异常，请稍后重试')
            raw_results = data['result']
            if any(not isinstance(item, str) or len(item.split('|')) < 35 for item in raw_results):
                raise RailwayQueryError('铁路余票数据不完整，请稍后重试')
            station_map = data.get("map", {})

            return self._parse_ticket_results(raw_results, station_map)

        except RailwayQueryError:
            raise
        except Exception as e:
            raise RailwayQueryError('铁路余票查询失败，请稍后重试') from e

    def _parse_ticket_results(
        self,
        raw_results: List[str],
        station_map: Dict[str, str]
    ) -> List[TrainTicketInfo]:
        """解析 12306 返回的竖线分割车次字符串数组"""
        train_list: List[TrainTicketInfo] = []
        for raw in raw_results:
            parts = raw.split("|")
            if len(parts) < 35:
                continue

            train_no = parts[2]
            train_code = parts[3]
            start_station_code = parts[4]
            end_station_code = parts[5]
            from_station_code = parts[6]
            to_station_code = parts[7]
            start_time = parts[8]
            arrive_time = parts[9]
            duration = parts[10]
            can_buy = (parts[11] == "Y")

            start_name = station_map.get(start_station_code) or station_service.get_name(start_station_code)
            end_name = station_map.get(end_station_code) or station_service.get_name(end_station_code)
            from_name = station_map.get(from_station_code) or station_service.get_name(from_station_code)
            to_name = station_map.get(to_station_code) or station_service.get_name(to_station_code)

            # 解析席别余票 (字段索引对应 12306 官方格式)
            def clean_seat(val: str) -> str:
                v = val.strip() if val else ""
                return v if v else "--"

            swz = clean_seat(parts[32])
            zy = clean_seat(parts[31])
            ze = clean_seat(parts[30])
            gr = clean_seat(parts[21])
            rw = clean_seat(parts[23])
            srrb = clean_seat(parts[33])
            yw = clean_seat(parts[28])
            rz = clean_seat(parts[24])
            yz = clean_seat(parts[29])
            wz = clean_seat(parts[26])

            def has_ticket(val: str) -> bool:
                return val == '有' or (val.isascii() and val.isdigit() and int(val) > 0)

            has_any = can_buy and any(has_ticket(s) for s in [swz, zy, ze, gr, rw, srrb, yw, rz, yz, wz])

            seat_info = TrainSeatInfo(
                swz=swz,
                zy=zy,
                ze=ze,
                gr=gr,
                rw=rw,
                srrb=srrb,
                yw=yw,
                rz=rz,
                yz=yz,
                wz=wz,
                has_any_ticket=has_any
            )

            # 解析票价信息 (来自 parts[39] 的 yp_info_new 编码)
            price_encoded = parts[39] if len(parts) > 39 else ""
            prices = self._parse_price_string(price_encoded)

            train_info = TrainTicketInfo(
                run_date=parts[13] or None,
                train_no=train_no,
                train_code=train_code,
                start_station_name=start_name,
                end_station_name=end_name,
                from_station_name=from_name,
                to_station_name=to_name,
                from_station_telecode=from_station_code,
                to_station_telecode=to_station_code,
                start_time=start_time,
                arrive_time=arrive_time,
                duration=duration,
                can_buy=can_buy,
                seats=seat_info,
                prices=prices
            )
            train_list.append(train_info)

        return train_list

    @staticmethod
    def _parse_price_string(price_str: str) -> Dict[str, str]:
        """
        解析 12306 yp_info_new 中的票价编码
        格式: [席别代号][5位金额(单位0.1元)][4位内部折扣码]
        """
        prices: Dict[str, str] = {}
        if not price_str:
            return prices
        matches = re.findall(r'([A-Za-z0-9])(\d{5})\d{4}', price_str)
        code_map = {
            '9': 'swz',  # 商务座
            'P': 'tz',   # 特等座
            'M': 'zy',   # 一等座
            'O': 'ze',   # 二等座
            '6': 'gr',   # 高级软卧
            '4': 'rw',   # 软卧
            'D': 'srrb', # 动卧
            'F': 'srrb', # 动卧
            '3': 'yw',   # 硬卧
            '2': 'rz',   # 软座
            '1': 'yz',   # 硬座
            'W': 'wz',   # 无座
        }
        for code, price_int in matches:
            seat_key = code_map.get(code)
            if seat_key and seat_key not in prices:
                val = float(price_int) / 10.0
                prices[seat_key] = f"¥{val:.1f}".replace(".0", "")
        if "wz" not in prices:
            if "ze" in prices:
                prices["wz"] = prices["ze"]
            elif "yz" in prices:
                prices["wz"] = prices["yz"]
        return prices

    def query_ticket_price(
        self,
        train_no: str,
        from_station_no: str,
        to_station_no: str,
        seat_types: str,
        train_date: str
    ) -> Dict[str, str]:
        """调用 12306 官方 /otn/leftTicket/queryTicketPrice 接口获取明细票价"""
        self.ensure_init()
        params = {
            "train_no": train_no,
            "from_station_no": from_station_no,
            "to_station_no": to_station_no,
            "seat_types": seat_types,
            "train_date": train_date
        }
        try:
            res = self.session.get(
                f"{settings.BASE_12306_URL}/leftTicket/queryTicketPrice",
                params=params,
                verify=False,
                timeout=settings.REQUEST_TIMEOUT
            )
            if res.status_code == 200:
                data = res.json().get("data", {})
                code_map = {
                    "A9": "swz", "P": "tz", "M": "zy", "O": "ze",
                    "A6": "gr", "A4": "rw", "F": "srrb", "A3": "yw",
                    "A2": "rz", "A1": "yz", "WZ": "wz"
                }
                result = {}
                for k, v in data.items():
                    if k in code_map and isinstance(v, str) and v.startswith("¥"):
                        result[code_map[k]] = v
                return result
        except Exception as e:
            logger.warning(f"Error querying ticket price API: {e}")
        return {}


    def query_train_stops(
        self,
        train_no: str,
        from_code: str,
        to_code: str,
        depart_date: str
    ) -> List[TrainStopInfo]:
        """Legacy wrapper; new planners use the strict error contract."""
        try:
            return self.query_train_stops_strict(train_no, from_code, to_code, depart_date)
        except RailwayQueryError:
            logger.warning('铁路时刻表查询未成功')
            return []

    def query_train_stops_strict(self, train_no: str, from_code: str, to_code: str,
                                 depart_date: str, timeout_seconds: float = None) -> List[TrainStopInfo]:
        cache_key = (train_no, depart_date, from_code, to_code)
        now = time.time()
        if cache_key in self._stops_cache:
            cache_time, cached_stops = self._stops_cache[cache_key]
            if now - cache_time < settings.STOPS_CACHE_HOURS * 3600:
                return cached_stops

        deadline = time.monotonic() + (timeout_seconds or settings.REQUEST_TIMEOUT)

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise RailwayQueryError('铁路时刻表查询超时，请稍后重试')
            return value

        params = {
            "train_no": train_no,
            "from_station_telecode": from_code,
            "to_station_telecode": to_code,
            "depart_date": depart_date
        }
        try:
            self.ensure_init(timeout_seconds=remaining(), strict=True)
            res = self.session.get(
                settings.STOPS_QUERY_URL,
                params=params,
                verify=True,
                timeout=remaining()
            )
            if res.status_code != 200:
                raise RailwayQueryError('铁路时刻表暂不可用，请稍后重试')
            payload = res.json()
            if not isinstance(payload, dict) or payload.get('status') is not True:
                raise RailwayQueryError('铁路时刻表查询未成功，请稍后重试')
            data = payload.get('data', {}).get('data')
            if not isinstance(data, list) or any(not isinstance(item, dict) or
                    not item.get('station_no') or not item.get('station_name') for item in data):
                raise RailwayQueryError('铁路时刻表数据不完整，请稍后重试')
            stops = [TrainStopInfo(station_no=item['station_no'], station_name=item['station_name'],
                arrive_time=item.get('arrive_time', '--'), start_time=item.get('start_time', '--'),
                stopover_time=item.get('stopover_time', '--')) for item in data]
            if stops:
                self._stops_cache[cache_key] = (now, stops)
                if len(self._stops_cache) > 256:
                    del self._stops_cache[next(iter(self._stops_cache))]
            return stops
        except RailwayQueryError:
            raise
        except Exception as e:
            raise RailwayQueryError('铁路时刻表查询失败，请稍后重试') from e

client_12306 = Ticket12306Client()
