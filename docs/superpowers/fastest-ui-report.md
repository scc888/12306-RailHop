# 最快中转前端实施与验证

日期：2026-10-14。范围：Task 2，仅前端与其固定响应浏览器测试；没有提交代码。

## 已实现

- 桌面与移动端独立“查最快中转”入口；请求 mode=fastest、sort_by=duration，不带 selected_train。旧车次列表及单车次接续/中转路径保留。
- 通过 /api/stations/scope 展示出发/到达实际站复选框；单站模式锁定对应实际站。默认使用 API 建议，并非全城市站默认全选。
- 选择与输入文本一起保存；其他城市输入不能复用旧城市代码。显式空列表保留并阻止请求，刷新后仍可重新勾选。请求 anchor 从选中的代码中取，输入与交换都会重新加载范围。
- “最多换乘”同时发送 max_transfers 和 transfer_count，默认1，最快模式可一键扩大到2次。重查、扩大绕行、扩大次数保留最快模式。
- 最快模式以中转列表为主，直达另作简明对照；同车接续不进入最快中转列表。直达失败显示失败状态，不能解释为无票。
- 摘要显示实际完整经由站、等待、车次/席别、跨日、跨夜候车与未核实便捷换乘；保留原有默认折叠、席别状态及排序后的展开状态。
- 默认最多展示5条，按需展开更多。仅耗时排序首条显示“本次已查范围内最快”；相同耗时少换乘优先。与最快中转的耗时差/等待差按实际数据计算。

## 验证证据

新增 frontend/tests/fastest.test.mjs 的5个行为测试先失败后通过，覆盖范围选择、显式空选择、实际anchor、按输入持久化、相同耗时少换乘及摘要事实。新增浏览器套件先观察到直达混入中转排名的失败，后通过；另追加了空选择刷新后仍可勾选的失败回归并修复。

最终前端 npm test：41/41；npm run build：成功；git diff --check -- frontend：成功。

固定响应 Chrome 浏览器共34组通过：

| 脚本 | 通过组数 | 重点 |
| --- | ---: | --- |
| journey-regressions.cjs | 22 | 原有车次/单车次、席别、价格、跨日、排序、展开保持、取消、切换车次、失败 |
| settings-regressions.cjs | 7 | 桌面滚动、320/390/1024抽屉、短窗口、浏览器重启持久化 |
| dynamic-transfers.cjs | 2 | 桌面/移动任意字典中转站、未知便捷换乘资料 |
| seat-fallback.cjs | 2 | 桌面/移动不适用席别回退及售罄偏好保留 |
| fastest-regressions.cjs | 1 | 最快入口、范围/anchor/持久化/空范围/单站/交换/输入变化、max语义、直达对照、排序/折叠、重试/扩大绕行/扩大次数、范围准备取消、过期POST、初始5条/分页、移动无横溢 |

测试工具模块：D:/tmp/railhop-browser-tools/node_modules/playwright。自有 Vite 地址：http://127.0.0.1:5181（保留运行供主任务复核）。

复现（PowerShell，项目根目录）：

```powershell
$env:PLAYWRIGHT_MODULE='D:/tmp/railhop-browser-tools/node_modules/playwright'
$env:BROWSER_URL='http://127.0.0.1:5181'
node frontend/browser-tests/fastest-regressions.cjs
```

截图：backend/logs/fastest-desktop.png 与 backend/logs/fastest-mobile.png，已目视检查，使用固定响应，未调用真人实时12306余票；截图不能证明真实余票或全局最优。

保留已有 JourneyPlanCard.vue 折叠改动、style.css、journey-regressions.cjs 用户修改。style.css 未做本任务修改。后端代码由其他执行者负责，本任务未改动。

## 独立评审修复

- P2 恢复默认范围：增加浏览器 RED→GREEN 回归。在默认上海/北京输入不变、仅选虹桥后恢复默认，复选框现在立即进入范围重载并恢复上海站；实际提交代码与界面一致。恢复默认先 invalidate/cancel，取消在途查询并清空结果；已取消旧 POST 晚返回不能恢复结果。
- P2 分页导致展开状态丢失：增加7条路线的 RED→GREEN 边界回归。最快方案展开并改选一等座后，价格排序将其移出首5条；“再显示2条”后仍展开且保持一等座。状态按 kind/id 存在 JourneyAlternatives，卡片仅展示受控展开值；新查询结果清空缓存，首次仍默认折叠。

修复后聚焦验证：fastest-regressions.cjs通过；settings-regressions.cjs的7组通过；settings/fastest单元测试9/9；journey-regressions的sort_preserves/fare_visibility/collapse三组通过；最终构建成功，diff check通过。未重复无关浏览器或后端全套。
