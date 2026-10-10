"""登录诊断只保留流程和响应特征，不保存可用于登录或识别旅客的内容。"""
import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit


AUTH_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "auth.log"
SAFE_PATHS = {
    "/", "/passport/web/create-qr64", "/passport/web/checkqr", "/passport/web/auth/uamtk",
    "/passport/web/auth/uamtk-static", "/passport/web/login", "/otn/uamauthclient",
    "/otn/passport", "/otn/resources/login.html", "/otn/login/init", "/otn/login/userLogin",
    "/otn/leftTicket/init", "/error", "/error.html", "/otn/error.html", "/mormhweb/logFiles/error.html",
}
AUTH_COOKIES = ("uamtk", "JSESSIONID", "_passport_session", "_passport_ct", "_passport_did",
                "RAIL_DEVICEID", "RAIL_EXPIRATION", "tk")


def configure_auth_logging():
    """将登录日志另存到有大小上限的UTF-8文件，重复初始化不会重复写入。"""
    auth_logger = logging.getLogger("app.services.auth_service")
    auth_logger.setLevel(logging.INFO)
    if any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == AUTH_LOG_PATH for h in auth_logger.handlers):
        return
    AUTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(AUTH_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    auth_logger.addHandler(handler)


def safe_endpoint(url):
    """只展示已知铁路页面路径；去掉账号口令、查询参数和可能包含令牌的未知路径。"""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return "[非HTTP地址]"
        host = parsed.hostname or ""
        host = host if host == "12306.cn" or host.endswith(".12306.cn") else "[其他主机]"
        path = parsed.path if parsed.path in SAFE_PATHS else "/[其他路径]"
        return f"{parsed.scheme}://{host}{path}"
    except ValueError:
        return "[无效地址]"


def cookie_summary(cookies):
    """仅记录关键登录Cookie是否存在，帮助判断授权前后是否发生变化。"""
    present = {c.name for c in cookies if c.value}
    return {"count": len(cookies), "present": {name: name in present for name in AUTH_COOKIES}}


def sent_cookie_presence(request):
    """从实际发出的请求核对Cookie是否携带，区分“已保存”和“本次已发送”。"""
    if request is None:
        return None
    names = {part.partition("=")[0].strip() for part in request.headers.get("Cookie", "").split(";")}
    return {name: name in names for name in AUTH_COOKIES}


def page_summary(response):
    """用固定特征标签和页面指纹描述异常页，不打印标题、正文、脚本或表单内容。"""
    content = response.content[:65536]
    try:
        # 官方错误页可能没有声明字符集，requests会按西文解码，先识别实际UTF-8内容。
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = response.encoding or "gb18030"
        text = content.decode(encoding, errors="replace")
    lower = text.lower()
    patterns = {
        "login_hint": ("登录", "login", "passport"),
        "verification_hint": ("验证", "captcha", "verification", "wzws", "acw_sc", "challenge"),
        "service_error_hint": ("系统忙", "维护", "网络可能存在问题", "service unavailable", "internal server error", "bad gateway", "forbidden", "not found"),
    }
    features = [name for name, words in patterns.items() if any(word in lower for word in words)]
    if urlsplit(response.url or "").path == "/mormhweb/logFiles/error.html":
        features.append("railway_error_page")
    targets = re.findall(r'''(?:location(?:\.href)?\s*=|location\.(?:replace|assign)\s*\()\s*["']([^"']{1,2048})["']''', text, re.I)
    if targets:
        features.append("script_redirect")
    form_targets = re.findall(r'''<form\b[^>]*\baction\s*=\s*["']([^"']{1,2048})["']''', text, re.I)
    if form_targets:
        features.append("form")
    base = response.url or "https://kyfw.12306.cn/"
    return {"page_features": features,
            "navigation_targets": sorted({safe_endpoint(urljoin(base, t)) for t in targets + form_targets})[:5],
            "body_sha256": hashlib.sha256(response.content).hexdigest()[:16]}
