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
