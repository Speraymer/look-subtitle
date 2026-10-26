"""look —— 给录播课做字幕和讲义。

  python look.py capture                起本地服务，等浏览器扩展上报
  python look.py info                   看看抓到了什么
  python look.py fetch                  下视频
  python look.py transcribe             转写
  python look.py ppt                    下 PPT 画面
  python look.py doc                    出 Word 讲义
  python look.py run                    一条龙（上面几步按顺序跑，已有的跳过）
  python look.py slides <课件或图片目录> 用高清课件按内容匹配平台画面
  python look.py polish <课件>           结合课件上下文清理口语并生成复核材料
  python look.py model                  下载语音模型（首次约 1GB）
"""

import argparse
import json
import os
import sys

# Windows 终端默认 GBK，遇到 ✓ 这种符号会直接崩；这里兜住
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8mb4"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lk import __version__
from lk.collect import collect, latest_sub_id, load_meta, save_meta
from lk.paths import Work


def _sid(args):
    sid = args.sub_id or latest_sub_id()
    if not sid:
        raise SystemExit("不知道是哪一节课：先 `look capture`，在课程页按 F5，或者写明 sub_id")
    return str(sid)


def _prepare(args):
    """抓一次 meta（每次跑都刷新，方便换了地址后重来）。"""
    sid = _sid(args)
    info = collect(sid)
    if not info["found"]:
        raise SystemExit(f"captures 里没有 sub_id={sid} 的上报——先把课程页刷一遍")
    save_meta(info)
    return sid, info


# ---------- 各步 ----------

def cmd_capture(args):
    from lk.capture import serve

    serve(args.port)


def cmd_info(args):
    sid = args.sub_id or latest_sub_id()
    if not sid:
        raise SystemExit("还没有任何上报")
    info = collect(str(sid))
    if not info["found"]:
        raise SystemExit(f"没有 sub_id={sid} 的上报")
    print(f"sub_id     {info['sub_id']}")
    print(f"course_id  {info['course_id']}")
    print(f"标题       {info['title']}")
    print(f"讲师       {info['lecturer']}")
    print(f"时长       {info['duration']}s")
    print(f"resource   {info['resource_id']}")
    print(f"视频地址   {len(info['video_urls'])} 个")
    for u in info["video_urls"][-2:]:
        print("   ", u[:110])
    pages = info.get("pages") or []
    print(f"PPT 画面   {len(pages)} 个" + (f"，第一个在 {pages[0]['t']}ms" if pages else ""))
    if len(sys.argv) > 1 and "--pages" in sys.argv:
        for p in pages[:10]:
            print("   ", p["t"], p["img"][-46:])
    w = Work(str(sid))
    for name, p in (("视频", w.video), ("音频", w.audio), ("转写", w.segments),
                    ("PPT图", w.ppt_raw), ("讲义", w.docx)):
        mark = "✓" if p.exists() else "·"
        print(f"  {mark} {name:<4} {w.rel(p) if p.exists() else '-'}")


def cmd_fetch(args):
    sid, info = _prepare(args)
    from lk import media

    w = Work(sid)
    v = media.fetch_video(info, force=args.force)
    if v:
        dur, vinfo = media.probe(v)
        print(f"  时长 {dur:.0f}s" if dur else "  时长未知")
        if vinfo:
            print("  " + vinfo[:110])


def cmd_transcribe(args):
    sid, info = _prepare(args)
    from lk import asr, media, subs

    w = Work(sid)
    if not w.video.exists():
        raise SystemExit("没有 video.mp4，先 `look fetch`")
    if not asr.ensure_model(download=not args.no_download):
        raise SystemExit("模型不可用")
    media.extract_audio(w.video, w.audio, force=args.force)
    asr.transcribe(w.audio, w.segments, threads=args.threads,
                   start=args.start, end=args.end, sub_id=sid)
    subs.build(w.segments, w.srt, w.vtt)


def cmd_ppt(args):
    sid, info = _prepare(args)
    from lk import deck

    w = Work(sid)
    if not w.ppt_pages.exists():
        raise SystemExit("没有 PPT 画面数据（平台没抽帧，或者扩展那一步没跑）")
    deck.download_pages(w, force=args.force)
    deck.crop_pages(w)


