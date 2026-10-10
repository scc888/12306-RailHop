"""
12306 常用联系人/乘车人服务
"""
import logging
from typing import List, Optional
from ..models.schemas import PassengerDTO
from .session_manager import UserSession, session_manager

logger = logging.getLogger(__name__)

class PassengerService:
    def get_passengers(self, session_id: str) -> List[PassengerDTO]:
        """
        获取当前登录账号下的常用乘车人列表
        """
        user_sess = session_manager.get(session_id)
        if not user_sess or not user_sess.is_logged_in:
            logger.warning(f"Session {session_id} not logged in when fetching passengers")
            return []

        url = "https://kyfw.12306.cn/otn/confirmPassenger/getPassengerDTOs"
        headers = {
            "Referer": "https://kyfw.12306.cn/otn/confirmPassenger/initDc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        payload = {
            "_json_att": ""
        }

        try:
            res = user_sess.session.post(
                url,
                data=payload,
                headers=headers,
                verify=True,
                timeout=10
            )
            res.raise_for_status()
            res_json = res.json()
            data = res_json.get("data", {})
            if res_json.get("status") is not True or not isinstance(data.get("normal_passengers"), list):
                raise RuntimeError("12306未返回有效乘车人列表")
            normal_passengers = data.get("normal_passengers", [])
            user_sess.extra_data["raw_passengers"] = normal_passengers

            result: List[PassengerDTO] = []
            for item in normal_passengers:
                raw_id = item.get("passenger_id_no", "")
                masked_id = self._mask_id_no(raw_id)
                p_dto = PassengerDTO(
                    passenger_name=item.get("passenger_name", ""),
                    passenger_id_type_code=item.get("passenger_id_type_code", "1"),
                    passenger_id_type_name=item.get("passenger_id_type_name", "中国居民身份证"),
                    passenger_id_no=masked_id,
                    passenger_id_no_raw=raw_id,
                    passenger_type=item.get("passenger_type", "1"),
                    passenger_type_name=item.get("passenger_type_name", "成人"),
                    mobile_no=item.get("mobile_no", ""),
                    allEncStr=item.get("allEncStr", "")
                )
                result.append(p_dto)
            return result

        except Exception as e:
            logger.error("同步乘车人失败", exc_info=e)
            raise RuntimeError("暂时无法同步12306乘车人，请稍后重试") from e

    @staticmethod
    def _mask_id_no(id_no: str) -> str:
        """身份证号脱敏"""
        if not id_no or len(id_no) < 8:
            return id_no
        if len(id_no) == 18:
            return id_no[:4] + "**********" + id_no[-4:]
        elif len(id_no) == 15:
            return id_no[:3] + "********" + id_no[-4:]
        else:
            return id_no[:2] + "****" + id_no[-2:]

passenger_service = PassengerService()
