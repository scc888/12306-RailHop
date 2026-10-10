"""购票任务边界测试：全部铁路响应为样本，不会创建真实订单。"""
import time
import unittest
from unittest.mock import Mock, patch
import requests
import threading
from concurrent.futures import ThreadPoolExecutor

from app.models.schemas import TrainSeatInfo, TrainTicketInfo, PlanBookingParam, SmartPlan, PlanSegment, PassengerDTO
from app.services.booking_service import booking_service
from app.services.order_service import order_service
from app.services.payment_service import payment_service
from app.services.waitlist_service import waitlist_service
from app.services.session_manager import session_manager, UserSession
from app.services.smart_planner import smart_planner
from test_v2 import order_param, response


def ticket():
    return TrainTicketInfo(train_date="2026-10-10", train_no="test-train", train_code="G1",
        start_station_name="上海", end_station_name="北京", from_station_name="上海", to_station_name="南京",
        from_station_telecode="SHH", to_station_telecode="NJH", start_time="23:00", arrive_time="23:55",
        duration="00:55", secret_str="test-secret", waitlist_available=True, seats=TrainSeatInfo(ze="有"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.sid = "workflow-test"
        self.user = UserSession(self.sid)
        self.user.is_logged_in = True
        session_manager._sessions[self.sid] = self.user
        segment = {"train_date": "2026-10-10", "from_station": "上海", "to_station": "南京",
                   "from_station_telecode": "SHH", "to_station_telecode": "NJH", "seat_code": "ze"}
        self.task = {"id": "task", "plan_id": "plan", "title": "测试", "train_no": "test-train", "train_code": "G1",
            "status": "READY", "current_step": 0, "message": "", "choose_seats": "",
            "passengers": order_param().passengers,
            "steps": [{"kind": "TICKET", "segment": segment.copy(), "status": "READY", "order_id": None},
                      {"kind": "WAITLIST", "segment": segment.copy(), "status": "READY", "order_id": None}]}
        self.user.extra_data["booking"] = self.task

    def tearDown(self):
        session_manager.remove(self.sid)

    def test_payment_advances_one_step_only_after_explicit_paid(self):
        self.task.update(status="WAITING_PAYMENT")
        self.task["steps"][0].update(order_id="E1", status="WAITING_PAYMENT")
        with patch.object(payment_service, "status", return_value={"status": "PAID"}):
            result = booking_service.refresh(self.sid, "task")
        self.assertEqual((result["status"], result["current_step"]), ("READY", 1))
        self.assertEqual(result["steps"][0]["status"], "PAID")

    def test_unknown_payment_never_advances_or_submits(self):
        self.task.update(status="WAITING_PAYMENT")
        self.task["steps"][0]["order_id"] = "E1"
        with patch.object(payment_service, "status", return_value={"status": "UNKNOWN"}), patch.object(booking_service, "submit_ticket") as submit:
            booking_service.refresh(self.sid, "task")
            booking_service.advance(self.sid, "task")
        self.assertEqual(self.task["current_step"], 0)
        self.assertEqual(self.task["status"], "UNKNOWN")
        submit.assert_not_called()

    def test_failure_after_dispatch_cannot_leave_ready_for_duplicate_submission(self):
        with patch.object(order_service, "query_no_complete_order", return_value=None), patch("app.services.booking_service.Ticket12306Client") as client, patch.object(booking_service, "submit_ticket", side_effect=RuntimeError("网络中断")):
            client.return_value.query_tickets.return_value = [ticket()]
            try:
                booking_service.advance(self.sid, "task")
            except RuntimeError:
                pass
        self.assertEqual(self.task["status"], "UNKNOWN")

    def test_remaining_section_always_uses_waitlist(self):
        self.task["current_step"] = 1
        with patch.object(order_service, "query_no_complete_order", return_value=None), patch("app.services.booking_service.Ticket12306Client") as client, patch.object(booking_service, "submit_ticket") as ordinary, patch.object(waitlist_service, "submit", return_value={"status": "WAITING_PAYMENT", "order_id": "H1", "msg": "待支付"}) as waitlist:
            client.return_value.query_tickets.return_value = [ticket()]
            booking_service.advance(self.sid, "task")
        waitlist.assert_called_once()
        ordinary.assert_not_called()

    def test_no_order_id_unknown_queue_is_queryable(self):
        self.task["status"] = "UNKNOWN"
        self.user.extra_data["pending_order"] = {"repeat_token": "abc", "order_id": None}
        self.user.session.get = Mock(return_value=response({"status": True, "data": {"orderId": "E1", "waitTime": -1}}))
        self.user.session.post = Mock(return_value=response({"status": True, "data": {"submitStatus": True}}))
        result = booking_service.refresh(self.sid, "task")
        self.assertEqual(result["steps"][0]["order_id"], "E1")

    def test_account_cannot_read_another_accounts_real_task(self):
        other = UserSession("other-user")
        other.is_logged_in = True
        session_manager._sessions[other.session_id] = other
        try:
            with self.assertRaises(LookupError):
                booking_service.refresh(other.session_id, "task")
        finally:
            session_manager.remove(other.session_id)

    def test_stopped_task_does_not_submit_and_preserves_paid_step(self):
        self.task["steps"][0].update(status="PAID", order_id="E1")
        booking_service.stop(self.sid, "task")
        with patch.object(booking_service, "submit_ticket") as submit:
            booking_service.advance(self.sid, "task")
        submit.assert_not_called()
        self.assertEqual(self.task["steps"][0]["order_id"], "E1")

    def test_order_precheck_timeout_does_not_clear_login(self):
        self.user.session.post = Mock(side_effect=requests.Timeout("模拟超时"))
        result = order_service.submit_ticket_order(self.sid, order_param())
        self.assertTrue(self.user.is_logged_in)
        self.assertFalse(result.success)

    def test_confirm_transport_timeout_is_unknown_and_cannot_resubmit(self):
        def post(url, **kwargs):
            if url.endswith("/initDc"):
                return Mock(text="var globalRepeatSubmitToken = 'abc123'; 'key_check_isChange': 'key', 'leftTicketStr': 'left', 'train_location': 'loc'")
            if url.endswith("/confirmSingleForQueue"):
                raise requests.Timeout("模拟确认超时")
            return response({"status": True, "data": {"flag": True, "submitStatus": True, "count": 0}})
        self.user.session.post = Mock(side_effect=post)
        result = order_service.submit_ticket_order(self.sid, order_param())
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("pending_order", self.user.extra_data)
        before = self.user.session.post.call_count
        order_service.submit_ticket_order(self.sid, order_param())
        self.assertEqual(self.user.session.post.call_count, before)

    def test_waitlist_unknown_request_cannot_be_dispatched_twice(self):
        self.user.extra_data["pending_waitlist"] = {"train_no": "test-train"}
        with patch("app.services.waitlist_service.railway_post") as post:
            result = waitlist_service.submit(self.sid, ticket(), order_param().passengers)
        self.assertEqual(result["status"], "UNKNOWN")
        post.assert_not_called()

    def test_zero_seats_not_recommended(self):
        self.assertEqual(smart_planner._get_best_available_seat(TrainSeatInfo(ze="0")), (None, None, None))

    def test_paid_waitlist_finishes_task_without_claiming_redemption(self):
        self.task.update(status="WAITING_PAYMENT", current_step=1)
        self.task["steps"][1]["order_id"] = "H1"
        with patch.object(payment_service, "status", return_value={"status": "PAID"}):
            result = booking_service.refresh(self.sid, "task")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertIn("兑现", result["message"])

    def test_paid_ticket_status_requires_all_passengers_paid(self):
        self.user.session.post = Mock(side_effect=[response({"status": True, "data": {"orderDBList": []}}),
            response({"status": True, "data": {"OrderDTODataList": [{"sequence_no": "E1", "tickets": [{"ticket_status_name": "已支付"}, {"ticket_status_name": "待支付"}]}]}})])
        self.assertEqual(payment_service.status(self.sid, "E1", "2026-10-10")["status"], "UNKNOWN")

    def test_already_redeemed_waitlist_is_still_confirmed_paid(self):
        def post(url, **kwargs):
            orders = [{"reserve_no": "H1", "status_code": "07"}] if url.endswith("queryProcessedHOrder") else []
            return response({"status": True, "data": {"list": orders}})
        self.user.session.post = Mock(side_effect=post)
        self.assertEqual(payment_service.status(self.sid, "H1", "2026-10-10", "WAITLIST")["status"], "PAID")

    def test_manual_candidate_recovery_does_not_attach_another_section(self):
        self.task.update(status="ACTION_REQUIRED", current_step=1)
        order = {"reserve_no": "H-other", "needs": [{"board_train_code": "G99", "from_tele_code": "SHH", "to_tele_code": "NJH", "train_date": "2026-10-10", "seat_type": "O"}], "passengers": [{"passenger_id_no": "test-id"}]}
        with patch("app.services.waitlist_service.railway_post", return_value={"order": order}), patch("app.services.waitlist_service.waitlist_orders", return_value=[]):
            result = booking_service.refresh(self.sid, "task")
        self.assertIsNone(result["steps"][1]["order_id"])
        self.assertEqual(result["current_step"], 1)

    def test_manual_candidate_recovery_matches_all_business_fields(self):
        self.task.update(status="ACTION_REQUIRED", current_step=1)
        order = {"reserve_no": "H1", "needs": [{"board_train_code": "G1", "from_tele_code": "SHH", "to_tele_code": "NJH", "train_date": "2026-10-10", "seat_type": "O"}], "passengers": [{"passenger_id_no": "test-id"}]}
        with patch("app.services.waitlist_service.railway_post", return_value={"order": order}):
            result = booking_service.refresh(self.sid, "task")
        self.assertEqual(result["steps"][1]["order_id"], "H1")
        self.assertEqual(result["status"], "WAITING_PAYMENT")

    def test_slide_validation_never_bypassed(self):
        with patch("app.services.waitlist_service.railway_post", side_effect=[{}, {"login_flag": True, "face_flag": True}, {"flag": True}, {"if_check_slide_passcode": "1"}]) as post:
            result = waitlist_service.submit(self.sid, ticket(), order_param().passengers)
        self.assertEqual(result["status"], "ACTION_REQUIRED")
        self.assertFalse(any(c.args[1].endswith("confirmHB") for c in post.call_args_list))

    def test_waitlist_uses_official_payload_and_preserves_uncertain_request(self):
        self.user.extra_data["raw_passengers"] = [{"passenger_id_no": "test-id", "passenger_id_type_code": "1"}]
        with patch("app.services.waitlist_service.railway_post", side_effect=[{}, {"login_flag": True, "face_flag": True}, {"flag": True}, {"hbTrainList": [{"train_date": "2026-10-10", "seat_type_code": "O"}], "jzdhDiffSelect": [10, 30, 60]}, RuntimeError("确认超时")]) as post:
            result = waitlist_service.submit(self.sid, ticket(), order_param().passengers)
        payload = post.call_args.args[2]
        self.assertEqual(payload["plans"], "test-secret,O#")
        self.assertEqual(payload["hbTrain"], "test-train#")
        self.assertEqual(payload["realize_limit_time_diff"], 30)
        self.assertTrue(payload["passengerInfo"].endswith("#0;"))
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("pending_waitlist", self.user.extra_data)

    def create_plan(self, plan_type=3):
        self.user.extra_data.pop("booking")
        segments = [PlanSegment(**self.task["steps"][0]["segment"], seat_name="二等座", seat_status="有票"),
            PlanSegment(train_date="2026-10-11", from_station="南京", to_station="北京", from_station_telecode="NJH", to_station_telecode="BJP", seat_code="ze", seat_name="二等座", seat_status="放弃后段", is_extension=plan_type == 1)]
        plan = SmartPlan(plan_id="plan", plan_type=plan_type, plan_type_name="测试", train_code="G1", train_no="test-train", title="测试", segments=segments)
        self.user.extra_data["plans"] = {"plan": {"plan": plan, "expires_at": time.time()+900}}
        return PlanBookingParam(plan_id="plan", passengers=order_param().passengers)

    def test_buy_long_board_short_only_creates_one_full_ticket(self):
        param = self.create_plan()
        contact = PassengerDTO(passenger_name="测试旅客", passenger_id_no="test-id", passenger_id_no_raw="test-id")
        with patch("app.services.booking_service.passenger_service.get_passengers", return_value=[contact]):
            result = booking_service.create(self.sid, param)
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["segment"]["to_station_telecode"], "BJP")
        self.assertNotIn("passengers", result)

    def test_expired_plan_rejected_without_network_submission(self):
        param = self.create_plan()
        self.user.extra_data["plans"]["plan"]["expires_at"] = 0
        with patch("app.services.booking_service.passenger_service.get_passengers") as contacts:
            with self.assertRaises(ValueError):
                booking_service.create(self.sid, param)
        contacts.assert_not_called()

    def test_duplicate_passengers_rejected(self):
        param = self.create_plan(1)
        param.passengers.append(param.passengers[0])
        contact = PassengerDTO(passenger_name="测试旅客", passenger_id_no="test-id", passenger_id_no_raw="test-id")
        with patch("app.services.booking_service.passenger_service.get_passengers", return_value=[contact]):
            with self.assertRaises(ValueError):
                booking_service.create(self.sid, param)

    def test_retry_definite_failure_keeps_paid_sections(self):
        self.task.update(current_step=1, status="FAIL")
        self.task["steps"][0].update(status="PAID", order_id="E1")
        self.task["steps"][1]["status"] = "FAIL"
        with patch.object(booking_service, "advance", return_value={"status": "WAITING_PAYMENT"}) as advance:
            booking_service.retry(self.sid, "task")
        advance.assert_called_once_with(self.sid, "task")
        self.assertEqual(self.task["steps"][0]["order_id"], "E1")
        self.assertEqual(self.task["steps"][1]["status"], "READY")

    def test_retry_uncertain_submission_is_forbidden(self):
        self.task["status"] = "UNKNOWN"
        with patch.object(booking_service, "advance") as advance:
            with self.assertRaises(ValueError):
                booking_service.retry(self.sid, "task")
        advance.assert_not_called()

    def test_waitlist_status_searches_later_official_pages(self):
        def post(url, **kwargs):
            if url.endswith("queryUnHonourHOrder"):
                page = kwargs["data"]["page_no"]
                return response({"status": True, "data": {"list": [{"reserve_no": "H1" if page == 1 else "H-other", "total_page": 2}]}})
            return response({"status": True, "data": {}})
        self.user.session.post = Mock(side_effect=post)
        self.assertEqual(payment_service.status(self.sid, "H1", "2026-10-10", "WAITLIST")["status"], "PAID")

    def test_second_section_uses_correct_train_and_interval(self):
        self.task["current_step"] = 1
        self.task["steps"][1].update(kind="TICKET")
        self.task["steps"][1]["segment"].update(train_date="2026-10-11", from_station_telecode="NJH", to_station_telecode="BJP")
        t = ticket().model_copy(update={"train_date": "2026-10-11", "from_station_telecode": "NJH", "to_station_telecode": "BJP"})
        with patch.object(order_service, "query_no_complete_order", return_value=None), patch("app.services.booking_service.Ticket12306Client") as client, patch.object(booking_service, "submit_ticket", return_value={"status": "WAITING_PAYMENT", "order_id": "E2", "msg": "待支付"}) as submit:
            client.return_value.query_tickets.return_value = [t]
            booking_service.advance(self.sid, "task")
        client.return_value.query_tickets.assert_called_once_with("2026-10-11", "NJH", "BJP")
        self.assertEqual(submit.call_args.args[1].train_no, "test-train")

    def test_client_zero_inventory_does_not_report_available(self):
        from app.services.client_12306 import Ticket12306Client
        fields = [""] * 40
        fields[0:12] = ["secret", "预订", "test-train", "G1", "SHH", "BJP", "SHH", "BJP", "08:00", "12:00", "04:00", "Y"]
        fields[30] = "0"
        result = Ticket12306Client()._parse_ticket_results(["|".join(fields)], {"SHH": "上海", "BJP": "北京"})
        self.assertFalse(result[0].seats.has_any_ticket)

    def test_retry_completed_task_is_rejected_without_index_error(self):
        self.task.update(status="COMPLETED", current_step=2)
        with self.assertRaises(ValueError):
            booking_service.retry(self.sid, "task")

    def test_waitlist_preparation_cannot_change_departure_date(self):
        self.user.extra_data["raw_passengers"] = [{"passenger_id_no": "test-id", "passenger_id_type_code": "1"}]
        with patch("app.services.waitlist_service.railway_post", side_effect=[{}, {"login_flag": True, "face_flag": True}, {"flag": True}, {"hbTrainList": [{"train_date": "2026-10-11", "seat_type_code": "O"}], "jzdhDiffSelect": [30]}, {"flag": False}]) as post:
            with self.assertRaises(ValueError):
                waitlist_service.submit(self.sid, ticket(), order_param().passengers)
        self.assertFalse(any(c.args[1].endswith("confirmHB") for c in post.call_args_list))

    def test_concurrent_clicks_only_dispatch_one_submission(self):
        entered, release = threading.Event(), threading.Event()
        def submit(*args):
            entered.set()
            release.wait(3)
            return {"status": "WAITING_PAYMENT", "order_id": "E1", "msg": "待支付"}
        with patch.object(order_service, "query_no_complete_order", return_value=None), patch("app.services.booking_service.Ticket12306Client") as client, patch.object(booking_service, "submit_ticket", side_effect=submit) as submission:
            client.return_value.query_tickets.return_value = [ticket()]
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(booking_service.advance, self.sid, "task")
                try:
                    self.assertTrue(entered.wait(2))
                    with self.assertRaises(ValueError):
                        booking_service.advance(self.sid, "task")
                finally:
                    release.set()
                self.assertEqual(future.result(timeout=3)["status"], "WAITING_PAYMENT")
        submission.assert_called_once()

    def test_query_preserves_encoded_secret_for_official_waitlist(self):
        from app.services.client_12306 import Ticket12306Client
        fields = [""] * 40
        fields[:12] = ["test%2Bsecret%3D", "预订", "test-train", "G1", "SHH", "BJP", "SHH", "BJP", "08:00", "12:00", "04:00", "Y"]
        result = Ticket12306Client()._parse_ticket_results(["|".join(fields)], {"SHH": "上海", "BJP": "北京"})
        self.assertEqual(result[0].secret_str, "test%2Bsecret%3D")

    def test_ordinary_order_decodes_secret_once_for_form_submission(self):
        param = order_param().model_copy(update={"secret_str": "test%2Bsecret%3D"})
        self.user.session.post = Mock(return_value=response({"status": True}))
        order_service._submit_order_request(self.user.session, param)
        self.assertEqual(self.user.session.post.call_args.kwargs["data"]["secretStr"], "test+secret=")


if __name__ == "__main__":
    unittest.main()
