# 同站中转查询 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 V1 上提供仅查询的同站便捷中转功能，支持 1～3 个中转站、指定站、可配置换乘间隔、分段席别和准确总价。

**Architecture:** 保留既有直达查询与同车规划。新增便捷换乘车站资料服务、隔离的铁路查询网关、受预算约束的中转搜索和独立 Vue 页面组件；通过完整日期时间及电报码连接不同列车。

**Tech Stack:** Python / FastAPI / Pydantic / requests，Vue 3 / Vite / Tailwind，unittest 与 Node 内置测试；不新增产品依赖。

**Spec:** `docs/superpowers/specs/2026-10-10-transfer-query-design.md`

## Global Constraints

- 本版仅查询，展示车次、时刻、余票、席别和价格。
- 只接受同一个车站内换乘，不接受同城跨站。
- 中转站数量提供 1、2、3 站，默认 1 站；该数量表示实际换乘次数。
- 最少换乘时间默认 15 分钟；允许用户调大，最低输入值为 15 分钟。
- 默认按首段出发至末段到达的总耗时排序，包含中间等待。
- 指定多个中转站时按输入顺序经过；不能静默替换指定站。
- 中转站必须有资料确认支持站内便捷换乘。
- “选择座位”指选择席别；查询不分配座位号。
- 金额以整数分处理；未知票价不当作 0 元，不输出虚假合计。
- 使用 Asia/Shanghai 完整日期时间；测试不创建真实订单。
- 仅修改本计划列出的路径；保留 `backend/logs/`；不合并购票分支。

## Review Focus

1. 铁路响应将同城其他车站混入站对查询：返回电报码不符的车次必须丢弃，归任务 2/3 测试。
2. 站台/站场适用条件无法从车次数据确定：不输出不具依据的便捷换乘推荐，归任务 1/3 测试。
3. 午夜换乘及持续两天以上的慢车：以日期和历时计算，不用时刻大小猜跨日，归任务 2/3 测试。
4. 用户重复点击或修改条件时旧请求晚返回：旧结果不能覆盖新结果，归任务 5 测试。
5. 席别改选导致排序价格变化、或一段缺价：显示合计与价格排序一致，未知合计排末，归任务 3/5 测试。

## 文件与公共接口

新增：

- `backend/app/models/transfer_schemas.py`：请求、搜索元信息、车站、分段和路线模型。
- `backend/data/transfer_stations.json`：逐站带来源的便捷换乘资料。
- `backend/app/services/transfer_station_service.py`：资料载入、检索与指定站校验。
- `backend/app/services/transfer_ticket_gateway.py`：严格错误合同、分段日期、票价与余票转换。
- `backend/app/services/transfer_planner.py`：搜索、时间衔接、排序和预算。
- `backend/app/api/transfer_routes.py`：中转 API。
- `backend/test_transfer_stations.py`、`test_transfer_gateway.py`、`test_transfer_planner.py`、`test_transfer_api.py`。
- `frontend/src/components/TransferSearch.vue`、`TransferPlanCard.vue`：表单、路线和席别选择。
- `frontend/src/lib/transfer.js`：请求、金额计算、排序、格式化和复制文本。
- `frontend/tests/transfer.test.mjs`：前端有状态交互及金额回归。

修改：

- `backend/app/services/client_12306.py`：增加向后兼容的严格查询入口。
- `backend/app/config.py`：显式中转搜索限制。
- `backend/app/main.py`：注册中转路由。
- `frontend/src/App.vue`：加入中转入口、复用查询条件和无票提示。
- `frontend/package.json`：增加 Node 测试脚本。
- `README.md`：功能、查询范围、车站资料与启动验证说明。

接口固定为：

- `GET /api/transfers/stations?keyword=...&limit=20` → `ApiResponse[list[TransferStation]]`。
- `POST /api/transfers/query`，请求：`from_station: str`、`to_station: str`（电报码）、
  `train_date: date`、`transfer_count: int=1`、`min_transfer_minutes: int=15`、
  `ordered_via_stations: list[str]=[]`、`allowed_seats: list[str]=['ze','zy']`、
  `sort_by: Literal['duration','arrival','price']='duration'`。
