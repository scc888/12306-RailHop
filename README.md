# 12306-RailHop · 铁跃

只查询的城市出行路线工具。一次填写出发地、目的地、日期和可接受席别；所选席别没有直达票时，继续查询同车接续和同站中转。

- **三种全程有票路线**：直达、同一运行列车的连续区间接续、1～3次同站换乘。支持城市范围或准确车站，结果展示实际上下车站和完整日期。
- **全部列车**：普速、高铁／动车、混合中转；默认包含二等座、一等座、硬座、硬卧、软卧，无座需主动选择。
- **换乘条件**：默认使用各站已采集的12306官方参考时间；缺少适用数据时回退15分钟；个人时间和官方时间取较大值。可按顺序指定中转站。
- **路线合理性**：默认过滤明显绕行、折返和过长行程；可主动允许较大绕行，或手动指定偏离站点。实际经由站、耗时与绕行提示明确展示。
- **席别和价格**：每段分别选择有票席别，以整数分计价；缺价显示待确认和已知部分，支持按耗时、到达时间、总价排序与复制路线。
- **有条件补票备选**：本次范围未找到全程有票结果时，可主动查看短途有票、后续申请补票的备选；只确认前段，不计入全程有票路线数量或排名。须在原票到站前申请，有运力才可能办理，被拒绝须在原票到站下车。后续能否乘坐、席位及补票金额均待确认。
- **可解释状态**：区分未查询、查询完成、查询不完整和铁路接口失败；取消或修改条件后旧响应不会覆盖新结果。

不提供下单、支付、抢票或补票操作。选择的是席别，不是具体座位号；同车接续不保证原席位延续，重联列车可能需经站台换厢。

## 本地启动

后端 Python/FastAPI，前端 Vue/Vite/Tailwind。

```powershell
# 在 backend 内
python -m pip install -r requirements.txt
python run.py

# 在另一终端的 frontend 内
npm install
npm run dev
```

页面 http://localhost:5173 ，后端接口文档 http://localhost:8000/docs 。Windows也可使用已有 `start.bat` 启动已安装依赖的环境。

## 查询接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/journeys/query` | 统一城市出行查询，返回三个全程有票分组和独立补票备选组 |
| GET | `/api/stations/search` | 城市归属、车站名称／拼音／代码搜索 |
| GET | `/api/transfers/stations` | 有公开便捷换乘依据的中转站及来源 |
| POST | `/api/transfers/query` | 原同站中转接口，继续保留 |
| GET | `/api/tickets/query`、`/api/tickets/stops`、`/api/smart-plans/calculate` | 原查询接口，兼容保留；原智能方案接口仅返回全程有票的同车方案 |

统一请求示例，日期替换为15天预售范围内（含今天）的实际出发日期：

```json
{
  "from_station": "SHH",
  "to_station": "BJP",
  "from_scope": "city",
  "to_scope": "city",
  "train_date": "2026-10-13",
  "mode": "auto",
  "train_type": "all",
  "allowed_seats": ["ze", "zy", "yz", "yw", "rw"],
  "transfer_count": 1,
  "max_same_train_segments": 2,
  "min_transfer_minutes": null,
  "ordered_via_stations": [],
  "allow_large_detour": false,
  "include_short_fallback": false,
  "sort_by": "duration"
}
```

`mode` 支持 `auto/all/direct/same_train/transfer`。`auto` 找到所选席别直达票后跳过两类替代方式；`all` 同时比较。首末站城市归属来自官方字典，中间连接始终是准确电报码相同的实际车站。

`data.direct/same_train/transfer` 分别返回 `plans/meta`，状态为 `complete/partial/upstream_error/skipped`；`data.short_fallback` 返回独立的 `options/meta`，仅主动开启且没有全程有票结果时查询。补票备选全程及后续价格为 `null`，有票区间为 `ticketed_leg`。未知票价不能作为0元排序。

## 数据和范围

便捷换乘资料收录12站，参考时间于2026-10-10采集，保存每站来源、核验日与条件。南京南等参考15分钟、上海30分钟、郑州东60分钟，均为快照，不是全国统一时间或现场保证。中转仅接受资料支持的同日到发条件，当前不推荐跨夜站内等待。

绕行筛选使用 [GeoNames](https://www.geonames.org/export/) 城市中心坐标（CC BY 4.0），匹配332个城市，保留出处和采集日期；城市中心大圆距离不等于实际铁路里程。缺失／歧义数据不猜测，可能保守排除可行路线。刷新脚本为 `backend/scripts/refresh_city_coordinates.py`，没有运行时地理查询依赖。

统一查询总预算60秒；同车最多4个候选车次，当前中转最多12个候选站、45秒、120区间请求、2000状态、50条结果，行程72小时。城市代表站响应不等于全部站对遍历。页面披露截断和失败，不保证全国最优。余票、价格、计划时刻、通道状态及检票安排以铁路实际为准。

## 验证与说明

```powershell
# backend：包含真实网络只读测试
python -m unittest discover -p "test_*.py"

# frontend
npm test
npm run build
# 需要本机可解析的 Playwright 和 Chrome，以及运行中的本地前后端
node browser-tests/journey-regressions.cjs
```

本轮后端76项、前端18项、生产构建和10个Chrome流程通过；真实查询、审查修复及范围限制见 [本轮验证记录](docs/superpowers/journey-query-validation.md)。

[改动说明](docs/2026-10-12-城市出行查询改动说明.md) · [实施计划](docs/superpowers/plans/2026-10-11-journey-query.md) · [12306旅客运输规程](https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html)

代码按 [MIT](LICENSE) 许可发布；GeoNames数据遵循其独立CC BY 4.0许可。
