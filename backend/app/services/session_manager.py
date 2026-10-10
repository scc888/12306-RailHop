"""
12306 多用户会话管理服务
负责隔离不同客户端的 requests.Session、Cookie 与登录状态
"""
import time
import uuid
import logging
import threading
from typing import Dict, Optional, Any
import requests
import urllib3
from ..config import settings

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

class UserSession:
    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.session: requests.Session = requests.Session()
        self.is_logged_in: bool = False
        self.username: Optional[str] = None
        self.user_name_real: Optional[str] = None
        self.qr_uuid: Optional[str] = None
        self.created_at: float = time.time()
        self.last_active: float = time.time()
        self.extra_data: Dict[str, Any] = {}
        # 同一账号的下单表单共享铁路会话，必须串行处理，避免令牌互相覆盖。
        self.operation_lock = threading.RLock()
        self._setup_session()

    def _setup_session(self) -> None:
        self.session.headers.update({
            "User-Agent": settings.DEFAULT_USER_AGENT,
            "Referer": "https://kyfw.12306.cn/otn/resources/login.html",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def touch(self) -> None:
        self.last_active = time.time()

    def clear_auth(self) -> None:
        with self.operation_lock:
            self.is_logged_in = False
            self.username = None
            self.user_name_real = None
            self.qr_uuid = None
            self.extra_data.clear()
            self.session.cookies.clear()


class SessionManager:
    def __init__(self, ttl_seconds: int = 7200):
        self._sessions: Dict[str, UserSession] = {}
        self._ttl_seconds: int = ttl_seconds
        self._lock = threading.RLock()

    def get_or_create(self, session_id: Optional[str] = None) -> UserSession:
        with self._lock:
            self.cleanup_expired()
            if not session_id or session_id not in self._sessions:
                new_id = session_id or str(uuid.uuid4())
                user_session = UserSession(new_id)
                self._sessions[new_id] = user_session
                logger.info(f"Created new session: {new_id}")
                return user_session

            user_session = self._sessions[session_id]
            user_session.touch()
            return user_session

    def get(self, session_id: str) -> Optional[UserSession]:
        with self._lock:
            self.cleanup_expired()
            user_session = self._sessions.get(session_id)
            if user_session:
                user_session.touch()
            return user_session

    def remove(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Removed session: {session_id}")

    def cleanup_expired(self) -> None:
        with self._lock:
            now = time.time()
            expired_ids = [
                sid for sid, s in self._sessions.items()
                if now - s.last_active > self._ttl_seconds
            ]
            for sid in expired_ids:
                del self._sessions[sid]
                logger.info(f"Cleaned up expired session: {sid}")

session_manager = SessionManager()
