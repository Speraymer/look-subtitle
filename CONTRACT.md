# 接口契约（给要扩展这套工具的另一个模型看）

这份文件描述的是**已经跑通的现状**，不是设想。所有路径、字段、命令都在本机验证过。

读完你应该能回答三个问题：数据从哪来、每一步的输入输出是什么、要加功能该改哪个文件。

---

## 1. 系统边界

三个进程，两个方向：

```
┌─────────────────┐         POST /report           ┌──────────────────┐
│ Edge 扩展        │ ───────────────────────────▶  │ lk/capture.py    │
│ (extension/)     │                                │ 127.0.0.1:8765   │
│                  │ ◀─── GET /subtitles ────────   │                  │
└─────────────────┘                                └────────┬─────────┘
                                                            │ 追加写
                                                            ▼
                                              captures/probe-YYYYMMDD-HHMM.jsonl
                                                            │
                                                            │ look.py 读
                                                            ▼
                                              works/<sub_id>/（见第 4 节）
```

- 扩展只做三件事：观察页面、把看到的东西 POST 出去、往页面叠一层字幕。
- 本机服务只做两件事：把上报落盘、按 `sub_id` 把字幕发回去。
- 其余全是离线处理，一步一个文件，可以单独重跑。

**没有任何一步需要云端**。平台在内网（`look.tongji.edu.cn` 解析到 192.168.x），出不去。

---

## 2. 扩展上报格式

每次 `POST http://127.0.0.1:8765/report`，body 是 JSON 对象。服务端不校验，直接追加一行到 jsonl。

公共字段（扩展自动加）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `kind` | string | 见下表 |
| `page` | string | 上报时所在的页面 URL（`content.js` 加的） |
| `frame` | string | `top` 或 `iframe` |
| `ts` | string | ISO 时间戳 |
| `tabId` | number | 由 `background.js` 从 sender 补上 |

`sub_id` **不一定有**。`content.js` 发的资源类上报就没有，`ppt.js` 发的才有。
`lk/collect.py::_sub_id_of()` 会兜底从 `page` 的 query 里解析。**这是唯一正确做法，别改成读顶层字段。**

### 2.1 `hello`

content script 注入成功。用来区分"扩展没加载"和"加载了但没注入"。

```json
{"kind":"hello","title":"...","ready":"interactive","page":"https://...","ts":"..."}
```

### 2.2 `resource`

页面发出的媒体请求，来自 `performance.getEntriesByType('resource')`。

```json
{"kind":"resource","url":"https://look.tongji.edu.cn/play/1/.../xxx_1920_1080.mp4?clientUUID=...&t=...",
 "initiatorType":"video","size":300}
```

- 真实文件是**渐进式 MP4 直链**，不是 HLS。`size` 是响应头字节数，不代表文件大小。
- URL 带签名参数：`t=<sub_id>-<过期unix秒>-<md5>`，有效期约 8 分钟，过期返回 403。
- **签名无法本地重算**（md5 的密钥在服务端），过期只能回页面重新抓。
- 不需要 cookie 就能下载（只带 UA + Referer）。

### 2.3 `liveinfo`（可选，当前没成功）

试图从 Vue 实例上挖 `liveInfo`，返回空。保留这个 kind 是为了以后换个挖法。
**不要依赖它**——地址已经能从 `resource` 拿到了。

### 2.4 `ppt-subinfo`

调 `/courseapi/v3/portal-home-setting/get-sub-info` 的结果摘要。

```json
{"kind":"ppt-subinfo","status":200,"rid":"1373568","is_export":"1",
 "sub_title":"2026-09-28第5-6节","lecturer":"邓蓉","duration":"5964",
 "course_type":"multi"}
```

### 2.5 `ppt-pages`（关键）

调 `/spidermaterial/spider-material/web/aitask/async/getPPTData?id=<rid>` 的全量结果。

```json
{"kind":"ppt-pages","status":200,"count":65,
 "pages":[{"t":15000,"img":"https://look.tongji.edu.cn/play/ai/clip/ppt_extraction/.../PPT_15000_0.jpg","type":"7","desc":""}]}
```

- `t` 单位是**毫秒**，是这一页在视频里开始出现的时刻。
- `img` 是平台 AI 从视频里裁出来的画面。**图片本身不需要鉴权**，直接 GET 就能下。
- 图片两种规格：`958×538`（老师电脑的全屏投屏截图，清楚）和 `429×250`（投影幕布的相机照片，糊）。
  比例大约 2:1。文档里对小的那张缩到 9.5cm 并加注。

### 2.6 `ppt-export`

试导出原始课件。目前三种 type 都返回 `{"code":1,"msg":"未找到下载记录"}`，
即系统里没有预生成的课件包。**这条路暂时不通，别在这上面花时间。**

### 2.7 其他

