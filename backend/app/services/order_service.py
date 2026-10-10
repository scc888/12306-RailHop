"""
12306 订单与购票服务 (完整 8 步排队状态机)
"""
import re
import json
import time
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from ..models.schemas import (
    OrderSubmitParam,
    PassengerOrderParam,
    OrderSubmitResult,
    UnpaidOrderInfo,
    UnpaidTicketDetail
)
from .session_manager import UserSession, session_manager

logger = logging.getLogger(__name__)

class OrderService:
    def submit_ticket_order(self, session_id: str, param: OrderSubmitParam) -> OrderSubmitResult:
        """串行提交同一账号的订单；已有不确定的排队请求时先查询，禁止重复提交。"""
        user = session_manager.get(session_id)
        if not user or not user.is_logged_in:
            return OrderSubmitResult(success=False, status="FAIL", msg="请先扫码登录12306")
        if not user.operation_lock.acquire(blocking=False):
            return OrderSubmitResult(success=False, status="BUSY", msg="当前账号正在处理订单，请稍后查询结果")
        try:
            if user.extra_data.get("pending_order"):
                return OrderSubmitResult(success=False, status="UNKNOWN", msg="已有订单正在确认，请先查询结果，避免重复下单")
            return self._submit_ticket_order(session_id, param)
        except RuntimeError:
            return OrderSubmitResult(success=False, status="FAIL", msg="暂时无法核验12306登录状态，请稍后重试")
        finally:
            user.operation_lock.release()

    def _submit_ticket_order(self, session_id: str, param: OrderSubmitParam) -> OrderSubmitResult:
        """
        完整购票排队状态机流水线:
        1. checkUser
        2. submitOrderRequest
        3. initDc (提取防重 Token 和表单数据)
        4. checkOrderInfo
        5. getQueueCount
        6. confirmSingleForQueue
        7. queryOrderWaitTime (轮询)
        8. resultOrderForDcQueue
        """
        user_sess = session_manager.get(session_id)
        if not user_sess or not user_sess.is_logged_in:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg="用户未登录，请先使用 12306 客户端扫码登录"
            )

        sess = user_sess.session

        # --- 步骤 1: 预检用户登录态 ---
        logger.info(f"Step 1: Checking user status...")
        if not self._check_user(sess):
            user_sess.clear_auth()
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg="12306 登录凭据已失效，请重新扫码登录"
            )

        # --- 步骤 2: 提交预订申请 submitOrderRequest ---
        logger.info(f"Step 2: Submitting order request for {param.train_code}...")
        sub_ok, sub_msg = self._submit_order_request(sess, param)
        if not sub_ok:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg=sub_msg
            )

        # --- 步骤 3: 初始化订单确认页面 initDc ---
        logger.info(f"Step 3: Initializing DC passenger form...")
        init_ok, init_data, init_msg = self._init_dc(sess)
        if not init_ok:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg=init_msg
            )

        repeat_token = init_data.get("repeat_token", "")
        key_check_isChange = init_data.get("key_check_isChange", "")
        left_ticket_str = init_data.get("left_ticket_str", "")
        train_location = init_data.get("train_location", "")

        # --- 构造乘车人串 passengerTicketStr & oldPassengerStr ---
        passenger_ticket_str, old_passenger_str = self._build_passenger_strings(param.passengers)
        if not passenger_ticket_str:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg="乘车人信息格式有误"
            )

        # --- 步骤 4: 校验订单信息 checkOrderInfo ---
        logger.info(f"Step 4: Checking order info...")
        chk_ok, chk_msg = self._check_order_info(sess, repeat_token, passenger_ticket_str, old_passenger_str)
        if not chk_ok:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg=chk_msg
            )

        # --- 步骤 5: 查询排队人数与余票 getQueueCount ---
        logger.info(f"Step 5: Getting queue count...")
        primary_seat = param.passengers[0].seat_type if param.passengers else "O"
        q_ok, q_count, q_msg = self._get_queue_count(
            sess,
            repeat_token,
            param.train_date,
            param.train_no,
            param.train_code,
            primary_seat,
            param.from_station_telecode,
            param.to_station_telecode,
            left_ticket_str,
            train_location
        )
        if not q_ok:
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg=q_msg
            )

        # --- 步骤 6: 提交单程排队下单 confirmSingleForQueue ---
        # 请求可能已被铁路收到，即使连接超时也必须用原令牌查询，不能重提。
        user_sess.extra_data["pending_order"] = {"repeat_token": repeat_token, "order_id": None}
        logger.info(f"Step 6: Confirming single for queue (choose_seats={param.choose_seats})...")
        c_ok, c_msg = self._confirm_single_for_queue(
            sess,
            repeat_token,
            passenger_ticket_str,
            old_passenger_str,
            key_check_isChange,
            left_ticket_str,
            train_location,
            param.choose_seats or ""
        )
        if c_ok is None:
            return OrderSubmitResult(success=False, status="UNKNOWN", msg=c_msg)
        if not c_ok:
            user_sess.extra_data.pop("pending_order", None)
            return OrderSubmitResult(
                success=False,
                status="FAIL",
                msg=c_msg
            )

        # --- 步骤 7: 轮询排队等待结果 queryOrderWaitTime ---
        logger.info(f"Step 7: Waiting in queue...")
        wait_ok, order_id, wait_msg = self._wait_for_order(sess, repeat_token)
        if not wait_ok:
            return OrderSubmitResult(
                success=False,
                status="UNKNOWN",
                msg=wait_msg
            )

        # --- 步骤 8: 确认下单结果 resultOrderForDcQueue ---
        if order_id:
            user_sess.extra_data["pending_order"]["order_id"] = order_id
            logger.info(f"Step 8: Finalizing DC queue for order {order_id}...")
            if not self._result_order_for_dc_queue(sess, repeat_token, order_id):
                return OrderSubmitResult(success=False, order_id=order_id, status="UNKNOWN", msg="订单已分配，但最终确认未完成，请查询官方订单状态")

        user_sess.extra_data.pop("pending_order", None)

        logger.info(f"Order created successfully! OrderID: {order_id}")
        return OrderSubmitResult(
            success=True,
            order_id=order_id,
            status="SUCCESS",
            msg="订单已创建，请按12306显示的支付截止时间完成付款"
        )

    def _check_user(self, sess) -> bool:
        try:
            res = sess.post(
                "https://kyfw.12306.cn/otn/login/checkUser",
                data={"_json_att": ""},
                headers={"Referer": "https://kyfw.12306.cn/otn/leftTicket/init"},
                verify=True,
                timeout=8
            )
            res.raise_for_status()
            body = res.json()
            data = body.get("data", {})
            if body.get("status") is not True or data.get("flag") not in (True, False):
                raise RuntimeError("未返回有效登录状态")
            return data["flag"] is True
        except Exception as e:
            logger.error("下单前核验登录状态失败", exc_info=e)
            raise RuntimeError("暂时无法核验登录状态") from e

    def _submit_order_request(self, sess, param: OrderSubmitParam) -> Tuple[bool, str]:
        url = "https://kyfw.12306.cn/otn/leftTicket/submitOrderRequest"
        payload = {
            "secretStr": urllib.parse.unquote(param.secret_str),
            "train_date": param.train_date,
            "back_train_date": param.back_train_date or param.train_date,
            "tour_flag": "dc",
            "purpose_codes": param.purpose_codes or "ADULT",
            "query_from_station_name": param.from_station_name,
            "query_to_station_name": param.to_station_name,
            "undefined": ""
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = sess.post(url, data=payload, headers=headers, verify=True, timeout=10)
            res_json = res.json()
            if res_json.get("status", False):
                return True, "提交预订成功"
            messages = res_json.get("messages", [])
            msg_str = "，".join(messages) if messages else "提交预订失败，可能席别已售罄或存在未完成订单"
            return False, msg_str
        except Exception as e:
            logger.error("submitOrderRequest exception", exc_info=e)
            return False, f"网络异常: {str(e)}"

    def _init_dc(self, sess) -> Tuple[bool, Dict[str, Any], str]:
        url = "https://kyfw.12306.cn/otn/confirmPassenger/initDc"
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            res = sess.post(url, data={"_json_att": ""}, headers=headers, verify=True, timeout=10)
            html = res.text

            # 提取 globalRepeatSubmitToken
            token_match = re.search(r"var\s+globalRepeatSubmitToken\s*=\s*'([a-f0-9]+)';", html)
            if not token_match:
                # 检查页面是否包含错误提示
                if "您还有未处理的订单" in html:
                    return False, {}, "您还有未完成支付的订单，请先支付或取消后再试"
                return False, {}, "无法获取防重令牌，请重试"

            repeat_token = token_match.group(1)

            # 提取 ticketInfoForPassengerForm 相关参数
            key_check_match = re.search(r"'key_check_isChange':\s*'([A-Za-z0-9]+)'", html)
            left_ticket_match = re.search(r"'leftTicketStr':\s*'([^']+)'", html)
            train_location_match = re.search(r"'train_location':\s*'([^']+)'", html)

            return True, {
                "repeat_token": repeat_token,
                "key_check_isChange": key_check_match.group(1) if key_check_match else "",
                "left_ticket_str": left_ticket_match.group(1) if left_ticket_match else "",
                "train_location": train_location_match.group(1) if train_location_match else ""
            }, "初始化成功"
        except Exception as e:
            logger.error("initDc exception", exc_info=e)
            return False, {}, f"初始化订单页失败: {str(e)}"

    def _build_passenger_strings(self, passengers: List[PassengerOrderParam]) -> Tuple[str, str]:
        """
        构造 passengerTicketStr 和 oldPassengerStr
        格式:
        passengerTicketStr: seatType,0,ticketType,name,idType,idNo,mobile,N,allEncStr_...
        oldPassengerStr: name,idType,idNo,ticketType_...
        """
        p_list = []
        old_list = []
        for p in passengers:
            # seat_type: 如 'O'(二等座), 'M'(一等座), '9'(商务座)
            s_type = p.seat_type or "O"
            t_type = p.passenger_type or "1"
            id_type = p.passenger_id_type_code or "1"
            mobile = p.mobile_no or ""
            enc = p.allEncStr or ""

            # 单人 passengerTicket: seat_type,0,passenger_type,name,id_type,id_no,mobile,N,allEncStr
            p_ticket = f"{s_type},0,{t_type},{p.passenger_name},{id_type},{p.passenger_id_no},{mobile},N,{enc}"
            p_list.append(p_ticket)

            # 单人 oldPassenger: name,id_type,id_no,passenger_type_
            old_p = f"{p.passenger_name},{id_type},{p.passenger_id_no},{t_type}_"
            old_list.append(old_p)

        return "_".join(p_list), "".join(old_list)

    def _check_order_info(self, sess, repeat_token: str, passenger_ticket_str: str, old_passenger_str: str) -> Tuple[bool, str]:
        url = "https://kyfw.12306.cn/otn/confirmPassenger/checkOrderInfo"
        payload = {
            "cancel_flag": "2",
            "bed_level_order_num": "000000000000000000000000000000",
            "passengerTicketStr": passenger_ticket_str,
            "oldPassengerStr": old_passenger_str,
            "tour_flag": "dc",
            "randCode": "",
            "whatsSelect": "1",
            "_json_att": "",
            "REPEAT_SUBMIT_TOKEN": repeat_token
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = sess.post(url, data=payload, headers=headers, verify=True, timeout=10)
            res_json = res.json()
            if not res_json.get("status", False):
                msgs = res_json.get("messages", [])
                return False, "，".join(msgs) if msgs else "乘车人校验失败"

            data = res_json.get("data", {})
            if data.get("submitStatus", False):
                return True, "校验通过"
            errMsg = data.get("errMsg", "乘车人校验未通过")
            return False, errMsg
        except Exception as e:
            logger.error("checkOrderInfo exception", exc_info=e)
            return False, f"校验乘车人失败: {str(e)}"

    def _get_queue_count(
        self,
        sess,
        repeat_token: str,
        train_date: str,
        train_no: str,
        station_train_code: str,
        seat_type: str,
        from_code: str,
        to_code: str,
        left_ticket_str: str,
        train_location: str
    ) -> Tuple[bool, int, str]:
        url = "https://kyfw.12306.cn/otn/confirmPassenger/getQueueCount"
        # 转换日期格式为 GMT
        try:
            dt = datetime.strptime(train_date, "%Y-%m-%d")
            # 格式: Mon Oct 12 2026 00:00:00 GMT+0800 (China Standard Time)
            gmt_date = dt.strftime("%a %b %d %Y 00:00:00 GMT+0800 (China Standard Time)")
        except Exception:
            gmt_date = train_date

        payload = {
            "train_date": gmt_date,
            "train_no": train_no,
            "stationTrainCode": station_train_code,
            "seatType": seat_type,
            "fromStationTelecode": from_code,
            "toStationTelecode": to_code,
            "leftTicket": left_ticket_str,
            "purpose_codes": "00",
            "train_location": train_location,
            "_json_att": "",
            "REPEAT_SUBMIT_TOKEN": repeat_token
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = sess.post(url, data=payload, headers=headers, verify=True, timeout=10)
            res_json = res.json()
            if not res_json.get("status", False):
                msgs = res_json.get("messages", [])
                return False, 0, "，".join(msgs) if msgs else "获取排队人数失败"

            data = res_json.get("data", {})
            count = int(data.get("count", 0))
            ticket = data.get("ticket", "0")
            # 检查是否有票或排队人数过多
            if data.get("op_2") == "true":
                return False, count, "排队人数已超过余票数，可能无法成功出票"
            return True, count, "排队校验成功"
        except Exception as e:
            logger.error("getQueueCount exception", exc_info=e)
            return False, 0, f"查询排队信息失败: {str(e)}"

    def _confirm_single_for_queue(
        self,
        sess,
        repeat_token: str,
        passenger_ticket_str: str,
        old_passenger_str: str,
        key_check_isChange: str,
        left_ticket_str: str,
        train_location: str,
        choose_seats: str
    ) -> Tuple[Optional[bool], str]:
        url = "https://kyfw.12306.cn/otn/confirmPassenger/confirmSingleForQueue"
        payload = {
            "passengerTicketStr": passenger_ticket_str,
            "oldPassengerStr": old_passenger_str,
            "randCode": "",
            "purpose_codes": "00",
            "key_check_isChange": key_check_isChange,
            "leftTicketStr": left_ticket_str,
            "train_location": train_location,
            "choose_seats": choose_seats,
            "seatDetailType": "000",
            "whatsSelect": "1",
            "roomType": "00",
            "dwAll": "N",
            "_json_att": "",
            "REPEAT_SUBMIT_TOKEN": repeat_token
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = sess.post(url, data=payload, headers=headers, verify=True, timeout=10)
            res.raise_for_status()
            res_json = res.json()
            if not res_json.get("status", False):
                msgs = res_json.get("messages", [])
                return False, "，".join(msgs) if msgs else "提交订单确认失败"

            data = res_json.get("data", {})
            if data.get("submitStatus", False):
                return True, "提交排队成功"
            errMsg = data.get("errMsg", "未能成功进入排队队列")
            return False, errMsg
        except Exception as e:
            logger.error("提交订单确认结果未知，保留原请求供查询", exc_info=e)
            return None, "提交确认结果未知，请查询原订单，避免重复提交"

    def refresh_pending_order(self, session_id: str):
        """查询原排队请求一次并保留订单号，轮询接口不再提交新的购票申请。"""
        user = session_manager.get(session_id)
        if not user or not user.is_logged_in:
            raise ValueError("请先扫码登录12306")
        with user.operation_lock:
            pending = user.extra_data.get("pending_order")
            if not pending:
                return None
            if not pending.get("order_id"):
                try:
                    res = user.session.get("https://kyfw.12306.cn/otn/confirmPassenger/queryOrderWaitTime",
                        params={"random": int(time.time() * 1000), "tourFlag": "dc", "_json_att": "",
                                "REPEAT_SUBMIT_TOKEN": pending["repeat_token"]}, timeout=8, verify=True)
                    res.raise_for_status()
                    body = res.json()
                    if body.get("status") is not True:
                        raise RuntimeError("官方未确认排队结果")
                    pending["order_id"] = body.get("data", {}).get("orderId")
                except Exception as exc:
                    logger.error("查询原排队订单失败", exc_info=exc)
                    raise RuntimeError("暂时无法查询原排队订单，请稍后刷新") from exc
            if pending.get("order_id"):
                self._result_order_for_dc_queue(user.session, pending["repeat_token"], pending["order_id"])
            return pending

    def pending_result(self, session_id: str):
        """普通购票超时后查询原请求；只有查到同一订单的待支付记录才提示下单成功。"""
        user = session_manager.get(session_id)
        if not user or not user.is_logged_in:
            raise ValueError("请先扫码登录12306")
        with user.operation_lock:
            pending = user.extra_data.get("pending_order")
            if pending and not pending.get("order_id"):
                pending = self.refresh_pending_order(session_id)
            unpaid = self.query_no_complete_order(session_id)
            if unpaid and (not pending or not pending.get("order_id") or pending["order_id"] == unpaid.sequence_no):
                user.extra_data.pop("pending_order", None)
                return OrderSubmitResult(success=True, order_id=unpaid.sequence_no, status="SUCCESS", msg="已确认订单，请按12306显示的截止时间付款")
            return OrderSubmitResult(success=False, order_id=(pending or {}).get("order_id"), status="UNKNOWN", msg="尚未查到明确结果，请在12306核对订单，不要重复提交")

    def _wait_for_order(self, sess, repeat_token: str, max_seconds: int = 30) -> Tuple[bool, Optional[str], str]:
        """
        轮询 queryOrderWaitTime 等待分配订单号
        """
        start_time = time.time()
        url = "https://kyfw.12306.cn/otn/confirmPassenger/queryOrderWaitTime"
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc"
        }

        while time.time() - start_time < max_seconds:
            try:
                params = {
                    "random": int(time.time() * 1000),
                    "tourFlag": "dc",
                    "_json_att": "",
                    "REPEAT_SUBMIT_TOKEN": repeat_token
                }
                res = sess.get(url, params=params, headers=headers, verify=True, timeout=8)
                res_json = res.json()

                if not res_json.get("status", False):
                    msgs = res_json.get("messages", [])
                    return False, None, "，".join(msgs) if msgs else "排队查询失败"

                data = res_json.get("data", {})
                wait_time = data.get("waitTime", 0)
                order_id = data.get("orderId")

                if order_id:
                    return True, order_id, "排队完成，成功生成订单"

                # waitTime < 0 代表处理完成或失败
                if wait_time < 0:
                    if order_id:
                        return True, order_id, "订票成功"
                    msg = data.get("msg") or "未能成功分配座位或出票已终止"
                    return False, None, msg

                # 仍在排队中，根据 wait_time 适度休眠
                sleep_sec = 2 if wait_time > 5 else 1
                time.sleep(sleep_sec)

            except Exception as e:
                logger.warning("queryOrderWaitTime notice", exc_info=e)
                time.sleep(2)

        return False, None, "排队等待超时，请稍后在【我的未完成订单】中查看是否已出票"

    def _result_order_for_dc_queue(self, sess, repeat_token: str, order_id: str) -> bool:
        url = "https://kyfw.12306.cn/otn/confirmPassenger/resultOrderForDcQueue"
        payload = {
            "orderSequence_no": order_id,
            "_json_att": "",
            "REPEAT_SUBMIT_TOKEN": repeat_token
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = sess.post(url, data=payload, headers=headers, verify=True, timeout=8)
            res.raise_for_status()
            body = res.json()
            return body.get("status") is True and body.get("data", {}).get("submitStatus") is True
        except Exception as e:
            logger.warning("resultOrderForDcQueue notice", exc_info=e)
            return False

    def query_no_complete_order(self, session_id: str) -> Optional[UnpaidOrderInfo]:
        """
        查询当前用户的未完成（待支付）订单
        """
        user_sess = session_manager.get(session_id)
        if not user_sess or not user_sess.is_logged_in:
            return None

        url = "https://kyfw.12306.cn/otn/queryOrder/queryMyOrderNoComplete"
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/queryOrder/initNoComplete",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = user_sess.session.post(url, data={"_json_att": ""}, headers=headers, verify=True, timeout=10)
            res.raise_for_status()
            res_json = res.json()
            if res_json.get("status") is not True or not isinstance(res_json.get("data"), dict):
                raise RuntimeError("12306未返回有效的订单查询结果")
            data = res_json["data"]
            order_db_list = data.get("orderDBList", [])
            if not order_db_list:
                return None

            first_order = order_db_list[0]
            sequence_no = first_order.get("sequence_no", "")
            ticket_total_price = first_order.get("ticket_total_price_page", "0")
            pay_limit_time = first_order.get("pay_limit_time", "")

            # 计算支付剩余秒数 (45分钟倒计时)
            countdown = None
            if pay_limit_time:
                try:
                    limit_dt = datetime.strptime(pay_limit_time, "%Y-%m-%d %H:%M:%S")
                    diff = (limit_dt - datetime.now()).total_seconds()
                    countdown = max(0, int(diff))
                except Exception:
                    countdown = None

            tickets_raw = first_order.get("tickets", [])
            ticket_details: List[UnpaidTicketDetail] = []
            for t in tickets_raw:
                ticket_details.append(UnpaidTicketDetail(
                    passenger_name=t.get("passengerDTO", {}).get("passenger_name", ""),
                    coach_no=t.get("coach_name", "") + "车",
                    seat_no=t.get("seat_name", ""),
                    seat_name=t.get("seat_type_name", ""),
                    ticket_type_name=t.get("ticket_type_name", ""),
                    price=f"¥{t['str_ticket_price_page']}" if t.get("str_ticket_price_page") else "待官方确认"
                ))

            train = tickets_raw[0].get("stationTrainDTO", {}) if tickets_raw else {}
            return UnpaidOrderInfo(
                sequence_no=sequence_no,
                train_code=train.get("station_train_code", ""),
                train_date=tickets_raw[0].get("start_train_date_page", "") if tickets_raw else "",
                start_time=train.get("start_time", ""),
                arrive_time=train.get("arrive_time", ""),
                from_station_name=train.get("from_station_name", ""),
                to_station_name=train.get("to_station_name", ""),
                tickets=ticket_details,
                total_price=f"¥{ticket_total_price}",
                pay_limit_time=pay_limit_time,
                countdown_seconds=countdown
            )

        except Exception as e:
            logger.error("查询待支付订单失败", exc_info=e)
            raise RuntimeError("暂时无法查询12306订单，请稍后重试") from e

    def cancel_no_complete_order(self, session_id: str, sequence_no: str) -> Tuple[bool, str]:
        """
        取消未完成订单 (注意: 每日限取消 3 次)
        """
        user_sess = session_manager.get(session_id)
        if not user_sess or not user_sess.is_logged_in:
            return False, "用户未登录"

        url = "https://kyfw.12306.cn/otn/queryOrder/cancelNoCompleteMyOrder"
        payload = {
            "sequence_no": sequence_no,
            "cancel_flag": "cancel_order",
            "_json_att": ""
        }
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/queryOrder/initNoComplete",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            res = user_sess.session.post(url, data=payload, headers=headers, verify=True, timeout=10)
            res_json = res.json()
            if res_json.get("status") is True and res_json.get("data", {}).get("existError") == "N":
                return True, "已成功取消订单"
            if res_json.get("data", {}).get("existError") == "Y":
                return False, res_json["data"].get("errorMsg", "12306拒绝取消订单")
            msgs = res_json.get("messages", [])
            return False, "，".join(msgs) if msgs else "取消订单失败"
        except Exception as e:
            logger.error("cancelNoCompleteMyOrder exception", exc_info=e)
            return False, f"操作异常: {str(e)}"

order_service = OrderService()