- 响应：`ApiResponse[TransferSearchResult]`，包含 `plans` 和 `meta`。
- `TransferSeat`：`code, name, availability, price_fen: int | None`。
- `TransferLeg`：`train_no, train_code, from_station, to_station, departure_at, arrival_at, seats`；
  日期时间序列化为带 `+08:00` 的 ISO 字符串。
- `TransferConnection`：`station, wait_minutes, required_minutes, source_url`。
- `TransferPlan`：`id, legs, connections, total_minutes, selected_seat_codes, total_price_fen, known_price_fen`。
- `TransferSearchMeta`：`queried_at, candidate_station_codes, query_count, failed_pairs, truncated,
  truncation_reasons, limits, station_data_checked_at`。

## Task 1: 模型与便捷换乘站资料

**Files:** 新增模型、车站 JSON、车站服务、`backend/test_transfer_stations.py`。

**Interfaces:**

- `TransferStationService.search(keyword: str, limit: int = 20) -> list[TransferStation]`。
- `TransferStationService.candidates(required_codes: list[str], limit: int) -> list[TransferStation]`。
- `TransferStationService.validate_via(codes: list[str]) -> list[TransferStation]`。
- 资料包含电报码、拼音、资料发布时间、核验时间、来源 URL、便捷换乘状态、可空最低参考分钟数、适用限制。

- [ ] 写模型校验及资料测试：`transfer_count=0/4`、间隔 14、空席别、重复指定站失败；默认值为 1 / 15 / ['ze','zy']；指定数量超过中转数量失败。
- [ ] 运行 `python -m unittest test_transfer_stations -v`（backend），确认新增行为尚未实现而失败。
- [ ] 从铁路、车站或政府发布的一手资料收集至少 12 个实际可用的便捷换乘站；逐条记录来源、发布日期和本次资料核验日期，以现有站字典校验电报码。不能将测试虚构站写入生产资料，也不能将历史文章核验日期称为实时车站状态确认。
- [ ] 实现模型和服务。指定站缺少资料、通道关闭、限制无法判断时返回明确原因；受限制站暂不进入自动推荐，除非网关数据足以核验条件。
- [ ] 补充断言：汉字/拼音/简拼匹配；指定站始终进入候选；错误电报码、资料空值、未知状态和站场限制不能被默认为可用；不以全国站点数量替代逐站数据。
- [ ] 再次运行上述测试，确认全部通过；检查每条生产资料 URL 与对应站名称。
- [ ] 精确暂存本任务文件并提交 `feat: add verified transfer station catalog and query models`。

## Task 2: 严格铁路查询与日期金额转换

**Files:** 修改 `client_12306.py`；新增网关和 `backend/test_transfer_gateway.py`。

**Interfaces:**

- 增加 `RailwayQueryError(RuntimeError)`；`Ticket12306Client.query_tickets_strict(train_date: str, from_code: str, to_code: str, purpose_codes: str = 'ADULT') -> list[TrainTicketInfo]`。
- 原 `query_tickets(...)` 保持失败返回 `[]` 的既有行为，内部复用严格入口；不改变旧接口参数合同。
- `TransferTicketGateway.query(train_date: date, from_code: str, to_code: str, allowed_seats: list[str], timeout_seconds: float) -> list[TransferLeg]`。
- `TransferTicketGateway` 使用自己的 `Ticket12306Client` 实例；不并发共享 V1 的单例会话。
- `parse_price_fen(value: str) -> int | None`，仅接受明确金额；使用 Decimal 转分。

- [ ] 写失败测试：HTTP 失败、重定向异常、空体、HTML、非法 JSON、上游业务失败抛 `RailwayQueryError`；合法空结果返回 `[]`；旧入口仍返回 `[]`。
- [ ] 运行 `python -m unittest test_transfer_gateway -v`，确认失败。
- [ ] 实现严格入口与网关，所有实际网络阶段都使用传入的超时限制。配置独立会话，保持参数、路径和返回的日期/区间一致。
- [ ] 写转换断言：`23:50 + 02:00` 为次日 `01:50`；`23:50 + 26:00` 为后日 `01:50`；与返回时刻不一致、格式错误或电报码不匹配的车次剔除并记录解析问题。
- [ ] 写余票与价格断言：仅“有”和正整数且可售的席别进入结果；候补、未开售、0、负数、-- 被过滤；¥123.5→12350；缺价返回 None；默认无座不入选。
- [ ] 运行任务 1/2 测试，确认通过；增加旧路由的 mock 回归，证明原失败处理与票价解析未改变。
- [ ] 精确暂存本任务文件并提交 `feat: add strict railway queries for transfer planning`。