`sw-start` / `sw-installed`：service worker 生命周期，只用来判断扩展是否活着。

---

## 3. 平台接口清单（已知）

| 接口 | 需要登录 | 返回 |
|---|---|---|
| `/courseapi/v3/portal-home-setting/get-sub-info?course_id&sub_id&tenant_code` | 是 | 小节信息，含 `resource_id`、`duration`、`is_export` |
| `/spidermaterial/spider-material/web/aitask/async/getPPTData?id=<resource_id>` | 是 | `[{timestamp(ms), imgurl, describe, type}]` |
| `/pptnote/v1/schedule/search-ppt?course_id&sub_id&page&per_page` | 是 | `{list:[{content(JSON字符串)}], total}` |
| `/courseapi/v2/export/get-courseware-status?type=4&sub_id` | 是 | 课件导出状态（当前无记录） |
| `/courseapi/v3/web-socket/search-trans-result?sub_id&format=json` | 是 | 平台自己的语音转写结果（**这门课没开，返回 403**） |
| `/courseapi/v2/play-template/get-config?tenant_id&sub_id&course_id` | **否** | 播放页模块列表。这门课只有「1个视频流 / AI识别PPT / 课程目录 / 课程笔记 / 学习日志 / 推荐」，没有语音识别模块 |

未登录时的错误形态：`{"code":5003,"msg":"用户未登录或登录信息已过期"}` 或裸 `403 Auth Forbidden`。

**登录态只有扩展拿得到**（`content.js` 在页面 origin 下 `fetch`，自动带 cookie）。
本机 `requests` 拿不到——Edge 的 Cookies 文件是独占锁，复制不出来。

---

## 4. 文件契约

### 4.1 `captures/*.jsonl`

追加写，一行一个上报。**只增不改**。任意时刻可以安全读。
文件名带分钟粒度时间戳，同一分钟内继续追加到同一文件。

### 4.2 `works/<sub_id>/`

| 文件 | 谁写 | 谁读 | 说明 |
|---|---|---|---|
| `meta.json` | `look info/prepare` | 所有步骤 | 从 captures 汇总出来的快照 |
| `video.mp4` | `look fetch` | `transcribe` | 支持 Range 续传，`.part` 临时 |
| `audio.wav` | `look transcribe` | `asr` | 16k / 16bit / 单声道 |
| `segments.json` | `look transcribe` | `look doc`、服务端 `/subtitles` | 见下 |
| `segments.raw.json` | `look polish` 首次运行 | `look polish` | 原始 ASR，只写一次 |
| `review.json` | `look polish` | 人工/模型复核 | 相邻语句与对应课件页文字 |
| `sub.srt` / `sub.vtt` | `look transcribe` | 人 | 标准格式 |
| `ppt/pages.json` | `look info` | `look ppt`、`look doc` | 平台给的 65 条 |
| `ppt/raw/NN.jpg` | `look ppt` | `look doc` | 序号补零，从 `00` 开始 |
| `ppt/crop/NN.jpg` | `look ppt` / `look slides` | `look doc` | 裁过边框；`slides` 会覆盖 |
| `handout.docx` | `look doc` | 人 | 成品 |

`segments.json` 结构：

```json
{"sub_id":"1965530","duration":5964.5,"offset":0.0,
 "segments":[{"start":14.78,"end":21.08,"text":"..."}]}
```

`start`/`end` 单位**秒**（不是毫秒）。服务端 `/subtitles` 原样返回，扩展用二分查找按 `video.currentTime` 命中。

`ppt/pages.json` 就是 `ppt-pages` 里的 `pages` 数组，元素里的 `t` 保持**毫秒**。

**单位不一致是历史原因**：字幕来自音频（秒），画面来自平台（毫秒）。
`deck.build_docx()` 里做了 `/1000` 转换，改这块时注意别重复换算。

---

## 5. CLI 契约

`look.py`，子命令。所有子命令支持省略 `sub_id`（用 `collect.latest_sub_id()`）。

| 命令 | 读 | 写 | 幂等 |
|---|---|---|---|
| `capture` | — | `captures/*.jsonl` | 常驻进程 |
| `info` | `captures/*.jsonl` | `meta.json`、`ppt/pages.json` | 是，覆盖 |
| `fetch` | `meta`/captures | `video.mp4` | 是，存在即跳过（`-f` 重下） |
| `transcribe` | `video.mp4` | `audio.wav`、`segments.json`、`sub.srt/vtt` | 是，同上 |
| `ppt` | `ppt/pages.json` | `ppt/raw/`、`ppt/crop/` | 是 |
| `doc` | `segments.json` + `ppt/crop/` | `handout.docx` | 是，覆盖 |
| `run` | 全部 | 全部 | 是 |
| `slides` | PDF/PPT/PPTX/外部图片目录 | 可信匹配覆盖 `ppt/crop/`，写 `mapping.json` | 是 |
| `polish` | `segments.raw.json`/`segments.json` + 课件 | `segments.json`、`review.json`、字幕 | 是 |

