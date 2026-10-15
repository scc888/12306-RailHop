# 12306-RailHop · 铁跃

只查询的城市出行路线工具。先查车次（无现票车次也显示），点击具体车次，展开该车的同车接续和沿途同站中转方案；也可不限定车次查询全部路线。

- **按车次查询**：点击车次编号或“接续 / 中转”，方案在该车次下展开；固定所选运行列车出发。该车未提供任何所选席别时，本次方案自动按默认组合查询，并显示本车适用席别；仅售罄不回退，原有席别偏好保留。席别与中转条件折叠设置，修改后保留车次列表，可直接重查方案。
- **简洁查询界面**：常用地点、日期、列车类型与排序直接可用；具体车站默认收起，席别与中转设置按需展开，收起仍显示当前条件。查询车次为主操作，最快中转为次操作，提供今天／明天／后天快捷日期与首次使用指引。交换地点保留两侧自选车站；无效的隐藏配置会自动展开并定位，所有查询入口共享校验。
- **分段行程清楚可见**：每段起终站、日期时刻和跨日标记常显，连接处明确换车或同车席别接续；底部可查看分段票价合计。切换排序保留已有方案和席别选择。
- **三种全程有票路线**：直达、同一运行列车的连续区间接续、1～3次同站换乘。支持城市范围或准确车站，结果展示实际上下车站和完整日期。
- **全部列车**：普速、高铁／动车、混合中转；默认包含二等座、一等座、硬座、硬卧、软卧，无座需主动选择。
- **换乘条件**：默认使用已采集的12306官方参考时间；缺少适用数据时，已核实便捷换乘参考15分钟，状态未核实的普通同站中转预留60分钟并明确提示。自定义时完全采用个人时间，可从完整车站字典按顺序指定中转站。
- **路线合理性**：默认过滤明显绕行、折返和过长行程；可主动允许较大绕行，或手动指定偏离站点。实际经由站、耗时与绕行提示明确展示。
- **席别和价格**：车次列表直接列出各席别余票和价格，不因未勾选或无票而隐藏价格。方案中各段可选席别与价格并排显示，点击切换并以整数分更新合计；缺价显示待确认和已知部分，支持按耗时、到达时间、总价排序与复制路线。
- **随时修改条件**：顶部和左侧设置保持原位，右侧车次及展开的方案独立滚动；设置过长时在侧栏内滚动。窄屏通过常驻“修改条件”打开设置抽屉，查询按钮与车次滚动区分开。修改席别或中转条件时保留车次列表。
- **浏览器记住设置**：路线、日期、席别、中转及排序偏好自动保存在本机浏览器，重开后恢复；过期日期回到今天，可一键恢复默认。不缓存余票结果，不写入后端。
- **有条件补票备选**：本次范围未找到全程有票结果时，可主动查看短途有票、后续申请补票的备选；每辆车只展示本次查到最远的可购区间，保留该区间可选席别。只确认前段，不计入全程有票路线数量或排名。须在原票到站前申请，有运力才可能办理，被拒绝须在原票到站下车。后续能否乘坐、席位及补票金额均待确认。
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
| POST | `/api/journeys/query` | 统一查询，返回含无票车次的列表、三类有票方案和独立补票备选；支持指定车次 |
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

页面先以 `mode=direct` 获取 `data.trains`。点击车次时，回传该项 `selection` 至请求 `selected_train`，并以 `mode=all` 查询方案。服务端重新核验实际运行身份；同车只查该车，中转首段固定为该车的可售沿途区间。车次变化或刷新失败时不会改查另一辆车。

`data.direct/same_train/transfer` 分别返回 `plans/meta`，状态为 `complete/partial/upstream_error/skipped`；`data.short_fallback` 返回独立的 `options/meta`，仅主动开启且没有全程有票结果时查询。补票备选全程及后续价格为 `null`，有票区间为 `ticketed_leg`。未知票价不能作为0元排序。

## 数据和范围

中转候选按起终点、相关列车经停站和全车站字典的方向探测动态寻找；没有直达车次时仍尝试两侧探测。手动指定站使用完整12306车站字典，不受便捷换乘资料名单限制。便捷资料独立收录15站，包含新增广州南、成都东、南昌；这不是全国便捷换乘站完整名单。原12站参考时间为2026-10-10快照，新增3站于2026-10-13采集，均保留来源、核验日与条件。南京南等参考15分钟、上海30分钟、郑州东60分钟，均不是全国统一时间或现场保证。已有便捷资料按本站同日到发等条件核对；状态未核实的普通同站中转可能需要出站重新安检，跨日需核对车站开放时段，60分钟仅为默认预留。

绕行筛选使用 [GeoNames](https://www.geonames.org/export/) 城市中心坐标（CC BY 4.0），匹配332个城市，保留出处和采集日期；城市中心大圆距离不等于实际铁路里程。缺失／歧义数据不猜测，可能保守排除可行路线。刷新脚本为 `backend/scripts/refresh_city_coordinates.py`，没有运行时地理查询依赖。

统一查询总预算60秒；全局同车最多4个候选车次，指定车次时仅核对该车；当前中转最多32个候选站、45秒、120次车次／经停站／区间请求、2000状态、50条结果，行程72小时。候选发现共享总预算，最多12秒、4个方向探测站、8次车次经停核验；优先保留手动站和所选首段车次的经停站。多次中转为后续路段预留预算。动态发现和城市代表站响应均不等于全国穷举，自动搜索标明范围不完整，“未找到”仅代表本次搜索范围。余票、价格、计划时刻、通道状态及检票安排以铁路实际为准。

## 验证与说明

```powershell
# backend：包含真实网络只读测试
python -m unittest discover -p "test_*.py"

# frontend
npm test
npm run build
# 需要本机可解析的 Playwright 和 Chrome，以及运行中的本地前后端
node browser-tests/journey-regressions.cjs
node browser-tests/settings-regressions.cjs
node browser-tests/dynamic-transfers.cjs
node browser-tests/seat-fallback.cjs
node browser-tests/ui-usability.cjs
```

动态中转调整的后端99项通过；席别兼容补充后，前端36项、生产构建和33个Chrome流程通过。真实查询、审查修复及限制见 [动态中转改动与验证](docs/2026-10-13-动态中转候选改动说明.md)；城市查询、设置和席别兼容的验证见 [城市查询验证记录](docs/superpowers/journey-query-validation.md)。

[改动说明](docs/2026-10-12-城市出行查询改动说明.md) · [实施计划](docs/superpowers/plans/2026-10-11-journey-query.md) · [12306旅客运输规程](https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html)

代码按 [MIT](LICENSE) 许可发布；GeoNames数据遵循其独立CC BY 4.0许可。
