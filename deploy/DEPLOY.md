# 12306-RailHop 部署指南

本项目已支持 **Docker 容器化部署（推荐）** 与 **Ubuntu/Debian 原生 systemd 部署**，并已接入 **GitHub Actions 自动化 CI/CD**。

默认前端访问端口：**8080**
后端内部接口端口：**18000**
云服务器公网 IP：`106.13.101.112`
访问地址：`http://106.13.101.112:8080/`

---

## 方式一：GitHub Actions 自动部署（已配置完毕）

当你将代码推送到 GitHub 的 `main` 分支时，GitHub Actions 会自动执行以下流水线：
1. **自动化测试**：运行 Vue 3 前端测试与 FastAPI 130+ 项后端单元测试。
2. **生产构建与打包**：编译前端静态资源，生成轻量级全量发布包（约 190KB）。
3. **安全直传**：通过专属 Deploy Key 安全上传至服务器 `/root/`。
4. **Docker 容器化部署**：服务器解压并执行 `deploy-docker.sh`，构建并启动独立容器 `12306-railhop`。
5. **双重健康验证**：容器内与公网健康检查双重校验，确认服务 100% 正常。

---

## 方式二：服务器手动 Docker 部署（推荐）

如果需要手动在服务器上部署或更新：

### 1. 上传压缩包
将打包生成的 `12306-railhop-<VERSION>.tar.gz` 上传至服务器 `/root/`。

### 2. 执行容器部署脚本
以 root 身份登录服务器：

```bash
cd /root
tar -xzf 12306-railhop-20261014.tar.gz
cd 12306-railhop-20261014
bash deploy-docker.sh
```

脚本将自动完成：
- 停用并清理旧的宿主机 systemd 服务与 nginx 配置（避免端口 8080 冲突）
- 基于缓存层以秒级速度构建并更新 `12306-railhop:latest` Docker 镜像
- 启动独立容器并设置开机自启（`--restart unless-stopped`）
- 自动完成健康检查与接口联通性校验

### 3. 日常 Docker 运维命令

```bash
# 查看容器状态
docker ps -f name=12306-railhop

# 查看容器运行日志（后端与 Nginx）
docker logs -f 12306-railhop

# 重启容器
docker restart 12306-railhop

# 停止容器
docker stop 12306-railhop

# 验证健康状态
curl -fsS http://127.0.0.1:8080/health
```

---

## PostgreSQL 查询缓存（可选）

余票成功响应缓存 15 秒（包含成功的空结果），经停时刻表缓存 12 小时；失败响应不缓存。
直达、同车接续、中转查询共享这些公开数据，席别和实际站点仍按每次请求筛选。
内存缓存有容量上限；配置 PostgreSQL 后可跨进程、重启复用。
数据库不可用时自动回退到内存和铁路接口，并暂缓数据库重连。

已有 PostgreSQL Docker 容器时，在服务器上执行一次：

```bash
python3 deploy/configure-postgres-cache.py pgsql16
```

脚本创建专用 `railhop_cache` 数据库和用户，将随机密码保存在权限为 `600` 的
`/etc/railhop/cache.env`，将数据库所在网络保存在 `/etc/railhop/docker-network`。
现有业务数据库不会被修改；已保存的配置不会被覆盖。
后续 `deploy-docker.sh`（包括 CI 部署）自动读取这两份文件，使应用加入相同网络。
脚本本身不重启应用；首次启用需要部署新版应用。

也可自行设置环境变量 `QUERY_CACHE_DATABASE_URL`（PostgreSQL URI）与
`TICKET_CACHE_SECONDS`（0 关闭余票缓存，最大 30 秒）。缓存表由应用首次使用时自动建立，
数据库用户需要在专用数据库中创建 `railhop_cache` schema 和表的权限。
不要将连接串或密码提交到仓库。

直接使用 Docker Compose 时，设置连接串后执行 `docker compose up -d --build`。
若数据库端口已发布到宿主机，连接串中的主机可使用 `host.docker.internal`；
使用数据库容器名则需让两个服务加入同一个 Docker 网络。

## 方式三：原生 Systemd + Nginx 部署（备选）

若不想使用 Docker，也可使用原生的 Linux 进程托管方式：

```bash
cd /root/12306-railhop-20261014
bash deploy.sh
```

如需更换端口：
```bash
PORT=8081 bash deploy.sh
```

日常服务管理：
```bash
systemctl status railhop.service
journalctl -u railhop.service -f
```

---

## 防火墙与安全组设置

请确保在云控制台（安全组入站规则）以及服务器主机防火墙中放行 **TCP 8080** 端口：

```bash
# 如果启用了 UFW 防火墙：
ufw status
ufw allow 8080/tcp
```
