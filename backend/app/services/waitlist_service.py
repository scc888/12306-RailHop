"""官方候补提交与排队查询；核验不通过时交由用户在官方页面处理。"""
from .payment_service import payment_service, railway_post, waitlist_orders


class WaitlistService:
    def pending(self, sid):
        user = payment_service.require_user(sid)
        data = railway_post(user, "/afterNateOrder/queryQueue")
        order = data.get("order") or {}
        if order.get("reserve_no"):
            return {"status": "WAITING_PAYMENT", "order_id": order["reserve_no"],
                    "msg": "候补订单已创建，请到12306支付预付款后生效"}
        return {"status": "UNKNOWN", "order_id": None, "msg": "候补结果尚未确认，请查询官方订单"}

    def submit(self, sid, ticket, passengers):
        """只候补指定车次和席别，进入确认后即使超时也只查询原请求。"""
        user = payment_service.require_user(sid)
        if user.extra_data.get("pending_waitlist"):
            return {"status": "UNKNOWN", "order_id": None, "msg": "已有候补提交正在确认，请查询原结果，避免重复提交"}
        seat_types = "".join(dict.fromkeys(p.seat_type for p in passengers))
        if not ticket.waitlist_available or any(s in ticket.waitlist_seat_limits for s in seat_types):
            raise ValueError("12306当前不允许该车次或席别候补，请调整方案")
        existing = self.pending(sid)
        if existing["order_id"]:
            raise ValueError("存在待支付候补订单，请先在12306处理")
        secret_list = "".join(f"{ticket.secret_str}#{seat}|" for seat in seat_types)
        face = railway_post(user, "/afterNate/chechFace", {"secretList": secret_list})
        if face.get("login_flag") is not True or face.get("face_flag") is not True:
            return {"status": "ACTION_REQUIRED", "order_id": None, "msg": "候补要求官方身份核验，请在12306完成核验并提交本区间候补"}
        prepared = railway_post(user, "/afterNate/submitOrderRequest", {"secretList": secret_list})
        if prepared.get("flag") is not True:
            return {"status": "ACTION_REQUIRED", "order_id": None, "msg": "官方要求进一步核验，请在12306完成本区间候补"}
        info = railway_post(user, "/afterNate/passengerInitApi")
        if str(info.get("if_check_slide_passcode")) == "1":
            return {"status": "ACTION_REQUIRED", "order_id": None, "msg": "官方要求滑块验证，请在12306完成本区间候补"}
        if not info.get("hbTrainList"):
            raise ValueError("官方未返回可提交的候补车次")
        if any(t.get("train_date") != ticket.train_date or t.get("seat_type_code") not in seat_types for t in info["hbTrainList"]):
            raise ValueError("官方返回的候补日期或席别与所选区间不同，请重新查询")
        if len(passengers) > int(info.get("hb_passenger_max_num", 19)):
            raise ValueError("已超出官方本次候补允许的乘车人数")
        cutoffs = [int(v) for v in info.get("jzdhDiffSelect", []) if str(v).isdigit() and int(v) >= 20]
        if not cutoffs:
            raise ValueError("官方未提供有效的候补截止时间")
        raw = user.extra_data.get("raw_passengers", [])
        passenger_info = []
        for p in passengers:
            contact = next((c for c in raw if c.get("passenger_id_no") == p.passenger_id_no and c.get("passenger_id_type_code") == p.passenger_id_type_code), None)
            if not contact:
                raise ValueError("候补乘车人信息已失效，请重新同步")
            # 官方候补乘车人串与普通购票串不同，最后一位表示老年旅客卧铺下铺偏好。
            passenger_info.append("#".join([p.passenger_type, p.passenger_name, p.passenger_id_type_code,
                                           p.passenger_id_no, p.allEncStr, "0"]))
        payload = {"passengerInfo": ";".join(passenger_info) + ";", "jzParam": "",
                   "hbTrain": ticket.train_no + "#", "lkParam": "", "sessionId": "", "sig": "",
                   "scene": "nc_login", "encryptedData": "", "if_receive_wseat": "N",
                   "realize_limit_time_diff": min(cutoffs),
                   "plans": ticket.secret_str + "," + seat_types + "#", "tmp_train_date": "",
                   "tmp_train_time": "", "add_train_flag": "N", "add_train_seat_type_code": ""}
        if any(p.passenger_type == "2" for p in passengers):
            payload["kid_seat_flag"] = "N"
        # 写请求发出前记录待确认状态，超时不能视为失败后重新提交。
        user.extra_data["pending_waitlist"] = {"train_no": ticket.train_no,
            "from_code": ticket.from_station_telecode, "to_code": ticket.to_station_telecode,
            "train_date": ticket.train_date, "seat_types": seat_types}
        try:
            confirmed = railway_post(user, "/afterNate/confirmHB", payload)
            if confirmed.get("flag") is not True:
                user.extra_data.pop("pending_waitlist", None)
                return {"status": "FAIL", "order_id": None, "msg": confirmed.get("msg") or "官方拒绝提交候补订单"}
            queue = railway_post(user, "/afterNate/queryQueue")
            if queue.get("flag") is True and str(queue.get("status")) == "-1":
                user.extra_data.pop("pending_waitlist", None)
                return {"status": "FAIL", "order_id": None, "msg": queue.get("msg") or "官方候补排队失败"}
            # 候补排队结果只说明提交是否完成，订单号必须再从当前账号订单中读取。
            return self.pending(sid)
        except RuntimeError:
            return {"status": "UNKNOWN", "order_id": None, "msg": "候补确认结果未知，请查询原订单，避免重复提交"}

    def recover(self, sid, task, step):
        """只接回车次、日期、区间、席别和乘车人完全一致的候补，其他订单不会推进本方案。"""
        user = payment_service.require_user(sid)
        data = railway_post(user, "/afterNateOrder/queryQueue")
        order = data.get("order") or {}
        if self.matches(order, task, step):
            user.extra_data.pop("pending_waitlist", None)
            return {"status": "WAITING_PAYMENT", "order_id": order["reserve_no"], "msg": "已核验本区间候补订单，请支付候补预付款"}
        orders = list(waitlist_orders(user, "/afterNateOrder/queryUnHonourHOrder", step["segment"]["train_date"]))
        orders.extend(waitlist_orders(user, "/afterNateOrder/queryProcessedHOrder", step["segment"]["train_date"]))
        matches = [o for o in orders if self.matches(o, task, step)]
        if len(matches) == 1:
            user.extra_data.pop("pending_waitlist", None)
            return {"status": "WAITING_PAYMENT", "order_id": matches[0]["reserve_no"], "msg": "已找到本区间候补订单，正在核验支付状态"}
        return {"status": "UNKNOWN", "order_id": None, "msg": "尚未找到完全匹配的候补订单，请核对官方订单"}

    @staticmethod
    def matches(order, task, step):
        from .booking_service import SEAT_TYPES
        segment = step["segment"]
        needs, people = order.get("needs", []), order.get("passengers", [])
        return bool(order.get("reserve_no")) and len(needs) == 1 and all(
            n.get("board_train_code") == task["train_code"]
            and n.get("from_tele_code") == segment["from_station_telecode"]
            and n.get("to_tele_code") == segment["to_station_telecode"]
            and n.get("train_date") == segment["train_date"]
            and n.get("seat_type") == SEAT_TYPES[segment["seat_code"]]
            for n in needs
        ) and sorted(p.get("passenger_id_no", "") for p in people) == sorted(p.passenger_id_no for p in task["passengers"])


waitlist_service = WaitlistService()