## Task 3: 受约束的多次中转搜索

**Files:** 新增 `transfer_planner.py`、`backend/test_transfer_planner.py`；修改 `config.py`。

**Interfaces:**

- `TransferPlanner(stations: TransferStationService, gateway: TransferTicketGateway)`。
- `TransferPlanner.search(request: TransferQueryRequest, now: datetime | None = None) -> TransferSearchResult`。
- 可注入时间和网关响应，测试不连接外部网络。

建议第一版明确以下可配置限制，并原样返回 `meta.limits`：

- 候选便捷站最多 12 个，包含所有指定站；按资料中稳定的枢纽优先级选取。
- 首段限定为用户选择的日期；后续段在首段出发后 72 小时内。
- 单次搜索最多 120 次实际站对/日期请求、45 秒、2000 个扩展状态，返回前 50 条路线。
- 网络请求串行，相邻实际请求至少间隔 200 毫秒；单阶段超时不超过 5 秒及剩余时间。
- 同站对同日期使用单次搜索缓存；进程内短缓存 30 秒、最多 512 个键，附带采集时间。
- 中转搜索同时只允许 1 个正在执行的请求；其他请求由路由返回可理解的繁忙错误。
- 预算用尽、候选缩减、状态或结果截断时均设置 `truncated=true` 及具体原因。

- [ ] 写最小失败用例：A→B→C 的真实电报码衔接、恰好 15 分钟通过、14 分钟过滤、用户 30 分钟及车站更高参考值生效。
- [ ] 运行 `python -m unittest test_transfer_planner -v`，确认失败。
- [ ] 实现带路线标签的分层搜索，状态包含已用中转站、当前实际时间、列车运行标识和已匹配指定站前缀；按剩余换乘次数扩展候选站，达到所选次数后只连接终点。保存多个时间标签，不用单个最低价/最早到达状态替代全部路线。
- [ ] 增加用例：1/2/3 中转分别 2/3/4 段；指定站子序列按顺序匹配；排除同城跨站、重复中转、经过起终点的循环，以及同一运行列车拆段。
- [ ] 增加日期用例：午夜抵达、次日发车、多日慢车、已出发车次过滤、后续查询日期正确；不能把同一个每日列车的不同运行日混为同车，也不能把同一运行的改车次编号视为可靠换车证据。
- [ ] 增加结果用例：每段有允许席别余票；已知价优先选择最低价可售席别；缺价只给 known_price_fen；全程耗时、最早到达、总价排序分别正确且稳定。
- [ ] 增加预算与故障用例：缓存合并重复查询；请求/时间/状态预算停止；部分站对失败保留有效路线及失败元信息；所有失败不能显示成“无票”；候选范围和截断原因可见。
- [ ] 运行任务 1～3 测试，确认通过；精确暂存并提交 `feat: search same-station transfer routes with time and fare constraints`。

## Task 4: 查询 API 与旧功能回归

**Files:** 新增 `transfer_routes.py`、`backend/test_transfer_api.py`；修改 `main.py`。

**Interfaces:** 注册 `/api/transfers` 路由，使用现有 `ApiResponse`；注入 planner 便于测试。

- [ ] 写失败测试：有效 POST 返回 200、参数格式错误返回 422、资料未知的指定站返回 400；缺失路线与部分失败均通过元信息区分。
- [ ] 运行 `python -m unittest test_transfer_api -v`，确认失败。
- [ ] 实现 GET 车站检索与 POST 路线查询；输入车站名称/代码仅按接口约定处理，无法识别明确报错；搜索锁不可用返回 429，提示稍后重试，并保证异常时释放锁。
- [ ] 用 mock 覆盖站对超时、全失败、部分失败、锁释放及默认值；禁止返回上游原始 HTML、Cookie 或敏感日志内容。
- [ ] 同一个 mock TestClient 验证旧 `/api/tickets/query`、`/api/tickets/stops`、`/api/smart-plans/calculate` 仍按旧合同响应。
- [ ] 运行任务 1～4 测试，确认通过；精确暂存并提交 `feat: expose read-only transfer query APIs`。

