"""官方付款入口与订单状态核验，始终以铁路订单查询结果为准。"""
import logging

from .session_manager import session_manager

logger = logging.getLogger(__name__)
BASE = "https://kyfw.12306.cn/otn"


def railway_post(user, path, payload=None):
    """读取官方表单接口；无效响应和网络失败均保留为错误，不能伪装成空订单。"""
    try:
        if path.startswith("/afterNateOrder/"):
            referer = BASE + "/view/lineUp_order.html"
        elif path in {"/afterNate/passengerInitApi", "/afterNate/confirmHB", "/afterNate/queryQueue"}:
            referer = BASE + "/view/lineUp_toPay.html"
        else:
            referer = BASE + ("/view/train_order.html" if path.startswith("/queryOrder/") else "/leftTicket/init")
        res = user.session.post(BASE + path, data=payload or {}, headers={"Referer": referer}, timeout=12, verify=True)
        res.raise_for_status()
        body = res.json()
        if body.get("status") is not True or not isinstance(body.get("data"), dict):
            raise RuntimeError("12306未返回有效结果")
        return body["data"]
    except Exception as exc:
        logger.error("读取铁路订单接口失败，接口=" + path, exc_info=exc)
        raise RuntimeError("暂时无法读取12306订单状态，请稍后刷新") from exc


def waitlist_orders(user, path, train_date):
    """按官方候补分页读取，订单不在第一页时也能核验；上限内未找到则保留未知状态。"""
    for page in range(20):
        data = railway_post(user, path, {"page_no": page, "query_start_date": train_date, "query_end_date": train_date})
        orders = data.get("list", [])
        yield from orders
        if not orders or page + 1 >= int(orders[0].get("total_page", 1)):
            break


class PaymentService:
    def require_user(self, sid):
        user = session_manager.get(sid)
        if not user or not user.is_logged_in:
            raise ValueError("请先扫码登录12306")
        return user

    def status(self, sid, order_id, train_date, kind="TICKET"):
        """按订单号确认支付，未完成订单消失时仍需找到明确的已支付记录。"""
        user = self.require_user(sid)
        if kind == "WAITLIST":
            pending = railway_post(user, "/afterNateOrder/queryQueue")
            order = pending.get("order") or {}
            if order.get("reserve_no") == order_id:
                return {"status": "WAITING_PAYMENT", "order_id": order_id}
            if any(o.get("reserve_no") == order_id for o in waitlist_orders(user, "/afterNateOrder/queryUnHonourHOrder", train_date)):
                # 此接口只返回已付款、等待兑现的候补订单。
                return {"status": "PAID", "order_id": order_id}
            for order in waitlist_orders(user, "/afterNateOrder/queryProcessedHOrder", train_date):
                if order.get("reserve_no") == order_id:
                    # 官方已兑现状态代表预付款已完成；终止或退款的候补不推进后续购票。
                    if order.get("status_code") == "07":
                        return {"status": "PAID", "order_id": order_id}
                    if order.get("status_code") in {"05", "06", "08", "10", "11"}:
                        return {"status": "CANCELLED", "order_id": order_id}
            return {"status": "UNKNOWN", "order_id": order_id}

        pending = railway_post(user, "/queryOrder/queryMyOrderNoComplete", {"_json_att": ""})
        if any(o.get("sequence_no") == order_id for o in pending.get("orderDBList", [])):
            return {"status": "WAITING_PAYMENT", "order_id": order_id}
        for page in range(20):
            data = railway_post(user, "/queryOrder/queryMyOrder", {
                "come_from_flag": "my_order", "query_where": "G", "queryType": "2",
                "queryStartDate": train_date, "queryEndDate": train_date,
                "pageIndex": page, "pageSize": 8, "sequeue_train_name": order_id,
            })
            for order in data.get("OrderDTODataList", []):
                if order.get("sequence_no") != order_id:
                    continue
                states = [t.get("ticket_status_name") for t in order.get("tickets", [])]
                if states and all(s in {"已支付", "已出票", "已检票", "已使用"} for s in states):
                    return {"status": "PAID", "order_id": order_id}
                if states and all(s in {"已取消", "已退票", "交易关闭"} for s in states):
                    return {"status": "CANCELLED", "order_id": order_id}
                return {"status": "UNKNOWN", "order_id": order_id}
            if (page + 1) * 8 >= int(data.get("order_total_number", 0)):
                break
        return {"status": "UNKNOWN", "order_id": order_id}

    def entry(self, sid, order_id, kind="TICKET"):
        """只为当前账号已有的待支付订单准备付款入口，不向浏览器传递Cookie。"""
        user = self.require_user(sid)
        with user.operation_lock:
            if kind == "WAITLIST":
                pending = railway_post(user, "/afterNateOrder/queryQueue")
                if (pending.get("order") or {}).get("reserve_no") != order_id:
                    raise ValueError("未找到当前账号的待支付候补订单")
                data = railway_post(user, "/afterNateOrder/continuePayNoCompleteMyOrder", {"reserve_no": order_id})
                if data.get("flag") is not True:
                    raise ValueError(data.get("msg") or "无法进入候补付款流程")
                url = BASE + "/view/lineUp_order.html"
            else:
                pending = railway_post(user, "/queryOrder/queryMyOrderNoComplete", {"_json_att": ""})
                order = next((o for o in pending.get("orderDBList", []) if o.get("sequence_no") == order_id), None)
                if not order:
                    raise ValueError("未找到当前账号的待支付订单")
                arrival = "".join(t["stationTrainDTO"]["station_train_code"] + "," + t["stationTrainDTO"]["arrive_time"] + ";" for t in order.get("tickets", []))
                data = railway_post(user, "/queryOrder/continuePayNoCompleteMyOrder", {"sequence_no": order_id, "pay_flag": "pay", "arrive_time_str": arrival})
                if data.get("existError") != "N":
                    raise ValueError(data.get("errorMsg") or "无法进入付款流程")
                url = BASE + "/view/train_order.html?isLC=N&payFlag=N"
            return {"url": url, "order_id": order_id,
                    "msg": "请在官方订单页找到该订单并点击去支付；官方网页可能需要再次扫码登录"}


payment_service = PaymentService()
