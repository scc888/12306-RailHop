"""方案购票的状态与外部接口合同测试，不创建真实订单。"""
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import SmartPlan, PlanSegment, TrainStopInfo, TrainSeatInfo
from app.services.smart_planner import smart_planner
from app.services.session_manager import session_manager, UserSession
from test_v2 import response
import requests


class BookingRoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = UserSession("booking-test-session")
        self.user.is_logged_in = True
        session_manager._sessions[self.user.session_id] = self.user
        self.headers = {"X-Session-Id": self.user.session_id}

    def tearDown(self):
        session_manager._sessions.pop(self.user.session_id, None)

    def test_payment_entry_checks_order_ownership(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"orderDBList": []}}))
        res = self.client.post("/api/orders/E-OTHER/payment", headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_missing_unpaid_order_does_not_prove_payment(self):
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"orderDBList": [], "OrderDTODataList": [], "order_total_number": 0}}))
        res = self.client.get("/api/orders/E-TEST/status?train_date=2026-10-10", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["status"], "UNKNOWN")

    def test_no_plan_is_rejected_before_order_submission(self):
        res = self.client.post("/api/bookings", headers=self.headers, json={"plan_id": "missing", "passengers": [{"passenger_name": "测试", "passenger_id_no": "test-id"}]})
        self.assertEqual(res.status_code, 400)

    def test_booking_cannot_be_read_from_another_session(self):
        res = self.client.get("/api/bookings/not-owned", headers=self.headers)
        self.assertEqual(res.status_code, 404)

    def test_auth_network_error_returns_retryable_502(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        res = self.client.get("/api/auth/status", headers=self.headers)
        self.assertEqual(res.status_code, 502)
        self.assertTrue(self.user.is_logged_in)

    def test_passenger_network_error_returns_502_instead_of_empty_list(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        res = self.client.get("/api/passengers", headers=self.headers)
        self.assertEqual(res.status_code, 502)

    def test_unpaid_network_error_returns_retryable_502(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("test timeout"))
        res = self.client.get("/api/orders/unpaid", headers=self.headers)
        self.assertEqual(res.status_code, 502)

    def test_direct_purchase_rejects_passenger_outside_current_account(self):
        from test_v2 import order_param
        from app.services.order_service import order_service
        with patch("app.services.booking_service.passenger_service.get_passengers", return_value=[]), patch.object(order_service, "submit_ticket_order") as submit:
            res = self.client.post("/api/orders/submit", headers=self.headers, json=order_param().model_dump())
        self.assertEqual(res.status_code, 400)
        submit.assert_not_called()

    def test_direct_purchase_cannot_interrupt_active_plan(self):
        from test_v2 import order_param
        self.user.extra_data["booking"] = {"status": "WAITING_PAYMENT"}
        res = self.client.post("/api/orders/submit", headers=self.headers, json=order_param().model_dump())
        self.assertEqual(res.status_code, 400)


class PlanDatesTests(unittest.TestCase):
    def test_departure_after_midnight_uses_next_day(self):
        stops = [
            TrainStopInfo(station_no="01", station_name="上海", arrive_time="----", start_time="23:00", stopover_time="--"),
            TrainStopInfo(station_no="02", station_name="南京", arrive_time="23:55", start_time="00:05", stopover_time="10"),
            TrainStopInfo(station_no="03", station_name="北京", arrive_time="02:00", start_time="----", stopover_time="--"),
        ]
        ticket = Mock(train_code="G1", seats=TrainSeatInfo(ze="有", has_any_ticket=True), prices={"ze": "¥100"})
        with patch("app.services.smart_planner.client_12306.query_train_stops", return_value=stops), patch("app.services.smart_planner.client_12306.query_tickets", return_value=[ticket]) as query:
            plans = smart_planner.calculate_smart_plans("2026-10-10", "G1", "test-train", "SHH", "BJP")
        plan = next(p for p in plans if p.plan_type == 2)
        self.assertEqual(plan.segments[0].train_date, "2026-10-10")
        self.assertEqual(plan.segments[1].train_date, "2026-10-11")
        self.assertEqual(plan.segments[1].from_station_telecode, "NJH")
        self.assertTrue(any(c.args == ("2026-10-11", "NJH", "BJP") for c in query.call_args_list))


if __name__ == "__main__":
    unittest.main()
