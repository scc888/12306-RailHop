"""
后端完整业务逻辑与真实 12306 数据自动化测试
"""
import sys
import os
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.station_service import station_service
from app.services.client_12306 import client_12306
from app.services.smart_planner import smart_planner
from app.services.transfer_ticket_gateway import CST

class TestBackendLogic(unittest.TestCase):

    def setUp(self):
        self.train_date = (datetime.now(CST) + timedelta(days=1)).date().isoformat()

    def test_01_station_service(self):
        print("\n--- [测试 1: 车站字典检索] ---")
        station_service.ensure_loaded()
        self.assertGreater(len(station_service.stations), 1000)
        
        # 测试汉字检索
        beijing_code = station_service.get_code("北京")
        self.assertEqual(beijing_code, "BJP")
        shanghai_code = station_service.get_code("上海")
        self.assertEqual(shanghai_code, "SHH")
        
        # 测试拼音模糊搜索
        search_res = station_service.search("shanghai", limit=5)
        self.assertTrue(any(s.name == "上海" for s in search_res))
        print(f"成功加载 {len(station_service.stations)} 个车站，检索 'shanghai' 匹配项: {[s.name for s in search_res]}")

    def test_02_direct_ticket_query(self):
        print("\n--- [测试 2: 真实 12306 直达余票查询] ---")
        train_date = self.train_date
        from_code = "SHH"
        to_code = "BJP"
        
        tickets = client_12306.query_tickets(train_date, from_code, to_code)
        self.assertIsInstance(tickets, list)
        self.assertGreater(len(tickets), 0, "未能查询到上海至北京的车次")
        
        sample = tickets[0]
        print(f"成功获取 {len(tickets)} 趟上海至北京列车！")
        print(f"示例车次: {sample.train_code} | {sample.start_time} -> {sample.arrive_time} | 历时: {sample.duration}")
        print(f"席别情况: 二等座={sample.seats.ze}, 一等座={sample.seats.zy}, 商务座={sample.seats.swz}, 无座={sample.seats.wz}")

    def test_03_query_stops(self):
        print("\n--- [测试 3: 车次沿途经停站时刻表查询] ---")
        train_date = self.train_date
        from_code = "SHH"
        to_code = "BJP"
        
        tickets = client_12306.query_tickets(train_date, from_code, to_code)
        self.assertGreater(len(tickets), 0)
        
        target_train = tickets[0]
        stops = client_12306.query_train_stops(
            target_train.train_no,
            target_train.from_station_telecode,
            target_train.to_station_telecode,
            train_date
        )
        self.assertGreater(len(stops), 1, "经停站列表为空或小于2站")
        print(f"车次 {target_train.train_code} 共有 {len(stops)} 个经停站:")
        for s in stops:
            print(f"  [{s.station_no}] {s.station_name} | 到: {s.arrive_time} | 开: {s.start_time} | 停: {s.stopover_time}")

    def test_04_smart_planner(self):
        print("\n--- [测试 4: 全程有票的同车接续算法] ---")
        train_date = self.train_date
        from_code = "SHH"
        to_code = "BJP"
        
        tickets = client_12306.query_tickets(train_date, from_code, to_code)
        self.assertTrue(tickets, '实时查询未取得候选列车，无法验证同车规划')
        # 挑选一趟有经停站的列车 (如 G28 或首趟车)
        selected_train = next((t for t in tickets if "G" in t.train_code), tickets[0])
        print(f"对车次 {selected_train.train_code} ({selected_train.train_no}) 执行智能方案推算...")
        
        plans = smart_planner.calculate_smart_plans(
            train_date=train_date,
            train_code=selected_train.train_code,
            train_no=selected_train.train_no,
            from_code=selected_train.from_station_telecode,
            to_code=selected_train.to_station_telecode
        )
        
        print(f"成功生成 {len(plans)} 个智能出行备选方案！")
        for idx, plan in enumerate(plans[:5], 1):
            print(f"\n【方案 {idx}】[{plan.plan_type_name}] (推荐分: {plan.recommendation_score})")
            print(f"标语: {plan.title}")
            print(f"风险级别: {plan.risk_level} | 贴士: {plan.risk_notice[:60]}...")
            for seg in plan.segments:
                status = "补票" if seg.is_extension else "购票"
                print(f"   -> [{status}] {seg.from_station} -> {seg.to_station} | 席别: {seg.seat_name} | 状态: {seg.seat_status}")

if __name__ == "__main__":
    unittest.main()
