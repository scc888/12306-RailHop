# 12306-RailHop 手动上传部署说明

部署包：`12306-railhop-20261014.tar.gz`，对应当前项目提交 `10353b5`。

适用环境：Ubuntu 22.04 / 24.04 或其他提供 Python 3.10+ 的 Debian/Ubuntu 系统，使用 systemd，由 root 执行。服务器需要能连接软件源、Python 包源和 12306；包内已包含生产前端和车站数据，无需 Node.js、数据库、Docker。

默认网页端口为 **8080**，后端仅监听 **127.0.0.1:18000**。脚本新增 `/etc/nginx/conf.d/railhop.conf`，保留现有 Nginx 站点和 80/443 端口配置。如果服务器不是上述 Linux 环境，请先确认系统再使用脚本。

## 1. 上传压缩包

通过云控制台文件上传，或使用你惯用的 SFTP 工具，以 root 登录 `106.13.101.112`，把 `12306-railhop-20261014.tar.gz` 上传到服务器 `/root/` 目录。只上传这个压缩包即可，不需要上传整个开发目录。

## 2. 在服务器执行

通过云控制台终端或自己已确认服务器身份的 SSH 连接执行：

```bash
cd /root
tar -xzf 12306-railhop-20261014.tar.gz
cd 12306-railhop-20261014
bash deploy.sh
```

首次执行会按需安装 Python、venv、Nginx 等系统组件，并联网安装锁定版本的 Python 依赖。出现 `Deployment complete` 表示本机的网页、健康检查和车站接口验证通过。

脚本创建独立 `railhop` 系统用户；应用安装到 `/opt/12306-railhop/releases/`，`current` 指向本次版本，启用 `railhop.service` 开机自启和进程失败重启。激活时发生错误会尝试恢复原有 RailHop 服务、站点配置和版本指向；依赖安装的系统包不会卸载，发布目录和备份保留。

如果 8080 被其他程序占用，换一个空闲端口：

```bash
PORT=8081 bash deploy.sh
```

后端端口冲突可设置 `BACKEND_PORT=18001`；例如：

```bash
PORT=8081 BACKEND_PORT=18001 bash deploy.sh
```

脚本拒绝覆盖同名但不属于本部署的服务或站点配置。失败后根据错误信息处理，不要删除现有站点。

## 3. 放行端口并访问

在云服务器的安全组入站规则中放行 **TCP 8080**（若改成 8081，就放行 8081）。来源范围按你实际需要访问的人群设置。

如果服务器启用了 UFW，再允许对应端口：

```bash
ufw status
# 仅在 UFW 为 active 时按需执行；无需启用或重置防火墙
ufw allow 8080/tcp
```

其他主机防火墙应按实际规则单独放行该端口。不要开放 18000 或 18001，后端通过 Nginx 访问。

浏览器打开：

**http://106.13.101.112:8080/**

该方式使用 HTTP；若需要域名和 HTTPS，后续将域名解析到本机，并为本网站单独配置证书。

## 4. 验证与日常管理

```bash
# 服务状态、健康检查、站名检索
systemctl status railhop.service --no-pager
curl -fsS http://127.0.0.1:8080/health
curl -fsS 'http://127.0.0.1:8080/api/stations/search?keyword=shanghai&limit=5'

# 查看日志
journalctl -u railhop.service -n 100 --no-pager
journalctl -u railhop.service -f

# 重启 / 停止
systemctl restart railhop.service
systemctl stop railhop.service

# 查看本次版本及配置备份
readlink -f /opt/12306-railhop/current
ls /opt/12306-railhop/deployment-backups
```

页面打不开：先确认 `curl http://127.0.0.1:8080/health` 是否成功。服务器本机可访问而外网不可访问时，检查安全组和主机防火墙是否放行了实际网页端口。

页面正常但实时查票失败：检查后端日志以及服务器到 `kyfw.12306.cn` 的网络。健康检查和车站检索正常，不代表实时余票查询一定成功；部署完成后请在网页用预售范围内日期实际查询一次。服务器的出口网络、铁路接口限制和接口服务状态都可能影响实时查询。

已有 80/443 站点的 502 错误不会被本部署修复；新项目使用独立端口访问。

## 包内容及验证边界

- `backend/app`：后端运行代码；`backend/data`：车站、城市坐标、换乘参考数据。
- `backend/requirements.lock`：本机已验证的 Python 依赖版本；`backend/requirements.txt`：项目原始依赖声明。
- `frontend/dist`：构建好的生产页面。
- `deploy.sh`、两个配置模板：安装和启动配置。
- `release-manifest.json`、`SHA256SUMS`：来源及包内文件校验。
- `LICENSE`：项目许可。

未包含服务器密码、SSH 私钥、日志、开发虚拟环境或 node_modules。打包完成前进行本地生产构建、脚本语法及包完整性验证；本安装脚本尚未在你的服务器执行，实时查询需部署后核实。
