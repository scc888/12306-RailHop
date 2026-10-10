"""通过真实API、服务和解析代码走完两段流程，只有铁路网络使用固定样本。"""
import time
import unittest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import app
from app.models.schemas import SmartPlan, PlanSegment
from app.services.session_manager import UserSession, session_manager
from test_v2 import response


class BookingFlowTests(unittest.TestCase):
    def test_ticket_payment_then_waitlist_payment(self):
        user = UserSession("full-booking-flow")
        user.is_logged_in = True
        session_manager._sessions[user.session_id] = user
        client = TestClient(app)
        headers = {"X-Session-Id": user.session_id}
        segments = [PlanSegment(train_date="2026-10-10", from_station="上海", to_station="南京", from_station_telecode="SHH", to_station_telecode="NJH", seat_name="二等座", seat_code="ze", seat_status="有票"),
                    PlanSegment(train_date="2026-10-11", from_station="南京", to_station="北京", from_station_telecode="NJH", to_station_telecode="BJP", seat_name="二等座", seat_code="ze", seat_status="候补", is_extension=True)]
        plan = SmartPlan(plan_id="plan", plan_type=1, plan_type_name="买短补长", title="前段购票，后段候补", train_code="G1", train_no="test-train", segments=segments)
        user.extra_data["plans"] = {"plan": {"plan": plan, "expires_at": time.time()+900}}
        paid_ticket = paid_waitlist = submitted_ticket = submitted_waitlist = False
        submitted = []
        contact = {"passenger_name": "测试旅客", "passenger_id_no": "test-id", "passenger_id_type_code": "1", "allEncStr": "official-enc"}

        def post(url, **kwargs):
            nonlocal submitted_ticket, submitted_waitlist
            path = url.split("/otn")[-1]
            data = {"flag": True, "submitStatus": True, "count": 0}
            if path.endswith("getPassengerDTOs"):
                data = {"normal_passengers": [contact]}
            elif path.endswith("initDc"):
                return Mock(text="var globalRepeatSubmitToken = 'abc123'; 'key_check_isChange': 'key', 'leftTicketStr': 'left', 'train_location': 'loc'")
            elif path.endswith("queryMyOrderNoComplete"):
                data = {"orderDBList": [{"sequence_no": "E1"}] if submitted_ticket and not paid_ticket else []}
            elif path.endswith("queryMyOrder"):
                data = {"OrderDTODataList": [{"sequence_no": "E1", "tickets": [{"ticket_status_name": "已支付"}]}] if paid_ticket else [], "order_total_number": 1 if paid_ticket else 0}
            elif path.endswith("confirmSingleForQueue"):
                submitted_ticket = True
                submitted.append(("TICKET", kwargs["data"]))
            elif path == "/afterNateOrder/queryQueue":
                data = {"order": {"reserve_no": "H1"}} if submitted_waitlist and not paid_waitlist else {}
            elif path.endswith("chechFace"):
                data = {"login_flag": True, "face_flag": True}
            elif path.endswith("passengerInitApi"):
                data = {"hbTrainList": [{"seat_type_code": "O", "train_date": "2026-10-11"}], "jzdhDiffSelect": [30, 60], "if_check_slide_passcode": "0"}
            elif path.endswith("confirmHB"):
                self.assertTrue(paid_ticket, "候补必须等前段已付款再提交")
                submitted_waitlist = True
                submitted.append(("WAITLIST", kwargs["data"]))
            elif path.endswith("queryUnHonourHOrder"):
                data = {"list": [{"reserve_no": "H1", "total_page": 1}] if paid_waitlist else []}
            return response({"status": True, "data": data})

        def get(url, **kwargs):
            if "queryOrderWaitTime" in url:
                return response({"status": True, "data": {"orderId": "E1", "waitTime": -1}})
            if "leftTicket/queryG" in url:
                params = kwargs["params"]
                fields = [""] * 40
                fields[:12] = ["fresh-secret", "预订", "test-train", "G1", "SHH", "BJP", params["leftTicketDTO.from_station"], params["leftTicketDTO.to_station"], "23:00", "02:00", "03:00", "Y"]
                fields[30] = "有" if params["leftTicketDTO.from_station"] == "SHH" else "无"
                fields[37] = "1"
                return response({"status": True, "data": {"result": ["|".join(fields)], "map": {"SHH": "上海", "NJH": "南京", "BJP": "北京"}}})
            return response({})

        user.session.post = Mock(side_effect=post)
        user.session.get = Mock(side_effect=get)
        try:
            result = client.post("/api/bookings", headers=headers, json={"plan_id": "plan", "passengers": [{"passenger_name": "不可信姓名", "passenger_id_no": "test-id", "allEncStr": "bad"}]})
            self.assertEqual(result.status_code, 200)
            task_id = result.json()["data"]["id"]
            advance = "/api/bookings/"+task_id+"/advance"
            refresh = "/api/bookings/"+task_id
            first = client.post(advance, headers=headers).json()["data"]
            self.assertEqual(first["status"], "WAITING_PAYMENT")
            self.assertEqual(first["steps"][0]["order_id"], "E1")
            client.post(advance, headers=headers)
            self.assertEqual(len(submitted), 1)
            paid_ticket = True
            self.assertEqual(client.get(refresh, headers=headers).json()["data"]["status"], "READY")
            second = client.post(advance, headers=headers).json()["data"]
            self.assertEqual(second["steps"][1]["order_id"], "H1")
            self.assertEqual(second["status"], "WAITING_PAYMENT")
            self.assertIn("测试旅客", submitted[0][1]["passengerTicketStr"])
            self.assertIn("official-enc", submitted[1][1]["passengerInfo"])
            paid_waitlist = True
            self.assertEqual(client.get(refresh, headers=headers).json()["data"]["status"], "COMPLETED")
        finally:
            session_manager.remove(user.session_id)


if __name__ == "__main__":
    unittest.main()
