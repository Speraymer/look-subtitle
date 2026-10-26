# look-subtitle

把同济 Look 课程回放变成本地字幕和 Word 讲义，并用老师发布的高清课件替换低清摄像机画面。语音、视频和课件都留在本机。

## 功能

- 浏览器扩展抓取回放地址与平台 PPT 画面，并在播放器上显示字幕
- SenseVoice 本地转写，输出 `segments.json`、SRT 和 VTT
- 自动删除“这个这个”、连续同义复述以及“呃”“没毛病”等独立口癖
- 按画面内容和页序把低清截图匹配到 PDF/PPT/PPTX 高清原页
- 生成带画面和讲解的 Word 讲义与逐段复核材料
- 可选的只读 QQ MCP：核实老师是否补发课件、勘误或更正

## 安装

需要 Windows、Python 3.11+；处理 PPT/PPTX 时需要本机 PowerPoint，PDF 不需要 Office。

```powershell
git clone <仓库地址>
cd look-subtitle
python -m pip install -r requirements.txt
python look.py model
```

首次模型下载约 1 GB。随后在 Edge 打开 `edge://extensions`，启用“开发人员模式”，选择“加载解压缩的扩展”，指向 `extension` 目录。

## 处理一节回放

```powershell
python look.py capture
```

保持窗口运行，打开课程回放并刷新页面。看到 `ppt-pages` 和 `resource` 后：

```powershell
python look.py run
python look.py slides "老师发布的课件.pdf"
python look.py polish "老师发布的课件.pdf"
python look.py doc
```

产物位于 `works/<sub_id>/`：

- `segments.raw.json`：首次 `polish` 时保存的原始转写
- `segments.json`、`sub.srt`、`sub.vtt`：清理后的字幕
- `review.json`：相邻语句、对应课件页文字和画面索引
- `ppt/mapping.json`：高清页匹配证据与置信度
- `handout.docx`：讲义

省略 `sub_id` 时使用最近抓到的回放；所有命令也可显式附上 `sub_id`。

## QQ 课件核实

公开版附带一个权限收紧的只读 QQ MCP。安装与 NapCat/OneBot 配置见 [integrations/qq_readonly/README.md](integrations/qq_readonly/README.md)。它默认不能读任何聊天，只有用户明确允许并写入 `allowed_chats` 的群才能读取历史；历史可能不完整。

让另一个代理完整处理回放时，直接把 [AGENT_PROMPT.md](AGENT_PROMPT.md) 作为任务提示词。提示词已要求：QQ 不通就停下询问、对照两个课程群确认课件版本、结合 PPT 和上下文修正磕巴，但不擅自改写课程特有的 Unix V6++ 内容。

## 常用命令

| 命令 | 作用 |
|---|---|
| `python look.py capture` | 启动本地服务，接收扩展上报 |
| `python look.py info` | 查看抓取结果 |
| `python look.py fetch` | 下载视频 |
| `python look.py transcribe` | 抽取音频并本地转写 |
| `python look.py ppt` | 下载并裁剪平台 PPT 画面 |
| `python look.py slides <课件>` | 匹配高清课件页，只替换可信结果 |
| `python look.py polish <课件>` | 清理口语并生成 `review.json` |
| `python look.py doc` | 生成 Word 讲义 |
| `python look.py run` | 顺序执行基础流程，已有文件跳过 |

## 安全与限制

- `.gitignore` 排除了课程视频、课件、转写、模型、日志、QQ 配置和 Token。
- QQ MCP 只有读取工具，并再次以 `allowed_chats` 限制历史和群文件访问。
- 平台视频地址带短时签名；若下载返回 403，回到课程页刷新后重新抓取。
- `polish` 只自动处理高置信度口癖与相邻重复；含义不确定的内容保留在 `review.json` 供复核。
- 课程材料请仅在获得授权的范围内使用和分享。

详细数据格式与模块边界见 [CONTRACT.md](CONTRACT.md)。项目采用 [MIT License](LICENSE)。
