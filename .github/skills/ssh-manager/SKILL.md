# mcp-ssh-manager 使用指南

通过 MCP 工具 `mcp-ssh-manager` 管理远程服务器。

## 服务器信息

| 项目 | 值 |
|------|-----|
| 服务器名 | `myserver` |
| 主机 | `your-server-ip` |
| 端口 | `your-server-port` |
| 用户 | `root` |
| 认证 | 密码认证 |

## 可用工具

### 文件传输

| 操作 | 工具 | 示例 |
|------|------|------|
| **上传文件** | `ssh_upload` | 上传本地文件到远程路径 |
| **下载文件** | `ssh_download` | 下载远程文件到本地路径 |
| **rsync 同步** | `ssh_sync` | 双向同步目录（需 `sshpass`） |
| **部署文件** | `ssh_deploy` | 上传+自动设置权限+备份 |

### 命令执行

| 操作 | 工具 | 说明 |
|------|------|------|
| **执行命令** | `ssh_execute` | 在远程服务器运行 shell 命令 |
| **sudo 执行** | `ssh_execute_sudo` | 提权执行命令 |
| **批量执行** | `ssh_execute_group` | 多服务器同时执行 |

### 持久会话

| 操作 | 工具 | 说明 |
|------|------|------|
| **开启会话** | `ssh_session_start` | 创建持久 shell 会话 |
| **发送命令** | `ssh_session_send` | 在会话中执行命令（保留工作目录和环境） |
| **关闭会话** | `ssh_session_close` | 结束会话 |
| **列出会话** | `ssh_session_list` | 查看活跃会话 |

### 监控管理

| 操作 | 工具 | 说明 |
|------|------|------|
| **健康检查** | `ssh_health_check` | CPU/内存/磁盘/网络综合检查 |
| **服务状态** | `ssh_service_status` | 检查 nginx/mysql/docker 等服务 |
| **进程管理** | `ssh_process_manager` | 列出/终止进程 |
| **系统监控** | `ssh_monitor` | 实时资源监控 |

### 数据库

| 操作 | 工具 | 说明 |
|------|------|------|
| **查询** | `ssh_db_query` | 执行 SELECT 查询（只读） |
| **列表** | `ssh_db_list` | 列出数据库/表 |
| **导出** | `ssh_db_dump` | 数据库备份 |
| **导入** | `ssh_db_import` | 数据库恢复 |

### 其他

| 操作 | 工具 | 说明 |
|------|------|------|
| **SSH 隧道** | `ssh_tunnel_create/close/list` | 端口转发 |
| **备份管理** | `ssh_backup_create/restore/list/schedule` | 自动备份 |
| **服务器别名** | `ssh_alias` | 管理服务器别名 |
| **命令别名** | `ssh_command_alias` | 管理命令别名 |

## 常用示例

### 文件传输

```json
// 上传文件
ssh_upload(server="myserver", localPath="C:/path/to/file.txt", remotePath="/data/file.txt")

// 下载文件
ssh_download(server="myserver", remotePath="/data/file.txt", localPath="C:/path/to/file.txt")

// 部署文件（自动备份原文件）
ssh_deploy(server="myserver", files=[{local:"C:/path/file.conf", remote:"/etc/app/config.conf"}], options={backup:true, restart:"nginx"})
```

### 命令执行

```json
// 执行命令
ssh_execute(server="myserver", command="ls -la /data")

// 指定工作目录
ssh_execute(server="myserver", command="docker ps", cwd="/opt/app")

// sudo 执行
ssh_execute_sudo(server="myserver", command="systemctl restart nginx")
```

### 持久会话（适合多步操作）

```json
// 1. 开启会话
ssh_session_start(server="myserver", name="deploy-session")

// 2. 发送命令（保留 cd 状态）
ssh_session_send(session="<sessionId>", command="cd /var/www && git pull")

// 3. 继续在相同目录操作
ssh_session_send(session="<sessionId>", command="npm install && npm run build")

// 4. 关闭会话
ssh_session_close(session="<sessionId>")
```

### 健康检查

```json
// 快速检查
ssh_health_check(server="myserver")

// 详细检查
ssh_health_check(server="myserver", detailed=true)

// 检查服务状态
ssh_service_status(server="myserver", services=["nginx", "mysql", "docker"])
```

## 注意事项

- 密码认证的服务器使用 `rsync` 需要本地安装 `sshpass`
- 单文件传输用 `ssh_upload`/`ssh_download` 即可，无需 `sshpass`
- 会话用完记得 `ssh_session_close` 释放资源
- 配置文件在 `~/.ssh-manager/.env`