def cmd_doc(args):
    sid, _ = _prepare(args)
    from lk import deck

    w = Work(sid)
    deck.build_docx(w, title=args.title, subtitle=args.subtitle, note=args.note)
    print(f"\n{w.docx}")


def cmd_run(args):
    sid, info = _prepare(args)
    from lk import asr, deck, media, subs

    w = Work(sid)
    print(f"[1/5] 视频")
    if not media.fetch_video(info, force=args.force):
        raise SystemExit("下载失败")
    print(f"[2/5] 音频")
    media.extract_audio(w.video, w.audio, force=args.force)
    print(f"[3/5] 转写")
    if asr.ensure_model(download=not args.no_download):
        asr.transcribe(w.audio, w.segments, threads=args.threads, sub_id=sid)
        subs.build(w.segments, w.srt, w.vtt)
    else:
        print("  跳过（模型不可用）")
    print(f"[4/5] PPT 画面")
    if w.ppt_pages.exists():
        deck.download_pages(w, force=args.force)
    else:
        print("  没有画面数据，讲义里只会有文字")
    print(f"[5/5] 讲义")
    deck.build_docx(w, title=args.title, subtitle=args.subtitle, note=args.note)
    print(f"\n完成：{w.docx}")


def cmd_slides(args):
    sid, _ = _prepare(args)
    from lk import deck

    w = Work(sid)
    deck.use_external_slides(w, args.source, args.map)


def cmd_polish(args):
    sid, _ = _prepare(args)
    from lk import polish, subs

    w = Work(sid)
    polish.polish(w, args.source, args.corrections)
    subs.build(w.segments, w.srt, w.vtt)


def cmd_model(args):
    from lk import asr

    print("模型就绪" if asr.ensure_model() else "模型不可用")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="look", description=f"录播课字幕/讲义工具 v{__version__}")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, force=False, no_download=False, threads=10, title=None):
        if force:
            p.add_argument("-f", "--force", action="store_true", help="忽略已有文件重做")
        if no_download:
            p.add_argument("--no-download", action="store_true", help="不自动下模型")
        if threads:
            p.add_argument("--threads", type=int, default=threads, help="识别线程数")
        if title:
            p.add_argument("--title", help="讲义标题")
        p.add_argument("sub_id", nargs="?", help="小节 id，默认取最近一次")

    p = sub.add_parser("capture", help="起本地服务，等扩展上报")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("info", help="看抓到了什么")
    p.add_argument("sub_id", nargs="?")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("fetch", help="下视频")
    common(p, force=True)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("transcribe", help="转写并出字幕")
    common(p, force=True, no_download=True)
    p.add_argument("--start", type=float, help="只转这一段（调试用）")
    p.add_argument("--end", type=float)
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("ppt", help="下 PPT 画面")
    common(p, force=True)
    p.set_defaults(func=cmd_ppt)

    p = sub.add_parser("doc", help="出 Word 讲义")
    common(p, title=True)
    p.add_argument("--subtitle", help="副标题（日期/讲师）")
    p.add_argument("--note", help="标题下的一行小字说明")
    p.set_defaults(func=cmd_doc)

    p = sub.add_parser("run", help="一条龙")
    common(p, force=True, no_download=True, title=True)
    p.add_argument("--subtitle")
    p.add_argument("--note")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("slides", help="用高清课件按内容匹配并替换抽帧图")
    p.add_argument("source", help="PPT/PPTX/PDF 或已导出的图片目录")
    p.add_argument("--map", help='JSON：{"0":12,"1":13} 手动对齐')
    p.add_argument("sub_id", nargs="?")
    p.set_defaults(func=cmd_slides)

    p = sub.add_parser("polish", help="结合课件上下文清理转写并生成 review.json")
    p.add_argument("source", help="PPT/PPTX/PDF；用于提取每页文字")
    p.add_argument("--corrections", help="JSON：全局替换和逐段人工修订")
    p.add_argument("sub_id", nargs="?")
    p.set_defaults(func=cmd_polish)

    p = sub.add_parser("model", help="下载语音模型")
    p.set_defaults(func=cmd_model)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
