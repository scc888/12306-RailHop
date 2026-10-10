"""
12306 用户认证服务 (官方 App 扫码登录与会话维持)
"""
import logging
import json
import time
import uuid as uuid_module
from typing import Dict, Any
import requests
from .session_manager import UserSession, session_manager
from .auth_diagnostics import cookie_summary, page_summary, safe_endpoint, sent_cookie_presence

logger = logging.getLogger(__name__)


class AuthResponseError(RuntimeError):
    """登录接口未返回可确认的结果，错误信息不包含铁路凭据或响应正文。"""


class AuthService:
    def _post_login(self, user: UserSession, url: str, payload: dict, referer: str, stage: str) -> dict:
        """提交一个登录步骤，只接受成功的HTTP响应和包含结果码的JSON对象。

        日志关联同一次扫码的各个步骤，并记录重定向和页面特征；不记录凭据和正文。
        异常响应不能证明登录成功，也不能据此清除已有登录凭据。
        """
        trace_id = user.extra_data.setdefault("auth_trace_id", uuid_module.uuid4().hex[:12])
        # 官网同源 POST 会携带 Origin；缺失时凭据交换接口会跳转到 HTML 错误页。
        headers = {"Referer": referer, "Origin": "https://kyfw.12306.cn"}
        context = {"trace_id": trace_id, "request_id": uuid_module.uuid4().hex[:12], "step": stage,
                   "method": "POST", "url": safe_endpoint(url), "referer": safe_endpoint(referer),
                   "origin": headers["Origin"],
                   "timeout_seconds": 10, "cookies_before": cookie_summary(user.session.cookies),
                   "parameter_names": [key for key in ("appid", "uuid", "tk") if key in payload],
                   "proxy_enabled": bool(user.session.proxies) or
                   bool(user.session.trust_env and requests.utils.get_environ_proxies(url))}
        logger.info("AUTH_REQUEST %s", json.dumps(context, ensure_ascii=False))
        started = time.monotonic()
        try:
            res = user.session.post(url, data=payload, headers=headers, verify=True, timeout=10)
        except requests.RequestException as exc:
            logger.error("AUTH_NETWORK_ERROR %s", json.dumps({**context, "exception_type": type(exc).__name__,
                         "elapsed_ms": round((time.monotonic() - started) * 1000)}, ensure_ascii=False))
            reason = "连接12306超时" if isinstance(exc, requests.Timeout) else "暂时无法连接12306"
            raise AuthResponseError(f"{stage}失败：{reason}，请稍后刷新二维码重试") from None

        content_type = res.headers.get("Content-Type", "未知").split(";", 1)[0][:80]
        original_request = (res.history[0] if res.history else res).request
        response_context = {**context, "http_status": res.status_code, "content_type": content_type,
                            "body_bytes": len(res.content), "elapsed_ms": round((time.monotonic() - started) * 1000),
                            "final_url": safe_endpoint(res.url or url), "final_method": getattr(res.request, "method", None),
                            "cookies_after": cookie_summary(user.session.cookies),
                            "sent_cookie_presence": sent_cookie_presence(original_request),
                            "response_cookies": cookie_summary(res.cookies),
                            "redirects": [{"status": h.status_code, "url": safe_endpoint(h.url or url),
                                           "location": safe_endpoint(requests.compat.urljoin(h.url or url, h.headers.get("Location", "")))}
                                          for h in res.history]}
        logger.info("AUTH_RESPONSE %s", json.dumps(response_context, ensure_ascii=False))

        def reject(message, reason):
            # 页面仅按固定关键词分类；页面里的姓名、令牌、隐藏表单等内容不会进入日志。
            logger.error("AUTH_INVALID_RESPONSE %s", json.dumps({**response_context, "reason": reason,
                         **page_summary(res)}, ensure_ascii=False))
            return AuthResponseError(message)

        if not 200 <= res.status_code < 300:
            raise reject(f"{stage}失败：12306返回HTTP {res.status_code}，请稍后刷新二维码重试", "http_error")
        if not res.content.strip():
            raise reject(f"{stage}失败：12306返回空响应（HTTP {res.status_code}），请稍后刷新二维码重试", "empty_body")
        try:
            body = res.json()
        except ValueError:
            # 有些网页错误页也返回HTTP 200，不能把它们当成有效的扫码授权结果。
            prefix = res.content.lstrip()[:32].lower()
            reason = "网页内容" if content_type == "text/html" or prefix.startswith((b"<html", b"<!doctype")) else "无法解析的数据"
            raise reject(f"{stage}失败：12306返回{reason}（HTTP {res.status_code}），请稍后刷新二维码重试", "invalid_json") from None
        if not isinstance(body, dict) or type(body.get("result_code")) not in {str, int}:
            raise reject(f"{stage}失败：12306返回的数据格式不正确，请稍后刷新二维码重试", "invalid_structure")
        code = body["result_code"]
        logger.info("AUTH_RESULT %s", json.dumps({"trace_id": trace_id, "request_id": context["request_id"],
                    "step": stage, "result_code": code if str(code).isdigit() else "[非数字结果码]",
                    "present_fields": {key: bool(body.get(key)) for key in ("uuid", "image", "newapptk", "apptk", "username")}}, ensure_ascii=False))
        return body

    def create_qr_code(self, session_id: str) -> Dict[str, Any]:
        """
        向 12306 申请二维码
        """
        user_sess = session_manager.get_or_create(session_id)
        user_sess.extra_data["auth_trace_id"] = uuid_module.uuid4().hex[:12]
        url = "https://kyfw.12306.cn/passport/web/create-qr64"
        payload = {"appid": "otn"}
        user_sess.qr_uuid = None
        try:
            data = self._post_login(user_sess, url, payload,
                                    "https://kyfw.12306.cn/otn/resources/login.html", "获取登录二维码")
            if data.get("result_code") == "0":
                uuid = data.get("uuid")
                image = data.get("image")
                if not isinstance(uuid, str) or not uuid.strip() or not isinstance(image, str) or not image.strip():
                    raise AuthResponseError("获取登录二维码失败：12306返回的二维码信息不完整，请刷新二维码重试")
                user_sess.qr_uuid = uuid
                return {
                    "success": True,
                    "uuid": uuid,
                    "image": f"data:image/png;base64,{image}",
                    "msg": "二维码获取成功"
                }
            else:
                return {
                    "success": False,
                    "msg": "获取登录二维码失败：" + (data.get("result_message") or "12306未允许本次请求，请稍后重试")
                }
        except AuthResponseError as e:
            logger.warning("扫码登录未完成，原因=%s", e)
            return {"success": False, "msg": str(e)}
        except Exception as e:
            logger.error("获取登录二维码发生异常，异常类型=%s", type(e).__name__)
            return {"success": False, "msg": "获取登录二维码失败：暂时无法处理12306响应，请稍后重试"}

    def check_qr_status(self, session_id: str) -> Dict[str, Any]:
        """串行核验扫码结果，成功换取凭据后不再重复使用二维码授权。"""
        user = session_manager.get_or_create(session_id)
        with user.operation_lock:
            if user.is_logged_in:
                return {"status": "SUCCESS", "username": user.username, "msg": "登录成功"}
            return self._check_qr_status(session_id)

    def _check_qr_status(self, session_id: str) -> Dict[str, Any]:
        """
        轮询二维码状态:
        0: 等待扫码 (WAITING)
        1: 已扫码待确认 (SCANNED)
        2: 扫码成功已授权 (SUCCESS)
        3: 二维码过期 (EXPIRED)
        """
        user_sess = session_manager.get_or_create(session_id)
        uuid = user_sess.qr_uuid
        if not uuid:
            return {
                "status": "EXPIRED",
                "msg": "二维码已失效，请重新刷新"
            }

        url = "https://kyfw.12306.cn/passport/web/checkqr"
        payload = {"uuid": uuid, "appid": "otn"}
        try:
            data = self._post_login(user_sess, url, payload,
                                    "https://kyfw.12306.cn/otn/resources/login.html", "查询扫码状态")
            result_code = str(data.get("result_code"))

            if result_code == "0":
                return {
                    "status": "WAITING",
                    "msg": "等待手机 12306 App 扫码"
                }
            elif result_code == "1":
                return {
                    "status": "SCANNED",
                    "msg": "已扫码，请在手机端点击确认登录"
                }
            elif result_code == "2":
                # 扫码成功，开始换取令牌
                auth_res = self._exchange_tokens(user_sess)
                if auth_res.get("success"):
                    return {
                        "status": "SUCCESS",
                        "username": user_sess.username or "铁路用户",
                        "msg": "登录成功"
                    }
                else:
                    return {
                        "status": "ERROR",
                        "msg": auth_res.get("msg", "授权凭据置换失败")
                    }
            elif result_code == "3":
                return {
                    "status": "EXPIRED",
                    "msg": "二维码已过期，请刷新"
                }
            else:
                return {
                    "status": "UNKNOWN",
                    "msg": data.get("result_message", "未知状态")
                }
        except AuthResponseError as e:
            logger.warning("扫码登录未完成，原因=%s", e)
            return {"status": "ERROR", "msg": str(e)}
        except Exception as e:
            logger.error("查询扫码状态发生异常，异常类型=%s", type(e).__name__)
            return {"status": "ERROR", "msg": "查询扫码状态失败：暂时无法处理12306响应，请刷新二维码重试"}

    def _exchange_tokens(self, user_sess: UserSession) -> Dict[str, Any]:
        """换取 uamtk 与 apptk，完成最终登录并获取用户名"""
        stage = "换取登录凭据"
        try:
            # 1. 验证 uamtk
            uamtk_url = "https://kyfw.12306.cn/passport/web/auth/uamtk"
            data1 = self._post_login(user_sess, uamtk_url, {"appid": "otn"},
                                     "https://kyfw.12306.cn/otn/passport?display=both", stage)
            if data1.get("result_code") != 0:
                logger.warning("12306拒绝换取登录凭据")
                return {"success": False, "msg": stage + "失败：" + (data1.get("result_message") or "12306未允许本次授权，请重新扫码")}

            newapptk = data1.get("newapptk")
            if not isinstance(newapptk, str) or not newapptk.strip():
                raise AuthResponseError("换取登录凭据失败：12306返回的登录凭据缺失，请重新扫码")

            # 2. 换取 client 登录态
            stage = "确认账号登录"
            client_url = "https://kyfw.12306.cn/otn/uamauthclient"
            data2 = self._post_login(user_sess, client_url, {"tk": newapptk},
                                     "https://kyfw.12306.cn/otn/passport?display=both", stage)
            if data2.get("result_code") == 0:
                username = data2.get("username", "")
                if not isinstance(username, str) or not username.strip():
                    raise AuthResponseError("确认账号登录失败：12306返回的账号信息缺失，请重新扫码")
                user_sess.is_logged_in = True
                user_sess.username = username
                user_sess.user_name_real = username
                logger.info("扫码登录成功")
                return {"success": True, "username": username}
            else:
                return {"success": False, "msg": stage + "失败：" + (data2.get("result_message") or "12306未确认账号登录，请重新扫码")}

        except AuthResponseError as e:
            logger.warning("扫码登录未完成，原因=%s", e)
            return {"success": False, "msg": str(e)}
        except Exception as e:
            logger.error("处理12306登录授权发生异常，步骤=%s，异常类型=%s", stage, type(e).__name__)
            return {"success": False, "msg": stage + "失败：暂时无法处理12306响应，请重新扫码"}

    def check_user_status(self, session_id: str) -> Dict[str, Any]:
        """检查用户会话是否仍然有效"""
        user_sess = session_manager.get(session_id)
        if not user_sess or not user_sess.is_logged_in:
            return {"logged_in": False, "username": None}

        # 网络失败不能证明凭据失效；只有官方明确返回未登录才清除凭据。
        try:
            url = "https://kyfw.12306.cn/otn/login/checkUser"
            res = user_sess.session.post(
                url,
                data={"_json_att": ""},
                headers={"Referer": "https://kyfw.12306.cn/otn/leftTicket/init"},
                verify=True,
                timeout=8
            )
            res.raise_for_status()
            body = res.json()
            data = body.get("data", {})
            if body.get("status") is not True or type(data.get("flag")) is not bool:
                raise RuntimeError("12306 未返回有效的登录状态")
            if data["flag"] is True:
                return {"logged_in": True, "username": user_sess.username or "铁路用户"}
        except Exception as e:
            logger.warning("核验登录状态失败，保留当前登录凭据", exc_info=e)
            raise RuntimeError("暂时无法核验12306登录状态，请稍后重试") from e

        user_sess.clear_auth()
        return {"logged_in": False, "username": None}

    def logout(self, session_id: str) -> bool:
        """用户登出"""
        user_sess = session_manager.get(session_id)
        if not user_sess:
            return True
        try:
            url = "https://kyfw.12306.cn/otn/login/loginOut"
            user_sess.session.post(url, verify=True, timeout=5)
        except Exception as e:
            logger.warning("Logout notice", exc_info=e)
        finally:
            user_sess.clear_auth()
        return True

auth_service = AuthService()
