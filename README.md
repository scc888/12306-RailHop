# 12306-RailHop · 铁跃 🚄

<div align="center">

**中国境内 12306 智能查票、跨站出行规划与扫码购票系统**  
*A Smart Seat-Hopping, Cross-Station Ticket Planner & Booking System for China Railway 12306.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5+-4FC08D.svg?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-6.0+-646CFF.svg?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-4.0+-38B2AC.svg?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

[功能特性](#-功能特性) • [技术架构](#-技术架构) • [快速开始](#-快速开始) • [接口文档](#-api-接口一览) • [常见问题与风控](#-常见问题与风控须知)

</div>

---

## 📖 项目背景与演进

### 第一版（V1.0）：免登录只读查票与多阶图搜索推算
* 解决直达无票场景下的**车内同车接续换座（全程有座不下车）**与**买短补长**计算。
* 原生逆向解码 12306 `yp_info_new`，零额外 API 请求输出真实票价。

### 第二版（V2.0）：用户会话隔离、官方 App 扫码登录与下单锁座
* **多用户会话隔离**：通过 `SessionManager` 为不同客户端分配独立持久会话，隔离 Cookie 与凭据。
* **12306 官方客户端扫码登录**：直接调取 12306 官方 `create-qr64` 接口，手机端确认授权，免去繁琐易封号的图形滑块逆向。
* **常用联系人自动同步**：拉取账号下乘车人（姓名、脱敏身份证号、旅客类型）。
* **完整购票排队状态机**：贯穿 `submitOrderRequest` $\to$ `initDc` $\to$ `checkOrderInfo` $\to$ `getQueueCount` $\to$ `confirmSingleForQueue` $\to$ `queryOrderWaitTime` $\to$ `resultOrderForDcQueue` 全流程。
* **高铁在线选座（靠窗/过道）**：支持 A/B/C/D/F 选座偏好。
* **未完成订单与 45 分钟支付倒计时**：展示真实分配车厢（如 05 车）、席位号（如 08A 号）与应付金额，并引导旅客至官方完成支付。

---

## ✨ 功能特性

### 1. 📲 官方 App 扫码登录与多会话管理
* 使用手机端【铁路 12306】App 扫一扫授权登录，防风控、零封号风险；
* 后端全自动完成 `uamtk` 与 `uamauthclient` 权签置换，展示当前登录用户名；
* 支持多客户端 Session 隔离与安全登出。

### 2. 👥 常用乘车人同步与多选预订
* 自动同步 12306 账号中的常用联系人；
* 批量勾选乘车人，支持分别配置席别（二等座/一等座/商务座/卧铺等）及票种（成人/儿童/学生）。

### 3. 💺 高铁在线选座（A/B/C/D/F）
* 高铁动车车次支持可视化席位偏好设置：靠窗（A/F）、过道（C/D）等，在提交排队时由铁路系统优先分配。

### 4. ⚡ 自动化购票排队流水线
* 点击“立即预订”一键完成防重 Token 提取、排队余票预检、单程排队提交及轮询等待；
* 成功锁定席位后，立即返回 12306 订单号（如 `E123456789`）。

### 5. ⏳ 待支付订单面板与 45 分钟支付倒计时
* 实时查询 12306 待支付订单，展示具体车厢号、座位号、应付总价及 45 分钟倒计时；
* 支持安全取消未完成订单（严格遵守 12306 每日最多取消 3 次的规则提示）。

### 6. 🔄 智能跨站方案推算（保持 V1 完整能力）
* 针对售罄车次，一键推算**同车换座（1次或2次换座）**、**买短补长**与**买长乘短**；
* 自定义席别白名单与最多购票张数切换。

---

## 🏛️ 技术架构

```mermaid
graph TD
    subgraph 前端单页 [前端 (Vite + Vue 3 + Tailwind CSS)]
        UI[App.vue 响应式单页]
        LoginModal[12306 扫码登录模态框]
        BookingModal[车票预订 & 乘车人/选座抽屉]
        UnpaidModal[待支付订单与倒计时卡片]
        FilterBar[席别偏好 & 最多购票张数控制器]
    end

    subgraph 后端服务 [后端 (Python 3.12 + FastAPI)]
        Routes[API 路由层: routes.py]
        SessionMgr[多用户会话管理: session_manager.py]
        AuthSvc[扫码认证服务: auth_service.py]
        PassengerSvc[联系人服务: passenger_service.py]
        OrderSvc[8步排队购票引擎: order_service.py]
        Planner[跨站推算引擎: smart_planner.py]
        Client12306[免登录公共查询: client_12306.py]
    end

    subgraph 12306 官方服务 [12306 官方集群]
        API_Passport["passport/web (create-qr64 / checkqr / uamtk)"]
        API_AuthClient["otn/uamauthclient (客户端权签)"]
        API_Passenger["otn/confirmPassenger/getPassengerDTOs"]
        API_Order["otn/confirmPassenger (initDc / queue / wait)"]
        API_Query["otn/leftTicket/query (余票与票价)"]
    end

    UI --> Routes
    Routes --> SessionMgr
    Routes --> AuthSvc --> API_Passport
    AuthSvc --> API_AuthClient
    Routes --> PassengerSvc --> API_Passenger
    Routes --> OrderSvc --> API_Order
    Routes --> Planner --> Client12306 --> API_Query
```

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
│   │   │   └── routes.py       # API 端点路由控制器 (含 V1 查票与 V2 认证/订单)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py      # Pydantic 数据规范模型 (车次、方案、乘车人、订单)
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── session_manager.py # 多用户请求会话与凭据隔离管理器
│   │       ├── auth_service.py    # 12306 扫码登录、状态轮询与权签置换
│   │       ├── passenger_service.py # 常用联系人拉取与数据脱敏
│   │       ├── order_service.py   # 8 步排队流水线、在线选座与待支付订单
│   │       ├── client_12306.py    # 免登录公共查询客户端与票价逆向解码
│   │       ├── station_service.py # 3404 个车站字典检索与本地持久化
│   │       └── smart_planner.py   # 智能出行推算引擎 (同车接续、买短、买长)
│   ├── data/
│   │   └── station_name.js     # 本地缓存的 12306 官方车站数据
│   ├── requirements.txt        # 后端依赖清单
│   ├── test_api.py             # FastAPI 端到端测试 (6 项全量通过)
│   └── test_backend.py         # 核心推算服务单元测试
│
└── frontend/                   # Vue 3 + Vite 前端
    ├── index.html              # HTML 模板入口
    ├── vite.config.js          # Vite 配置 (包含对 8000 端口的反向代理)
    ├── package.json            # 前端依赖配置
    └── src/
        ├── main.js             # Vue 挂载入口
        ├── style.css           # Tailwind CSS 样式导入
        └── App.vue             # 完整交互界面 (扫码登录、车次列表、购票抽屉、待支付卡片)
```

---

## 🚀 快速开始

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

### 1. 用户会话与认证接口 (V2)
| 请求方式 | 接口端点 | 功能说明 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/auth/session/init` | 初始化/确认客户端 Session ID | `X-Session-Id` (Header) |
| `GET` | `/api/auth/qr` | 获取 12306 登录二维码图片 (Base64) | `X-Session-Id` (Header) |
| `GET` | `/api/auth/qr/status` | 轮询扫码状态 (等待/已扫/成功/过期) | `X-Session-Id` (Header) |
| `GET` | `/api/auth/status` | 检查当前会话登录状态与用户名 | `X-Session-Id` (Header) |
| `POST` | `/api/auth/logout` | 退出 12306 登录并注销会话 | `X-Session-Id` (Header) |

### 2. 乘车人与购票订单接口 (V2)
| 请求方式 | 接口端点 | 功能说明 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/passengers` | 获取 12306 账号常用乘车人列表 | `X-Session-Id` (Header) |
| `POST` | `/api/orders/submit` | 提交订单排队并锁定席位 | `secret_str`, `passengers`, `choose_seats` |
| `GET` | `/api/orders/unpaid` | 查询未完成（待支付）订单详情 | `X-Session-Id` (Header) |
| `POST` | `/api/orders/cancel` | 取消未完成订单 (每日限 3 次) | `sequence_no` (订单号) |

### 3. 基础查票与跨站推算接口 (V1)
| 请求方式 | 接口端点 | 功能说明 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/stations/search` | 车站拼音/简拼/中文联想搜索 | `keyword`, `limit` |
| `GET` | `/api/tickets/query` | 12306 直达车次余票与各席别票价 | `train_date`, `from_station`, `to_station` |
| `GET` | `/api/tickets/stops` | 指定车次的沿途经停站时刻表 | `train_no`, `from_station`, `to_station`, `depart_date` |
| `GET` | `/api/smart-plans/calculate` | 智能跨站方案推算（换座/买短/买长） | `train_date`, `train_code`, `allowed_seats`, `max_tickets` |

---

## 🧪 自动化测试验证

```bash
# 运行后端全量 API 与 V1/V2 综合测试 (6项全通过)
python backend/test_api.py

# 验证前端生产打包 (Vite)
cd frontend
npm run build
```

---

## ⚠️ 常见问题与风控须知

### Q1：为什么采用官方 App 扫码登录而不是账号密码？
12306 官方近年对网页账号密码登录实施了非常严密的设备指纹与图形验证码风控。直接使用密码登录极易触发验证码失败或账号风控拦截。**采用官方手机 App 扫码登录，经由用户手机端确认授权，完全合法合规、零封号风险且体验流畅。**

### Q2：系统能直接扣款支付吗？
**不能**。为了保障资金安全与合规性，系统仅负责**自动排队与锁定席位**（生成待支付订单）。席位锁定后系统享有 45 分钟保留期，用户需前往【铁路 12306】官方 App、微信小程序或网页完成最终在线支付。

### Q3：为什么取消订单有次数限制？
根据 12306 官方风控规则，单个账号一天内累计主动取消订单达到 **3 次** 后，当天将无法再次在铁路系统中购票。系统在取消订单时会进行显式风险提示。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 许可证开源。
