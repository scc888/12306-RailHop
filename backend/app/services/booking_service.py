"""推荐方案逐段购票：每段支付确认后才推进，结果不明时禁止自动重提。"""
import time
import uuid
from .client_12306 import Ticket12306Client
from .order_service import order_service
from .passenger_service import passenger_service
from .payment_service import payment_service
from ..models.schemas import OrderSubmitParam, PassengerOrderParam

SEAT_TYPES = {"ze": "O", "zy": "M", "swz": "9", "yw": "3", "rw": "4", "srrb": "F", "yz": "1"}


class BookingService:
    def book_single(self, sid, param):
        """普通购票使用当前账号联系人和刷新后的凭据，浏览器只负责选择车次与席别。"""
        user = payment_service.require_user(sid)
        if not user.operation_lock.acquire(blocking=False):
            raise ValueError("当前账号正在处理订单，请稍后刷新")
        try:
            task = user.extra_data.get("booking")
            if task and task["status"] not in {"COMPLETED", "STOPPED"}:
                raise ValueError("已有方案正在购票，请先处理或停止当前方案")
            if user.extra_data.get("pending_order") or user.extra_data.get("pending_waitlist"):
                raise ValueError("已有提交结果待确认，请先查询原订单")
            passengers = self.resolve_passengers(sid, param.passengers)
            if order_service.query_no_complete_order(sid):
                raise ValueError("账号存在待支付订单，请先支付或取消")
            tickets = Ticket12306Client(user.session).query_tickets(param.train_date, param.from_station_telecode, param.to_station_telecode)
            ticket = next((t for t in tickets if t.train_no == param.train_no and t.train_code == param.train_code
                           and t.from_station_telecode == param.from_station_telecode and t.to_station_telecode == param.to_station_telecode), None)
            if not ticket or not ticket.secret_str or not ticket.can_buy:
                raise ValueError("当前区间不可预订，请重新查询")
            for person, requested in zip(passengers, param.passengers):
                code = next((k for k, value in SEAT_TYPES.items() if value == requested.seat_type), None)
                count = sum(p.seat_type == requested.seat_type for p in param.passengers)
                if not code or not self.has_seats(ticket, code, count):
                    raise ValueError("所选席别余票不足或暂不支持，请重新选择")
                person.seat_type = requested.seat_type
            trusted = param.model_copy(update={"secret_str": ticket.secret_str, "from_station_name": ticket.from_station_name,
                "to_station_name": ticket.to_station_name, "passengers": passengers})
            return order_service.submit_ticket_order(sid, trusted)
        finally:
            user.operation_lock.release()

    def resolve_passengers(self, sid, requested_passengers):
        """证件只用于选择账号联系人，姓名、票种与校验信息以官方同步结果为准。"""
        contacts = passenger_service.get_passengers(sid)
        selected, ids = [], set()
        for requested in requested_passengers:
            key = (requested.passenger_id_type_code, requested.passenger_id_no)
            if key in ids:
                raise ValueError("不能重复选择同一乘车人")
            ids.add(key)
            contact = next((p for p in contacts if p.passenger_id_type_code == key[0] and p.passenger_id_no_raw == key[1]), None)
            if not contact:
                raise ValueError("乘车人不属于当前账号，请重新同步")
            selected.append(PassengerOrderParam(passenger_name=contact.passenger_name,
                passenger_id_type_code=contact.passenger_id_type_code, passenger_id_no=contact.passenger_id_no_raw,
                passenger_type=contact.passenger_type, mobile_no=contact.mobile_no, allEncStr=contact.allEncStr))
        return selected

    def create(self, sid, param):
        """从当前会话的推荐结果建立任务，客户端不能自行改写列车或购票区间。"""
        user = payment_service.require_user(sid)
        with user.operation_lock:
            snapshot = user.extra_data.get("plans", {}).get(param.plan_id)
            if not snapshot or time.time() > snapshot["expires_at"]:
                raise ValueError("推荐方案已过期或不属于当前会话，请重新计算")
            existing = user.extra_data.get("booking")
            if existing and existing["status"] not in {"COMPLETED", "STOPPED"}:
                if existing["plan_id"] == param.plan_id:
                    return self.view(existing)
                raise ValueError("已有方案正在购票，请先处理或停止当前方案")
            plan = snapshot["plan"].model_copy(deep=True)
            selected = self.resolve_passengers(sid, param.passengers)
            segments = plan.segments
            if plan.plan_type == 3:
                # 买长乘短只买一张到更远站的票，不能把放弃的区间再买一遍。
                segment = segments[0].model_copy(deep=True)
                segment.to_station = segments[-1].to_station
                segment.to_station_telecode = segments[-1].to_station_telecode
                segment.arrive_time = segments[-1].arrive_time
                segments = [segment]
            steps = []
            for segment in segments:
                if not segment.from_station_telecode or not segment.to_station_telecode or not segment.train_date:
                    raise ValueError("方案缺少准确区间或日期，请重新查询")
                if segment.seat_code not in SEAT_TYPES:
                    raise ValueError("该席别尚不能在工具中准确预订，请选择其他席别或在12306办理")
                steps.append({"kind": "WAITLIST" if segment.is_extension else "TICKET",
                              "segment": segment.model_dump(), "status": "READY", "order_id": None})
            task = {"id": str(uuid.uuid4()), "plan_id": param.plan_id, "title": plan.title,
                    "train_code": plan.train_code, "train_no": plan.train_no, "steps": steps,
                    "passengers": selected, "choose_seats": param.choose_seats,
                    "status": "READY", "current_step": 0, "message": "已建立方案，请开始下单"}
            user.extra_data["booking"] = task
            return self.view(task)

    def task(self, sid, task_id):
        user = payment_service.require_user(sid)
        task = user.extra_data.get("booking")
        if not task or task["id"] != task_id:
            raise LookupError("未找到当前会话的购票方案")
        return user, task

    def view(self, task):
        """仅返回进度和区间，乘车人证件与铁路凭据不进入任务查询响应。"""
        return {k: task[k] for k in ["id", "plan_id", "title", "train_code", "steps", "status", "current_step", "message"]}

    def refresh(self, sid, task_id):
        user, task = self.task(sid, task_id)
        with user.operation_lock:
            if task["status"] in {"WAITING_PAYMENT", "UNKNOWN", "ACTION_REQUIRED"}:
                step = task["steps"][task["current_step"]]
                if step["order_id"]:
                    state = payment_service.status(sid, step["order_id"], step["segment"]["train_date"], step["kind"])["status"]
                    if state == "PAID":
                        step["status"] = "PAID"
                        user.extra_data.pop("pending_order", None)
                        if step["kind"] == "WAITLIST":
                            user.extra_data.pop("pending_waitlist", None)
                        task["current_step"] += 1
                        task["status"] = "COMPLETED" if task["current_step"] == len(task["steps"]) else "READY"
                        task["message"] = "全部步骤已完成；候补是否兑现以12306为准" if task["status"] == "COMPLETED" else "当前段已支付，可以继续下一段"
                    elif state == "WAITING_PAYMENT":
                        step["status"] = task["status"] = "WAITING_PAYMENT"
                        user.extra_data.pop("pending_order", None)
                        if step["kind"] == "WAITLIST":
                            user.extra_data.pop("pending_waitlist", None)
                        task["message"] = "请前往12306付款，付款后自动核验并继续"
                    elif state == "CANCELLED":
                        step["status"] = task["status"] = "STOPPED"
                        task["message"] = "当前订单已取消，后续步骤已停止"
                    else:
                        step["status"] = task["status"] = "UNKNOWN"
                        task["message"] = "尚未查到明确支付结果，请查询官方订单；不会重复下单"
                elif step["kind"] == "TICKET":
                    pending = order_service.refresh_pending_order(sid) or {}
                    if pending.get("order_id"):
                        step["order_id"] = pending["order_id"]
                else:
                    from .waitlist_service import waitlist_service
                    result = waitlist_service.recover(sid, task, step)
                    if result.get("order_id"):
                        step["order_id"] = result["order_id"]
                        step["status"] = task["status"] = result["status"]
                        task["message"] = result["msg"]
            return self.view(task)

    def advance(self, sid, task_id):
        """每次最多执行一段，已进入排队或待支付的步骤只能查询，不能再次提交。"""
        user, task = self.task(sid, task_id)
        if not user.operation_lock.acquire(blocking=False):
            raise ValueError("当前账号正在处理订单，请稍后刷新")
        try:
            if task["status"] != "READY":
                return self.view(task)
            step = task["steps"][task["current_step"]]
            segment = step["segment"]
            if order_service.query_no_complete_order(sid):
                raise ValueError("账号存在待支付订单，请先在12306支付或取消")
            client = Ticket12306Client(user.session)
            tickets = client.query_tickets(segment["train_date"], segment["from_station_telecode"], segment["to_station_telecode"])
            ticket = next((t for t in tickets if t.train_no == task["train_no"] and t.train_code == task["train_code"]), None)
            if not ticket or not ticket.secret_str:
                raise ValueError("未查到该区间的准确车次和下单凭据，请刷新方案")
            passengers = [p.model_copy(update={"seat_type": SEAT_TYPES[segment["seat_code"]]}) for p in task["passengers"]]
            if step["kind"] == "TICKET" and (not self.has_seats(ticket, segment["seat_code"], len(passengers)) or not ticket.can_buy):
                raise ValueError("当前区间该席别余票不足，已保留其他已完成步骤，请重新查询")
            # 外部写请求开始后先锁住进度，连接中断也不能让任务回到可重复提交状态。
            step["status"] = task["status"] = "UNKNOWN"
            task["message"] = "正在核验提交结果，请勿重复下单"
            if step["kind"] == "WAITLIST":
                from .waitlist_service import waitlist_service
                result = waitlist_service.submit(sid, ticket, passengers)
            else:
                result = self.submit_ticket(sid, ticket, passengers, task["choose_seats"])
            step["order_id"] = result.get("order_id")
            step["status"] = task["status"] = result["status"]
            task["message"] = result["msg"]
            return self.view(task)
        except ValueError as exc:
            if task["status"] == "UNKNOWN" and not user.extra_data.get("pending_order") and not user.extra_data.get("pending_waitlist"):
                task["status"] = task["steps"][task["current_step"]]["status"] = "FAIL"
                task["message"] = str(exc)
            raise
        finally:
            user.operation_lock.release()

    def submit_ticket(self, sid, ticket, passengers, seats):
        result = order_service.submit_ticket_order(sid, OrderSubmitParam(
            secret_str=ticket.secret_str, train_date=ticket.train_date, train_no=ticket.train_no,
            train_code=ticket.train_code, from_station_name=ticket.from_station_name,
            to_station_name=ticket.to_station_name, from_station_telecode=ticket.from_station_telecode,
            to_station_telecode=ticket.to_station_telecode, passengers=passengers, choose_seats=seats,
        ))
        return {"status": "WAITING_PAYMENT" if result.success else result.status,
                "order_id": result.order_id, "msg": result.msg}

    @staticmethod
    def has_seats(ticket, seat_code, count):
        value = getattr(ticket.seats, seat_code, "--")
        return value == "有" or (str(value).isdigit() and int(value) >= count)

    def stop(self, sid, task_id):
        user, task = self.task(sid, task_id)
        with user.operation_lock:
            task["status"] = "STOPPED"
            task["message"] = "已停止后续自动下单，已有铁路订单仍需到12306处理"
            return self.view(task)

    def retry(self, sid, task_id):
        """只重试官方明确失败的当前段，已付款区间保留；未知结果不允许重试。"""
        user, task = self.task(sid, task_id)
        with user.operation_lock:
            if task["status"] != "FAIL":
                raise ValueError("只有明确失败的步骤才能重试，请先核对官方状态")
            step = task["steps"][task["current_step"]]
            if step["order_id"] or user.extra_data.get("pending_order") or user.extra_data.get("pending_waitlist"):
                raise ValueError("只有明确失败且没有待确认订单的步骤才能重试，请先核对官方状态")
            step["status"] = task["status"] = "READY"
            return self.advance(sid, task_id)


booking_service = BookingService()