`look doc` 的两个前提：至少有一个画面 **或** 一段字幕。

---

## 6. 外部课件接入

### 6.1 目标

平台抽的图有一部分是拍幕布的照片，糊。如果手上有老师发的原始课件
（QQ 群文件里的 PDF / PPTX），按页渲染成图片，替换掉那些糊图。

### 6.2 已经备好的接口

```powershell
python look.py slides <PDF/PPT/PPTX/图片目录> [sub_id]
```

- PDF 由 PyMuPDF 渲染，PPT/PPTX 由本机 PowerPoint 导出；图片目录按文件名自然序读取。
- 对齐会先比较感知哈希，再对候选页做 ORB + RANSAC 局部特征验证，并用单调路径约束页序。
- 只有特征或连续序列证据达到阈值的页才覆盖 `ppt/crop/NN.jpg`；其余保留平台原图。
- 每一帧的候选页、距离、特征内点数和是否替换写入 `ppt/mapping.json`。

### 6.3 QQ 课件来源核实

仓库在 `integrations/qq_readonly/` 提供可选的本地只读 QQ MCP。它只读取用户明确加入
`allowed_chats` 的群，并固定标记 `history_may_be_incomplete`。代理工作流见
`AGENT_PROMPT.md`：QQ 不可用时必须停下请用户配置，不能跳过版本核实。

该集成只负责找消息、群文件和下载地址；取得原始 PDF/PPT/PPTX 或图片目录后，仍调用
上面的 `slides` 命令完成画面对齐。

判定"对应哪节课"的可用信号（按可靠性排序）：

1. 文件名里的日期 + 节次（`2026-09-28 第5-6节`、`第5讲`）
2. 文件名里的章节号（`第2章`、`Ch03`）
3. 文件修改时间接近上课时间
4. 内容首行标题与平台 `sub_title` 模糊匹配

### 6.4 对齐的正确性检查

`slides` 不以页数一致作为替换依据。页数不等、回放插入摄像头或一页停留多帧时，
仍以画面内容和单调页序匹配；低置信度帧不会替换。最终应抽查 `mapping.json` 中
`confident=true` 的页，尤其是低清摄像头帧。

---

## 7. 失败模式

| 现象 | 原因 | 处理 |
|---|---|---|
| `captures` 里只有 `sw-start`，没有 `hello` | 页面在装扩展**之前**就开着 | 重新加载扩展 + F5 |
| 有 `hello` 没 `resource` | 没点播放 / 视频还没加载 | 播一下再等 |
| `ppt-pages` 没来 | 接口鉴权 / 页面没加载完 | 看 `ppt-error` 那条的 `msg` |
| 下载 403 | 签名过期（约 8 分钟） | 回页面刷新，重新抓 |
| 转写全是空白 | 音频本身没声音 | 用 ffmpeg 查一下 streams |
| 图很糊 | 那一帧是投影幕布相机画面 | 用 `look slides` 换外部课件 |
| `doc` 报"没有画面也没有字幕" | 两个输入都没 | 先 `transcribe` 或 `ppt` |
| 终端里中文乱码 | Windows 代码页 | `chcp 65001` |

---

## 8. 不要动的地方

- **不要给平台发写请求**。整套只读：GET 接口 + 下载图片和视频。任何 POST 到 `look.tongji.edu.cn` 都不该出现。
- **不要把课程内容往外传**。没有云调用，转写是本地模型。
- **不要把 `segments.json` 的秒改成毫秒**。服务端和扩展都按秒解析。
- **不要依赖 `liveinfo` 那条上报**。它是空的，地址从 `resource` 拿。

---

## 9. 代码地图

```
look.py               CLI 入口，子命令分发
lk/paths.py           路径约定（Work 类）+ ffmpeg 定位
lk/capture.py         HTTP 服务（/report /subtitles /view /download /health）
lk/collect.py         jsonl → 结构化 meta
lk/media.py           下载（Range 续传）+ 抽音频
lk/asr.py             SenseVoice + 能量分段（时间戳的来源）
lk/subs.py            段落 → srt/vtt（按字数分配时间）
lk/deck.py            PPT 图下载/裁剪 + Word 排版
extension/
  manifest.json       两个 content_scripts：look 页面、本地字幕页
  content.js          观察资源 + 挖 liveinfo + 上报
  ppt.js              调三个平台接口 + 上报 ppt-pages
  overlay.js          字幕层（拖动/字号/全屏/跳转）
  viewer.js           字幕全文页的点击跳转
  background.js       所有网络动作的代理（不受页面 CSP 限制）
```