## Task 5: 中转表单、路线卡片与席别总价

**Files:** 新增前端两个组件、lib、测试；修改 `App.vue`、`package.json`。

**Interfaces:**

- `TransferSearch.vue` props：`initialFrom: string, initialTo: string, initialDate: string`，输入经车站搜索转换为实际电报码。
- `TransferPlanCard.vue` props：`plan`，emit `seat-change({planId, legIndex, seatCode})`；父组件维护所选席别及排序。
- `transfer.js` 导出 `calculateFare(legs, selectedCodes)` → `{totalPriceFen, knownPriceFen}`、
  `sortPlans(plans, sortBy)`、`formatMoney(priceFen)`、`buildTransferText(plan)`、
  `createTransferQueryController(fetchImpl)` → `{search(request), cancel()}`。
- 请求控制器采用 AbortController 与请求序号双重防护，仅接受最后一次查询结果。

- [ ] 写 Node 失败测试：`12350 + 20005 = 32355`；更换席别更新总价；任何一段未知价 total 为 null；价格排序未知合计排末；复制文本包含全部日期、车次与换乘时长。
- [ ] 运行 `node --test tests/transfer.test.mjs`（frontend），确认失败。
- [ ] 实现 lib 与路线卡片。每段只能选择该段有余票且在允许范围内的席别；展示源数据采集时间、分段金额、等待时间和便捷换乘资料链接。
- [ ] 实现表单：1/2/3 中转、默认 15 分钟、指定站有序列表、席别多选、日期和排序；缩小中转数量时明确要求移除多出的指定站，不静默删除。
- [ ] 接入独立“直达查询 / 中转查询”切换，并在直达所选席别无票时提供带入站点、日期和偏好的入口；保留原同车规划。
- [ ] 新增有状态测试：先发请求 A 后发 B，A 最后返回也不能覆盖 B；取消/切换页面停止旧请求；超时和非 JSON 显示可理解错误；调整日期后旧结果有明确失效处理。
- [ ] 增加 `npm test` 脚本调用 `node --test tests/*.test.mjs`；验证 `npm.cmd test` 与 `npm.cmd run build` 均成功。
- [ ] 浏览器验证表单和结果卡片在桌面及手机宽度可用，键盘可操作输入和席别选择，加载/无票/繁忙/部分结果状态清晰。
- [ ] 精确暂存并提交 `feat: add transfer search and per-leg seat fare selection`。

## Task 6: 一体化验收与交付说明

**Files:** 修改 `README.md`；必要的回归补充限于上述测试文件。

- [ ] 使用固定铁路响应，通过真实 API→服务→转换→前端请求合同，覆盖跨日两次中转、指定顺序、15 分钟边界、改选席别与缺价。
- [ ] 运行后端 `python -m unittest test_transfer_stations test_transfer_gateway test_transfer_planner test_transfer_api`；检查退出码及测试总数。
- [ ] 运行前端 `npm.cmd test`、`npm.cmd run build`；仅在新失败或新改动需要时重复。
- [ ] 做一次限速的真实只读查询，分别记录网络是否成功、数据条数、候选范围和是否有有效路线；实时无票或网络受限时如实记录，不据此修改测试成固定通过。
- [ ] README 写明仅查询、1～3 中转、默认 15 分钟、席别选择、站点资料来源、72 小时/候选站范围、部分结果提示、接口与验证命令。
- [ ] 对最终改动做一次整体审查，核对设计 12 个验收场景，尤其检查候选受限时不宣称全国最优、查询异常不宣称无票、没有交易接口或虚构车站资料。
- [ ] 执行 `git diff --check`、精确暂存后 `git diff --cached --check`，核对仅有计划文件；提交 `docs: document transfer query coverage and validation`。
- [ ] 最后核对当前分支、提交和工作区；报告样本测试、浏览器验证及实时查询各自结果。推送或合并按用户后续指示处理。

## 执行方式待选择

建议由当前会话直接按上述顺序执行，因为模型、网关、搜索和页面有连续接口依赖；最后做整体审查。
也可选择子代理逐任务实施及独立审查。用户尚未选择执行方式，此计划未开始执行。
