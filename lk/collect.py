"""从 captures/*.jsonl 里把这个 sub_id 的所有上报捞出来，归成一份 meta。

扩展每发一条就落一行，这里按 kind 合并。同一个 sub_id 反复刷新也没关系，
后出现的覆盖先出现的（比如换了新的播放地址）。
"""

import glob
import json
import os
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from .paths import CAPTURES, Work


def _sub_id_of(d):
    """上报里可能没直接写 sub_id（比如资源请求），就从它所在的页面 URL 里取。"""
    sid = d.get("sub_id")
    if sid:
        return str(sid)
    page = d.get("page") or ""
    if page:
        got = (parse_qs(urlparse(page).query).get("sub_id") or [None])[0]
        if got:
            return str(got)
    return None


def load_reports(sub_id=None):
    """按时间顺序读出所有上报；给了 sub_id 就只留这个。"""
    out = []
    for f in sorted(glob.glob(str(CAPTURES / "*.jsonl"))):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if sub_id and _sub_id_of(d) != str(sub_id):
                        continue
                    out.append(d)
        except OSError:
            continue
    return out


def collect(sub_id):
    """把一个 sub_id 的上报整理成结构化数据。返回 dict。"""
    reps = load_reports(sub_id)
    if not reps:
        return {"sub_id": str(sub_id), "found": False, "reports": 0}

    info = {
        "sub_id": str(sub_id),
        "found": True,
        "reports": len(reps),
        "course_id": None,
        "tenant": None,
        "title": None,
        "lecturer": None,
        "duration": None,
        "resource_id": None,
        "video_urls": [],
        "pages": None,          # [{t(ms), img, type, desc}]
        "captured_at": None,
    }

    for d in reps:
        k = d.get("kind")
        if d.get("course_id"):
            info["course_id"] = str(d["course_id"])
        if k == "hello":
            info["captured_at"] = info["captured_at"] or d.get("ts")
        elif k == "resource":
            u = d.get("url") or ""
            if ".mp4" in u and u not in info["video_urls"]:
                info["video_urls"].append(u)
        elif k in ("ppt-subinfo", "subinfo"):
            info["title"] = info["title"] or d.get("sub_title")
            info["lecturer"] = info["lecturer"] or d.get("lecturer")
            info["duration"] = info["duration"] or d.get("duration")
            info["resource_id"] = d.get("rid") or info["resource_id"]
        elif k == "ppt-pages":
            info["pages"] = d.get("pages") or []

    if info["duration"]:
        try:
            info["duration"] = float(info["duration"])
        except (TypeError, ValueError):
            info["duration"] = None
    return info


def save_meta(info):
    """写 works/<sub_id>/meta.json。"""
    w = Work(info["sub_id"])
    keep = {k: v for k, v in info.items() if k != "found"}
    keep["saved_at"] = datetime.now().isoformat(timespec="seconds")
    # 页面列表单独存，meta 里只留数量和文件位置
    pages = keep.pop("pages", None)
    if pages:
        w.ensure_dirs()
        with open(w.ppt_pages, "w", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False, indent=1)
        keep["ppt_pages_count"] = len(pages)
    with open(w.meta, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=1)
    return keep


def load_meta(sub_id):
    w = Work(sub_id)
    if w.meta.exists():
        with open(w.meta, encoding="utf-8") as f:
            return json.load(f)
    return None


def latest_sub_id():
    """最后收到 hello 的那个 sub_id —— 方便直接敲 `look run`。"""
    best, best_ts = None, ""
    for f in sorted(glob.glob(str(CAPTURES / "*.jsonl"))):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    ts = d.get("ts") or ""
                    sid = _sub_id_of(d)
                    if sid and ts >= best_ts:
                        best, best_ts = str(sid), ts
        except OSError:
            continue
    return best
