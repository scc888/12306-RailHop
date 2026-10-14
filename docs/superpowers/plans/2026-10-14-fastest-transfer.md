# 最快中转实施方案

用户已确认：最快是首程出发到末程到达的总耗时，包含等待；增加直接查询入口、可见的端点车站范围、最多换乘次数、直达对照及折叠卡片摘要。结果仅称本次已查范围内最快。

## 共同约束与接口

- 只做查询；每段真实有票；中途严格实际电报码同站匹配；个人最少换乘时间优先；保留现有未提交修改。
- `TransferQueryRequest` 新增可选 `max_transfers: int | None`（1～3）。缺省时 `transfer_count` 继续表示恰好换乘次数；提供时搜索1～max_transfers次，共用一个查询/时间预算。指定站数量不得超过有效上限。
- 新增可选 `from_station_codes` / `to_station_codes`，均为电报码数组。提供时必须非空、包含对应 anchor、属于相同官方城市分组；station 范围只能选 anchor。不提供时沿用旧范围逻辑。
- `JourneyQueryRequest.mode` 新增 `fastest`：不绑定首程，按 duration 查询；查询直达作为对照、查询中转、跳过同车接续。响应 `scope.mode` 表示模式。
- `GET /api/stations/scope?station_code=SHH` 返回 ApiResponse，data 为 `{city_name, stations: StationInfo[], default_station_codes: string[]}`。候选按官方城市字段分组。默认选择城市同名车站及用户输入的 anchor；另保留武汉等明确的主要客站别名。其余车站可手动勾选。默认选择不声称车站位于市中心。
- 所有旧入口与缺省请求兼容；查询失败不能视为无票。

## Task 1 — 后端搜索（worker）

所有权：`backend/app/services/transfer_planner.py`、`transfer_candidates.py`；对应 `test_transfer_planner.py`、`test_dynamic_transfers.py`、`test_city_search.py`，可新增独立 planner 测试文件。不修改请求模型、journey_service、station_service 或 API 文件。

修复有限预算漏掉较快方案：以站对+日期复用查询，各候选完整路线均衡推进；不要让一条前缀穷举72小时后才考虑其他站。日期任务按首程出发后的可靠耗时下界排序，不能机械偏爱当天；保留晚出发而历时短的前缀。支持上述可选 max_transfers；每层结果与继续中转共享预算。候选发现优先实际时刻较快的相关列车，兼顾多种经停路线；车站顺序不要只依赖电报码。城市端点应覆盖明确的选中实际站，保留范围说明。不可单纯提高限制修复。

先写并观察失败测试：32站/120请求时，首站600分钟而末站165分钟必须找到；短前程长等待与晚出发快全程；跨午夜；最多2次同时返回1和2次、旧exact不变；不同实际端点覆盖及严格中途同站；query/time/state预算。保留原有缓存、指定站顺序、席别和自定义时间行为。

## Task 2 — 前端（worker）

所有权：`frontend/src` 中相关组件/lib、前端单元测试及 browser-tests。保留已有 JourneyPlanCard.vue 的折叠实现、style.css 及浏览器测试中的未提交修改。不得修改后端。

增加“查最快中转”独立按钮，直接发 mode=fastest、sort_by=duration，不带selected_train；现有查车次和单车次方案继续可用。可见可调整的出发/到达站范围通过上述 scope API 加载；station 模式严格单站；默认非全行政城市选中，选中列表为空须提示，输入变化/交换要正确重置范围；请求 anchor 使用选中站之一。用户勾选应稳定持久化，避免旧城市范围污染新输入。

换乘设置显示“最多换乘”，发送 max_transfers，同时保留 transfer_count 字段以兼容；默认1，提供扩大到2次的快捷操作。最快模式默认显示中转，直达用独立简明对照展示，不混淆最快中转排名。重试/扩大绕行/扩大次数保持最快模式。最短耗时同值时少换乘优先。

折叠摘要显示完整实际路线、中转站/等待、跨日、总耗时、价格与席别摘要；显示未核实换乘、跨夜候车等具体事实。首条只在duration排序时标“本次已查范围内最快”；首屏3～5条，详情保持默认折叠；提供有依据的与最快方案耗时差/等待差，避免无依据安全判断或任意硬过滤。

通过单元测试与可运行浏览器回归验证入口请求、scope选择、max语义、摘要可见/折叠保持、模式重试与排序。

## Task 3 — 契约与编排（root）

所有权：请求模型、`journey_service.py`、`station_service.py`、`api/routes.py`、`api/transfer_routes.py`、独立契约/集成测试。实现共同接口、scope默认与校验、fastest编排和直达对照。先失败测试后实现。保留已有诊断日志代码。

## 验证与评审

检查每个任务边界的接口一致性；后端离线全套、前端测试/构建、固定响应浏览器回归；独立代码复查。真人实时铁路查询未执行时明确说明，不把fixture当真实余票。完成后仅保留本次改动和原有未提交内容，不自动提交或推送。

## 决策记录

- 当前 checkout 有用户未提交内容，切到 `codex/fastest-transfer-20261014` 就地改动以保留并验证该基线。
- 搜索与前端文件归不同执行者，契约归 root；接口以上述字段为准，可以并行，不互相覆盖。
- 相同地名词首仅用于初始勾选建议，城市归属始终使用官方城市字段；用户可检查或修改实际车站列表。
