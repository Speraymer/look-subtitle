# QQ 只读 MCP 配置

它只提供状态、会话查找、已授权历史、群文件列表和下载地址；没有发送、撤回、删除、加群或改群设置的工具。

## 1. 安装并登录 NapCat

Windows 可从 [NapCatQQ Desktop 官方发布页](https://github.com/NapNeko/NapCatQQ-Desktop/releases) 安装，或按 [NapCatQQ 官方安装包说明](https://napneko.github.io/guide/boot/release) 使用一键包。完成 QQ 扫码登录后，在 NapCat WebUI 新建并启用 OneBot HTTP Server：

- Host：`127.0.0.1`
- Port：`3033`
- Token：自行生成的长随机字符串

WebUI 端口/密码和 OneBot 端口/Token 是两组不同配置。若 WebUI 能打开而 `3033` 不通，通常只是 OneBot HTTP Server 尚未启用。官方配置结构可在 [NapCatQQ OneBot 配置](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-webui-backend/src/onebot/config.ts) 核对。

```powershell
Test-NetConnection 127.0.0.1 -Port 3033
```

## 2. 安装 MCP

```powershell
cd integrations\qq_readonly
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

编辑生成的 `settings.json`：

```json
{
  "api_url": "http://127.0.0.1:3033",
  "api_token": "与 NapCat 完全一致的 token",
  "allowed_chats": ["group:用户明确允许读取的群号"]
}
```

不要把 `settings.json` 提交到 Git；仓库已经忽略它。

## 3. 接入 Codex

把以下内容加入 `%USERPROFILE%\.codex\config.toml`，路径换成当前仓库的绝对路径：

```toml
[mcp_servers.qq_readonly]
command = "C:\\绝对路径\\look-subtitle\\integrations\\qq_readonly\\.venv\\Scripts\\python.exe"
args = ["C:\\绝对路径\\look-subtitle\\integrations\\qq_readonly\\server.py"]
startup_timeout_sec = 30
tool_timeout_sec = 60
```

重启 Codex 后先调用 `qq_readonly.check_status`，再用 `find_chats` 找群。只有用户明确选择的群才能加入 `allowed_chats`；`find_chats` 本身不代表获得历史读取许可。

## 排错

- `6099` 能访问但 `3033` 不通：WebUI 已启动，OneBot HTTP 未启用或端口不同。
- `401/403`：NapCat 和 `settings.json` 的 Token 不一致。
- `online=false`：QQ 尚未完成登录或已掉线。
- 只能看到部分旧消息：QQ 可返回的历史本来可能不完整；输出会固定标记 `history_may_be_incomplete=true`。
- 仍无法连接：停下来让用户检查 NapCat 界面和登录状态，不得绕过 QQ 核实继续生成最终讲义。
