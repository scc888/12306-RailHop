# 12306-RailHop · 铁跃 🚄

<div align="center">

**中国境内 12306 智能查票与跨站出行规划系统**  
*A Smart Seat-Hopping & Cross-Station Ticket Planner for China Railway 12306.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5+-4FC08D.svg?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-6.0+-646CFF.svg?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-4.0+-38B2AC.svg?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

[功能特性](#-功能特性) • [技术架构](#-技术架构) • [快速开始](#-快速开始) • [接口文档](#-api-接口一览) • [常见问题与风控](#-常见问题与风控须知)

</div>

---

## 📖 项目背景与痛点

节假日、周末与春运大客流期间，热门线路（如上海⇋北京、广州⇋长沙、北京⇋西安等）的高铁直达票往往秒空，官方候补队列漫长且兑现成功率难以预期。

广大旅客普遍面临三大痛点：
1. **直达无票，但“分段其实有票”**：同一趟列车可能全程无直达余票，但前半程（如上海→南京南）和后半程（如南京南→北京南）分别有余票。旅客完全可以在车内移步换座直达终点，无需下车出站，但 12306 官方并不支持同一车次的多段余票接续推算。
2. **“买短补长”缺乏智能计算**：旅客不知道买到沿途哪一个经停站刚好有票且起步成本最低，也不知道哪一站有票距离目的地最近、能最大程度享受舒适有座。
3. **第三方工具臃肿且需账号登录**：多数第三方抢票软件要求用户授权 12306 账号密码甚至付费加速包，存在隐私泄露风险。

**12306-RailHop（铁跃）** 旨在打破直达无票死局，基于 12306 公开接口，**免账号登录、免 Token 认证、毫秒级响应**，利用多阶图搜索算法推算出真正能保障出行的备选方案。

---

## ✨ 功能特性

### 同站中转查询（仅查询）

页面新增“中转查询”入口，保留原直达查询与同车接续规划。直达在所选席别下无票时，也可以将站点、日期和席别偏好带入中转页面。

- 选择中转 **1、2、3 个站**，对应 2、3、4 段不同列车；默认 1 个站。
- 默认按**各中转站的 12306 官方参考换乘时间**筛选，不统一设为 15 分钟。可切换自定义时间，并取个人设置与适用官方值中的较大值；没有适用官方数据时，基础参考回退为 15 分钟。
- 仅同站换乘，以实际电报码相接，排除同城跨站、同一运行列车拆段及重复中转站。
- 可输入一个或多个指定中转站，按输入顺序经过；未指定的位置自动规划。
- 每段分别选择可售席别，实时更新分段金额及总价；默认二等座/一等座，不默认接受无座。
- 支持按全程耗时（含等待）、最早到达、当前所选席别总价排序，并复制完整路线。
- 使用完整日期时间处理跨日车次；仅查询可售余票，不将候补当作现票，不提供下单或支付。

便捷换乘资料位于 `backend/data/transfer_stations.json`。首版收录 12 个有公开来源的站：南京南、郑州东、武汉、杭州东、上海虹桥、长沙南、天津西、深圳北、上海、上海南、长春、长春西。每条资料保存来源、发布日期、资料核验日及适用条件；卡片可展开查看。[郑州东站资料示例](https://www.zhengdong.gov.cn/bmdt/8186685.jhtml)。核验日表示资料查阅日期，不能代替通道实时开放状态确认。当前数据保守限定同日到发的 G/D/C 列车换乘；其他站、普速连接及跨夜站内等待不做未经核验的便捷换乘推荐。

**查询范围：**最多 12 个候选站、120 个日期区间请求、45 秒搜索、2000 个扩展状态；后续行程在首段出发后 72 小时内，最多展示 50 条路线。相同区间短缓存 30 秒、最多 512 项，请求间隔至少 200 毫秒。设置位于 `backend/app/config.py` 的 `TRANSFER_*` 项。站点、时间或结果数量受限时，页面显示查询范围及不完整提示，不宣称全国全局最优。多个中转搜索同时提交时，后来的请求收到繁忙提示。

余票及票价为查询快照；缺价展示“票价待确认”与已知金额，不将其计作 0 元。换乘间隔按计划到发时刻计算，不含晚点预测；请结合现场停止检票、行李及步行情况留足时间。

官方换乘时间于 2026-10-10 从 12306 网页实际使用的 `index12306/queryLCtime` 接口逐站采集，只取实际电报码相同的站内换乘记录。当前南京南、上海虹桥等为 15 分钟，上海站为 30 分钟，郑州东为 60 分钟；这些是参考数据，不是全国统一标准。原始响应记录于 `backend/data/transfer_time_reference.json`，各站保存独立的时间来源、采集日及适用日期；搜索按实际接续出发日检查有效范围。这是已采集快照，不会每次搜索实时刷新官方时间，也不能代表通道实时开放状态。

新增接口：

| 方式 | 接口 | 用途 |
| --- | --- | --- |
| GET | `/api/transfers/stations?keyword=njn&limit=20` | 检索已收录便捷换乘站 |
| POST | `/api/transfers/query` | 查询同站有票中转路线 |

```json
{
  "from_station": "AOH",
  "to_station": "VNP",
  "train_date": "2026-10-11",
  "transfer_count": 1,
  "min_transfer_minutes": null,
  "ordered_via_stations": ["NKH"],
  "allowed_seats": ["ze", "zy"],
  "sort_by": "duration"
}
```

站点参数使用实际车站电报码；示例日期需替换为实际出行日期。响应 `data.plans` 为路线，`data.meta` 记录查询次数、范围、失败区间和截断原因；铁路查询失败不会被表示成确定无票。

`min_transfer_minutes` 省略或为 `null` 表示按各站官方参考时间；传入 15～1440 表示个人最少时间，仍不会低于适用官方参考值。每个换乘节点分别返回 `required_minutes`（实际采用阈值）和 `official_min_minutes`（无适用数据时为 `null`）。

验证命令（分别在对应目录执行）：

```powershell
# backend：固定铁路样本测试
python -m unittest test_transfer_stations test_transfer_gateway test_transfer_planner test_transfer_api
# backend：完整测试，包含真实铁路只读接口，依赖当日车次与网络
python -m unittest discover -p "test_*.py"
# frontend
npm test
npm run build
```

本次开发已通过样本/API 测试、桌面及移动端 Chromium 交互检查，并对上海虹桥—南京南—北京南进行了真实只读中转查询。具体测试总数和交付证据记录于 `docs/superpowers/transfer-query-validation.md`；实时查询结果随余票变化。

### 1. 🔄 同车接续 / 车内换座（全程有座不下车）
* **同一车次内部接续**：购买同一趟列车的分段车票。经停中间站时，无需下车出站，在车厢内移步至新座位即可继续前往目的地。
* **严格购票上限控制**：
  * **买 2 张票（默认）**：全程分 2 段行程，车内换座 1 次，体验最佳；
  * **买 3 张票（上限）**：全程分 3 段行程，车内换座 2 次，应对极端无票场景；
  * **坚决剔除买 4 张票（换座 3 次）**的过度折腾方案，保障乘车基本体验。

### 2. 🎫 买短补长（起步成本最低，保底先上车）
* **起步成本最低方案**：推算买到最近有票站上车，解决“无论如何先进站上车”的燃眉之急；
* **舒适度最高方案**：推算买到距离终点最近的有票站，尽量多坐有座区间，后半程在列车上补票；
* **风控提示**：显著标注“春运/严重超员时铁路部门有权停办越站补票”的合规警示。

### 3. ⏩ 买长乘短（提前下车，规避限售）
* 利用铁路局“长途优先放票”机制，自动检索终点站后方的 1~2 个经停站，多买几站并提前在目的地正常刷身份证出站。

### 4. 💰 官方真实票价秒级解码
* 逆向解析 12306 原生 `yp_info_new`（0.1 元基准编码串），**零额外 API 请求开销**，毫秒级直接输出二等座、一等座、商务座、卧铺等精准到元的真实票价。
* 方案卡片同步展示**总票价**以及**各分段票价明细**。

### 5. 💺 自主偏好与白名单过滤
* **席别白名单多选**：二等座、一等座、商务座、动卧、硬卧、软卧、硬座自由勾选，算法严格按用户偏好匹配；
* **购票张数快捷单选**：支持在 `1张 (买短补长)`、`2张 (换座1次·默认)`、`3张 (最多换座2次)` 之间随时切换，方案抽屉自动热刷新。

### 6. 🕒 经停时刻表全景与一键复制
* **横向时间轴**：展开车次即可完整查看始发至终到的所有经停站、发到时刻与停站时间；
* **一键复制**：格式化导出行程步骤、车次、发到时刻、各段席位与分段票价至系统剪贴板。

---

## 🏛️ 技术架构

```mermaid
graph TD
    subgraph 前端单页 [前端 (Vite + Vue 3 + Tailwind CSS)]
        UI[App.vue 响应式单页]
        StationPicker[拼音/汉字联想车站选择器]
        FilterBar[席别偏好 & 最多购票张数控制器]
        PlanDrawer[沿途经停时刻表 & 跨站方案抽屉]
    end

    subgraph 后端服务 [后端 (Python 3.12 + FastAPI)]
        Routes[API 路由层: routes.py]
        Planner[跨站推算引擎: smart_planner.py]
        Client12306[12306 客户端: client_12306.py]
        StationService[车站字典服务: station_service.py]
    end

    subgraph 12306 官方开放接口 [12306 官方服务]
        API_Query["leftTicket/query(G) (余票与票价解码)"]
        API_Stops["czxx/queryByTrainNo (经停时刻表)"]
        API_Names["station_name.js (全量车站字典)"]
    end

    UI --> Routes
    Routes --> StationService --> API_Names
    Routes --> Client12306 --> API_Query
    Client12306 --> API_Stops
    Routes --> Planner --> Client12306
```

### 核心机制亮点
* **免 Token 认证与自适应路由**：12306 接口会在 `queryG`, `queryA` 等动态切换。系统内建 `resolve_c_url` 动态探测，并自动维护匿名 Cookie 会话，遇 302 自动重连。
* **车站字典毫秒检索**：本地缓存 3404 个车站全量数据，支持汉字、全拼、简拼（如 `bjn` 检索 `北京南`）高效前缀匹配。
* **区间缓存与防风控**：推算同一列车方案时，建立局部区间余票缓存 `segment_cache[(i, j)]`，杜绝组合数暴涨带来的冗余查询，防范 IP 频控。

---

## 📁 源码目录结构

```text
12306-RailHop/
├── start.bat                   # 纯 ASCII 格式一键启动脚本 (双开后端与前端并拉起网页)
├── README.md                   # 项目说明文档
├── .gitignore                  # Git 忽略配置
├── backend/                    # Python 3.12 FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI 入口，跨域配置与生命周期管理
│   │   ├── config.py           # 12306 官方接口与全局配置
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes.py       # API 端点路由控制器
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py      # Pydantic 数据规范模型
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── client_12306.py # 12306 客户端封装、Cookie 维持、票价逆向解码
│   │       ├── station_service.py # 3404 个车站字典检索与本地持久化
│   │       └── smart_planner.py   # 智能出行推算引擎 (多阶同车接续、买短、买长)
│   ├── data/
│   │   └── station_name.js     # 本地缓存的 12306 官方车站数据
│   ├── requirements.txt        # 后端依赖清单
│   ├── test_api.py             # FastAPI 端到端自动化测试
│   └── test_backend.py         # 核心服务单元测试
│
└── frontend/                   # Vue 3 + Vite 前端
    ├── index.html              # HTML 模板入口
    ├── vite.config.js          # Vite 配置 (包含对 8000 端口的反向代理)
    ├── package.json            # 前端依赖配置
    └── src/
        ├── main.js             # Vue 挂载入口
        ├── style.css           # Tailwind CSS 样式导入
        └── App.vue             # 完整交互界面 (搜索条、偏好面板、车次卡片、方案抽屉)
```

---

## 🚀 快速开始

### 运行环境
* **Python**：3.10+（开发环境使用 Python 3.12）
* **Node.js**：v18+
* **网络环境**：可正常访问 `kyfw.12306.cn`

### 方式一：一键双击启动（Windows 推荐）
直接在项目根目录下双击运行：
```bat
start.bat
```
脚本将自动在后台拉起后端与前端服务，并在默认浏览器中自动打开界面：
* 前端页面：[http://localhost:5173](http://localhost:5173)
* 后端 API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 方式二：手动命令行启动

#### 1. 启动后端
```bash
cd backend
python -m venv venv
# Windows 激活虚拟环境:
venv\Scripts\activate
# Linux/macOS 激活虚拟环境:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 2. 启动前端
```bash
cd frontend
npm install
npm run dev
```

---

## 📡 API 接口一览

FastAPI 启动后自带 Swagger 交互式文档，可在 `http://127.0.0.1:8000/docs` 直接调试：

| 请求方式 | 接口端点 | 功能说明 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | 服务健康检查与已加载车站数 | 无 |
| `GET` | `/api/stations/search` | 车站拼音/简拼/中文联想搜索 | `keyword` (关键词), `limit` (返回数量) |
| `GET` | `/api/tickets/query` | 12306 直达车次余票与各席别票价 | `train_date`, `from_station`, `to_station` |
| `GET` | `/api/tickets/stops` | 指定车次的沿途经停站时刻表 | `train_no`, `from_station`, `to_station`, `depart_date` |
| `GET` | `/api/smart-plans/calculate` | 智能跨站方案推算（换座/买短/买长） | `train_date`, `train_code`, `train_no`, `from_station`, `to_station`, `allowed_seats`, `max_tickets` |
| `GET` | `/api/tickets/price` | 12306 官方底层票价查询接口 | `train_no`, `from_station_no`, `to_station_no`, `seat_types`, `train_date` |

---

## 🧪 自动化测试验证

项目内置完整的单元测试与端到端测试用例：

```bash
# 运行后端全量 API 与智能推算测试
python backend/test_api.py

# 验证前端生产打包 (Vite)
cd frontend
npm run build
```

---

## ⚠️ 常见问题与风控须知

### Q1：买短补长（先上车后补票）合法合规吗？有何风险？
根据《中国国家铁路集团有限公司铁路旅客运输规程》，旅客在车票到站前要求越过到站继续乘车时，应在原车票到站前主动向列车工作人员提出，并核收越站区间的票价和手续费。  
**特别风险提示**：在春运、国庆等极端客流高峰期，若列车出现严重超员甚至引发安全报警时，**铁路部门有权根据安全规程在车内暂停办理越站补票**，并可能组织越站旅客就近下车。请广大旅客务必结合具体出行时间与列车实际拥挤程度审慎使用买短补长方案。

### Q2：同车换座需要下车出站重新安检吗？
**不需要**。由于所购车票属于同一列车号，到达第一段的终点站（即第二段的起点站）时，列车仅作短暂中途停靠。旅客无需下车出站，只需带好随身行李，在车厢内直接移步至第二张车票对应的座位坐下即可。

### Q3：为什么不推荐车内换座 3 次以上？
车内换座 3 次意味着旅客需要购买 4 张车票，在 3 个不同的停靠站搬运行李调换车厢。这不仅乘车体验极差、容易造成行程混乱，而且由于 12306 席位锁定规则，成功出票的概率极低。因此系统坚决将购票张数上限限制为最多 3 张票。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 许可证开源。所有最终购票、支付、改签及退票操作均需在铁路官方渠道完成。
