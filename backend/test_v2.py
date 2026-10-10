"""V2 登录与订单回归测试，外部网络响应由固定样本代替。"""
import unittest
import json
from unittest.mock import Mock, patch

import requests

from app.models.schemas import OrderSubmitParam, PassengerOrderParam
from app.services.auth_service import auth_service
from app.services.order_service import order_service
from app.services.session_manager import UserSession, session_manager


def response(data):
    result = requests.Response()
    result.status_code = 200
    result.encoding = "utf-8"
    result.headers["Content-Type"] = "application/json"
    result._content = json.dumps(data).encode("utf-8")
    return result


def order_param():
    return OrderSubmitParam(
        secret_str="test-secret", train_date="2026-10-10", train_code="G1",
        train_no="test-train", from_station_name="上海", to_station_name="北京",
        from_station_telecode="SHH", to_station_telecode="BJP",
        passengers=[PassengerOrderParam(passenger_name="测试旅客", passenger_id_no="test-id")],
    )


class V2RegressionTests(unittest.TestCase):
    def setUp(self):
        self.sid = "v2-regression-session"
        self.user = UserSession(self.sid)
        self.user.is_logged_in = True
        session_manager._sessions[self.sid] = self.user

    def tearDown(self):
        session_manager._sessions.pop(self.sid, None)

    def test_final_confirmation_failure_is_not_success(self):
        def post(url, **kwargs):
            if url.endswith("/initDc"):
                return Mock(text="var globalRepeatSubmitToken = 'abc123'; 'key_check_isChange': 'key', 'leftTicketStr': 'left', 'train_location': 'loc'")
            if url.endswith("/resultOrderForDcQueue"):
                return response({"status": True, "data": {"submitStatus": False}})
            return response({"status": True, "data": {"flag": True, "submitStatus": True, "count": 0}})
        self.user.session.post = Mock(side_effect=post)
        self.user.session.get = Mock(return_value=response({"status": True, "data": {"orderId": "E-TEST", "waitTime": -1}}))
        result = order_service.submit_ticket_order(self.sid, order_param())
        self.assertFalse(result.success)
        self.assertEqual(result.order_id, "E-TEST")
        self.assertEqual(result.status, "UNKNOWN")

    def test_cancel_business_rejection_is_not_success(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"existError": "Y", "errorMsg": "取消被拒绝"}}))
        ok, msg = order_service.cancel_no_complete_order(self.sid, "E-TEST")
        self.assertFalse(ok)
        self.assertIn("拒绝", msg)

    def test_network_timeout_preserves_login_and_cookies(self):
        self.user.session.cookies.set("test-cookie", "test-value")
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        with self.assertRaises(RuntimeError):
            auth_service.check_user_status(self.sid)
        self.assertTrue(self.user.is_logged_in)
        self.assertEqual(self.user.session.cookies.get("test-cookie"), "test-value")

    def test_explicit_login_expiry_clears_login(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"flag": False}}))
        self.assertFalse(auth_service.check_user_status(self.sid)["logged_in"])
        self.assertFalse(self.user.is_logged_in)

    def test_order_query_failure_is_not_empty_order(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        with self.assertRaises(RuntimeError):
            order_service.query_no_complete_order(self.sid)

    def test_official_nested_passenger_and_train_fields_are_parsed(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"orderDBList": [{
            "sequence_no": "E-TEST", "ticket_total_price_page": "553.00",
            "tickets": [{"passengerDTO": {"passenger_name": "测试旅客"},
                         "stationTrainDTO": {"station_train_code": "G1", "from_station_name": "上海", "to_station_name": "北京", "start_time": "08:00", "arrive_time": "12:00"},
                         "start_train_date_page": "2026-10-10", "coach_name": "05", "seat_name": "08A",
                         "seat_type_name": "二等座", "ticket_type_name": "成人票", "str_ticket_price_page": "553.00"}]
        }]}}))
        order = order_service.query_no_complete_order(self.sid)
        self.assertEqual(order.train_code, "G1")
        self.assertEqual(order.tickets[0].passenger_name, "测试旅客")
        self.assertEqual(order.tickets[0].price, "¥553.00")
        self.assertIsNone(order.countdown_seconds)

    def test_order_final_confirmation_transport_error_is_not_success(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        self.assertFalse(order_service._result_order_for_dc_queue(self.user.session, "test-token", "E-TEST"))

    def test_login_exchange_is_not_repeated_after_success(self):
        self.user.is_logged_in = False
        self.user.qr_uuid = "test-qr"
        self.user.session.post = Mock(side_effect=[response({"result_code": "2"}),
            response({"result_code": 0, "newapptk": "test-token"}), response({"result_code": 0, "username": "测试旅客"})])
        first = auth_service.check_qr_status(self.sid)
        second = auth_service.check_qr_status(self.sid)
        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(second["status"], "SUCCESS")
        self.assertEqual(self.user.session.post.call_count, 3)

    def test_invalid_login_flag_cannot_be_treated_as_expiry(self):
        self.user.session.post = Mock(return_value=response({"status": False, "data": {"flag": "bad"}}))
        with self.assertRaises(RuntimeError):
            auth_service.check_user_status(self.sid)
        self.assertTrue(self.user.is_logged_in)

    def test_single_order_pending_query_confirms_existing_unpaid_order(self):
        self.user.extra_data["pending_order"] = {"repeat_token": "abc", "order_id": "E-TEST"}
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"orderDBList": [{"sequence_no": "E-TEST", "tickets": []}]}}))
        result = order_service.pending_result(self.sid)
        self.assertTrue(result.success)
        self.assertEqual(result.order_id, "E-TEST")
        self.assertNotIn("pending_order", self.user.extra_data)

    def test_single_order_pending_query_never_treats_missing_order_as_success(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"orderDBList": []}}))
        result = order_service.pending_result(self.sid)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
