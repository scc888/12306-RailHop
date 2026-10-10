"""
12306 查票工具配置文件
"""
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "12306-RailHop (铁跃) 智能查票与跨站规划服务"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 12306 接口地址配置
    BASE_12306_URL: str = "https://kyfw.12306.cn/otn"
    STATION_NAME_URL: str = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
    INIT_URL: str = "https://kyfw.12306.cn/otn/leftTicket/init"
    QUERY_PROBE_URL: str = "https://kyfw.12306.cn/otn/leftTicket/query"
    STOPS_QUERY_URL: str = "https://kyfw.12306.cn/otn/czxx/queryByTrainNo"
    
    # 网络超时与缓存
    REQUEST_TIMEOUT: int = 10
    STATION_CACHE_HOURS: int = 24
    STOPS_CACHE_HOURS: int = 12
    TRANSFER_MAX_CANDIDATES: int = 12
    TRANSFER_MAX_QUERIES: int = 120
    TRANSFER_MAX_SECONDS: float = 45
    TRANSFER_MAX_STATES: int = 2000
    TRANSFER_MAX_RESULTS: int = 50
    TRANSFER_HORIZON_HOURS: int = 72
    TRANSFER_REQUEST_INTERVAL: float = 0.2
    TRANSFER_QUERY_TIMEOUT: float = 5
    TRANSFER_CACHE_SECONDS: float = 30
    TRANSFER_CACHE_SIZE: int = 512

    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

settings = Settings()
