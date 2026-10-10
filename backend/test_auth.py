"""扫码登录异常响应回归测试；仅替换铁路网络，不使用真实账号。"""
import json
import unittest
import re
from unittest.mock import Mock

import requests

from app.services.auth_service import auth_service
from app.services.session_manager import UserSession, session_manager


def railway_response(body, status=200, content_type="application/json"):
    result = requests.Response()
    result.status_code = status
    result.encoding = "utf-8"
    result.headers["Content-Type"] = content_type
    result._content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return result


class AuthResponseTests(unittest.TestCase):
    stages = {
        "qr": "获取登录二维码",
        "scan": "查询扫码状态",
        "token": "换取登录凭据",
        "account": "确认账号登录",
    }

    def setUp(self):
        self.sid = "auth-response-test"
        self.user = UserSession(self.sid)
        self.user.qr_uuid = "sample-qr"
        self.user.session.cookies.set("sample-cookie", "sample-cookie-value")
        session_manager._sessions[self.sid] = self.user

    def tearDown(self):
        session_manager.remove(self.sid)

    def invoke(self, stage, result):
        # 每个异常样本都从一张可查询的二维码开始，避免前一个样本影响后一个步骤。
        self.user.qr_uuid = "sample-qr"
        self.user.is_logged_in = False
        before = [railway_response({"result_code": "2"})] if stage in {"token", "account"} else []
        if stage == "account":
            before.append(railway_response({"result_code": 0, "newapptk": "sample-token"}))
        self.user.session.post = Mock(side_effect=before + [result])
        return auth_service.create_qr_code(self.sid) if stage == "qr" else auth_service.check_qr_status(self.sid)

    def assert_failure(self, stage, response, reason):
        result = self.invoke(stage, response)
        self.assertFalse(result.get("success", False))
        self.assertNotEqual(result.get("status"), "SUCCESS")
        self.assertIn(self.stages[stage], result["msg"])
        self.assertIn(reason, result["msg"])
        self.assertNotIn("Expecting value", result["msg"])
        self.assertFalse(self.user.is_logged_in)
        self.assertEqual(self.user.session.cookies.get("sample-cookie"), "sample-cookie-value")
        return result

    def test_empty_response_identifies_the_failing_login_stage(self):
        for stage in self.stages:
            with self.subTest(stage=stage):
                self.assert_failure(stage, railway_response(b""), "空响应")

    def test_html_response_is_not_reported_as_a_json_parser_error(self):
        for stage in self.stages:
            with self.subTest(stage=stage):
                self.assert_failure(stage, railway_response(b"<html>Service unavailable</html>", content_type="text/html"), "网页内容")

    def test_non_json_response_identifies_the_failing_login_stage(self):
        for stage in self.stages:
            with self.subTest(stage=stage):
                self.assert_failure(stage, railway_response(b"not-json", content_type="text/plain"), "无法解析")

    def test_http_error_cannot_be_accepted_as_login_success(self):
        for stage in self.stages:
            with self.subTest(stage=stage):
                body = {"result_code": "0" if stage in {"qr", "scan"} else 0,
                        "uuid": "sample-qr", "image": "sample-image", "newapptk": "sample-token", "username": "测试旅客"}
                self.assert_failure(stage, railway_response(body, status=503), "HTTP 503")

    def test_non_object_json_and_missing_result_code_are_rejected(self):
        for stage in self.stages:
            for body in [[], None, {}, {"result_code": None}]:
                with self.subTest(stage=stage, body=body):
                    self.assert_failure(stage, railway_response(body), "格式")

    def test_success_without_qr_fields_is_rejected(self):
        for missing in ["uuid", "image"]:
            body = {"result_code": "0", "uuid": "sample-qr", "image": "sample-image"}
            body.pop(missing)
            with self.subTest(missing=missing):
                self.assert_failure("qr", railway_response(body), "二维码信息不完整")

    def test_success_without_token_does_not_attempt_account_login(self):
        self.assert_failure("token", railway_response({"result_code": 0}), "登录凭据缺失")
        self.assertEqual(self.user.session.post.call_count, 2)

    def test_success_without_username_does_not_mark_the_session_logged_in(self):
        self.assert_failure("account", railway_response({"result_code": 0}), "账号信息缺失")

    def test_request_failure_never_exposes_exception_credentials(self):
        for stage in self.stages:
            for error in [requests.Timeout("secret-token-in-exception"), requests.ConnectionError("secret-token-in-exception")]:
                with self.subTest(stage=stage, error=type(error).__name__):
                    with self.assertLogs("app.services.auth_service", level="INFO") as logs:
                        result = self.invoke(stage, error)
                    self.assertIn(self.stages[stage], result["msg"])
                    self.assertNotIn("secret-token-in-exception", result["msg"] + "".join(logs.output))
                    self.assertFalse(self.user.is_logged_in)

    def test_diagnostic_logs_contain_response_metadata_without_secrets(self):
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            result = self.invoke("account", railway_response(b"<html>secret-response-content</html>", content_type="text/html"))
        output = "".join(logs.output)
        self.assertIn("确认账号登录", output)
        self.assertIn("200", output)
        self.assertIn("text/html", output)
        for secret in ["secret-response-content", "sample-token", "sample-cookie-value", "sample-qr"]:
            self.assertNotIn(secret, output + result["msg"])

    def test_valid_qr_response_still_returns_the_image(self):
        result = self.invoke("qr", railway_response({"result_code": "0", "uuid": "sample-qr", "image": "sample-image"}))
        self.assertTrue(result["success"])
        self.assertEqual(result["image"], "data:image/png;base64,sample-image")

    def test_valid_account_response_finishes_login_once(self):
        result = self.invoke("account", railway_response({"result_code": 0, "username": "测试旅客"}))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["username"], "测试旅客")
        self.assertTrue(self.user.is_logged_in)
        self.assertEqual(auth_service.check_qr_status(self.sid)["status"], "SUCCESS")
        self.assertEqual(self.user.session.post.call_count, 3)

    def test_token_exchange_sends_origin_and_completes_confirmed_qr_login(self):
        class RailwayGateway(requests.adapters.BaseAdapter):
            def send(self, request, **kwargs):
                if request.url.endswith("/checkqr"):
                    response = railway_response({"result_code": "2"})
                elif request.url.endswith("/auth/uamtk"):
                    # 实测：同一个接口缺少 Origin 会跳转到官方 HTML 错误页。
                    if request.headers.get("Origin") != "https://kyfw.12306.cn":
                        response = railway_response(b"<html>Railway error page</html>", content_type="text/html")
                        response.url = "https://www.12306.cn/mormhweb/logFiles/error.html"
                    else:
                        response = railway_response({"result_code": 0, "newapptk": "sample-token"})
                else:
                    response = railway_response({"result_code": 0, "username": "测试旅客"})
                response.request = request
                response.url = response.url or request.url
                return response

            def close(self):
                pass

        self.user.session.mount("https://", RailwayGateway())
        result = auth_service.check_qr_status(self.sid)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(self.user.is_logged_in)

    def test_login_steps_share_a_trace_without_logging_the_client_session_id(self):
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            self.invoke("qr", railway_response({"result_code": "0", "uuid": "sample-qr", "image": "sample-image"}))
            result = self.invoke("account", railway_response({"result_code": 0, "username": "测试旅客"}))
        output = "\n".join(logs.output)
        traces = re.findall(r'"trace_id": "([a-f0-9]+)"', output)
        self.assertGreaterEqual(len(traces), 8)
        self.assertEqual(len(set(traces)), 1)
        self.assertNotIn(self.sid, output)
        self.assertEqual(result["status"], "SUCCESS")

    def test_failed_token_logs_redirects_and_page_features_without_sensitive_content(self):
        html = (b'<html><title>Access verification secret-title-value</title>'
                b'<script>window.location.href="/otn/resources/login.html?tk=secret-js-token";</script>'
                b'<form action="/otn/passport?token=secret-form-token">captcha</form>'
                b'<input value="secret-body-value"></html>')
        result = railway_response(html, content_type="text/html")
        result.url = "https://kyfw.12306.cn/otn/resources/login.html?tk=secret-url-token"
        redirect = railway_response(b"", status=302)
        redirect.url = "https://kyfw.12306.cn/passport/web/auth/uamtk?token=secret-history-token"
        redirect.headers["Location"] = result.url
        redirect.request = requests.Request("POST", redirect.url, headers={"Cookie": "uamtk=secret-sent-cookie"}).prepare()
        result.history = [redirect]
        result.headers["Set-Cookie"] = "uamtk=secret-set-cookie"
        self.user.session.cookies.set("uamtk", "secret-cookie-value", domain="kyfw.12306.cn", path="/passport")
        self.user.session.cookies.set("RAIL_DEVICEID", "secret-device-id", domain="kyfw.12306.cn", path="/")
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            self.invoke("token", result)
        output = "\n".join(logs.output)
        for expected in ["AUTH_INVALID_RESPONSE", '"redirects"', "302", "verification_hint", "script_redirect",
                         "https://kyfw.12306.cn/otn/resources/login.html", "uamtk", "RAIL_DEVICEID", '"elapsed_ms"', '"body_sha256"', '"sent_cookie_presence"']:
            self.assertIn(expected, output)
        for secret in ["secret-title-value", "secret-js-token", "secret-form-token", "secret-body-value", "secret-url-token",
                       "secret-history-token", "secret-set-cookie", "secret-cookie-value", "secret-device-id", "secret-sent-cookie"]:
            self.assertNotIn(secret, output)

    def test_official_error_redirect_is_identified_even_without_an_http_error_status(self):
        result = railway_response('<html>网络可能存在问题，请您重试一下！</html>'.encode("utf-8"), content_type="text/html")
        result.encoding = "ISO-8859-1"
        result.url = "https://www.12306.cn/mormhweb/logFiles/error.html"
        redirect = railway_response(b"", status=302)
        redirect.url = "https://kyfw.12306.cn/passport/web/auth/uamtk"
        redirect.headers["Location"] = result.url
        result.history = [redirect]
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            self.invoke("token", result)
        output = "\n".join(logs.output)
        self.assertIn("/mormhweb/logFiles/error.html", output)
        self.assertIn("railway_error_page", output)
        self.assertIn("service_error_hint", output)

    def test_network_error_logs_the_failed_request_without_exception_secrets(self):
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            result = self.invoke("token", requests.Timeout("secret-network-details"))
        output = "\n".join(logs.output)
        self.assertIn("AUTH_NETWORK_ERROR", output)
        self.assertIn("/passport/web/auth/uamtk", output)
        self.assertIn('"elapsed_ms"', output)
        self.assertNotIn("secret-network-details", output + result["msg"])

    def test_unknown_response_paths_and_userinfo_are_not_logged(self):
        response = railway_response(b"<html>error</html>", content_type="text/html")
        response.url = "https://user:secret-password@kyfw.12306.cn/secret-path-token?tk=secret-query-token"
        with self.assertLogs("app.services.auth_service", level="INFO") as logs:
            self.invoke("token", response)
        output = "\n".join(logs.output)
        self.assertIn("AUTH_INVALID_RESPONSE", output)
        for secret in ["secret-password", "secret-path-token", "secret-query-token"]:
            self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
