"""
FastAPI HTTP 端点端到端自动化测试
"""
import sys
import os
import unittest
from fastapi.testclient import TestClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app

class TestFastApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_root_and_health(self):
        print("\n--- [测试 API: 根路径与健康检查] ---")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "online")

        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertGreater(res_health.json()["stations_loaded"], 3000)
        print("根路径与健康检查测试通过，已加载车站数:", res_health.json()["stations_loaded"])

    def test_02_station_search_api(self):
        print("\n--- [测试 API: 车站联想搜索] ---")
        res = self.client.get("/api/stations/search?keyword=nanjing&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertGreater(len(data), 0)
        names = [s["name"] for s in data]
        print("搜索 'nanjing' 返回车站:", names)
        self.assertTrue(any("南京" in n for n in names))

    def test_03_ticket_query_api(self):
        print("\n--- [测试 API: 直达余票查询] ---")
        res = self.client.get("/api/tickets/query?train_date=2026-10-10&from_station=上海&to_station=北京")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first_train = data[0]
        self.assertIn("prices", first_train)
        print(f"查询上海->北京成功返回 {len(data)} 趟列车，首趟: {first_train['train_code']}，票价: {first_train['prices']}")

    def test_04_smart_plans_api(self):
        print("\n--- [测试 API: 智能推算方案] ---")
        # 查上海到北京
        query_res = self.client.get("/api/tickets/query?train_date=2026-10-10&from_station=上海&to_station=北京")
        trains = query_res.json()["data"]
        target = trains[0]
        
        plan_url = (
            f"/api/smart-plans/calculate?"
            f"train_date=2026-10-10&"
            f"train_code={target['train_code']}&"
            f"train_no={target['train_no']}&"
            f"from_station=上海&"
            f"to_station=北京"
        )
        res = self.client.get(plan_url)
        self.assertEqual(res.status_code, 200)
        plans = res.json()["data"]
        self.assertIsInstance(plans, list)
        print(f"车次 {target['train_code']} 成功计算出 {len(plans)} 个智能方案！")
        if plans:
            print(f"Top 1 方案标题: {plans[0]['title']}")

if __name__ == "__main__":
    unittest.main()
