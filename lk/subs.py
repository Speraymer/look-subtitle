"""段落 -> 字幕：按标点切句、按字数分配时间，输出 srt / vtt。"""

import json
import re

MAX_CHARS = 20
MIN_DUR = 0.8
SENT_END = "。！？；…!?;"
SOFT = "，、,"


def split_long(text, limit=MAX_CHARS):
    out = []
    while len(text) > limit:
        cut = limit
        for i in range(limit, max(limit // 2, 1), -1):
            if text[i] in SOFT + " ":
                cut = i + 1
                break
        out.append(text[:cut])
        text = text[cut:]
    if text:
        out.append(text)
    return out


def clauses(text):
    parts = re.split(f"(?<=[{SENT_END}])", text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= MAX_CHARS:
            out.append(p)
            continue
        subs = re.split(f"(?<=[{SOFT}])", p)
        cur = ""
        for s in subs:
            if len(cur) + len(s) <= MAX_CHARS:
                cur += s
            else:
                if cur:
                    out.append(cur)
                cur = s
        if cur:
            out.extend(split_long(cur))
    return out


def to_entries(segments):
    entries = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        cs = clauses(text)
        total = sum(len(c) for c in cs) or 1
        span = max(0.4, seg["end"] - seg["start"])
        t = seg["start"]
        for c in cs:
            d = span * len(c) / total
            entries.append({"start": t, "end": t + d, "text": c})
            t += d

    merged = []
    for e in entries:
        if merged and (e["end"] - e["start"]) < MIN_DUR:
            prev = merged[-1]
            if e["start"] - prev["end"] < 0.3 and len(prev["text"]) + len(e["text"]) <= MAX_CHARS * 1.6:
                prev["text"] += e["text"]
                prev["end"] = e["end"]
                continue
        merged.append(dict(e))
    for i, e in enumerate(merged):
        if i and e["start"] < merged[i - 1]["end"]:
            e["start"] = merged[i - 1]["end"]
        if e["end"] <= e["start"]:
            e["end"] = e["start"] + 0.4
    return merged


def fmt(ts, sep=","):
    h, m, s = int(ts // 3600), int(ts % 3600 // 60), int(ts % 60)
    ms = int(round((ts - int(ts)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(entries, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\n{fmt(e['start'])} --> {fmt(e['end'])}\n{e['text']}\n\n")


def write_vtt(entries, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for e in entries:
            f.write(f"{fmt(e['start'], '.')} --> {fmt(e['end'], '.')}\n{e['text']}\n\n")


def build(segments_json, srt_path, vtt_path):
    with open(segments_json, encoding="utf-8") as f:
        data = json.load(f)
    entries = to_entries(data["segments"])
    write_srt(entries, srt_path)
    write_vtt(entries, vtt_path)
    print(f"  字幕 {len(entries)} 行 -> {srt_path.name} / {vtt_path.name}")
    return entries
