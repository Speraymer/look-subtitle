"""下视频、抽音频。两个都有断点/跳过逻辑，重跑不会浪费。"""

import subprocess
import time
from pathlib import Path

import requests
import urllib3

from .paths import Work, ffmpeg_exe

urllib3.disable_warnings()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
)
BASE_HEADERS = {"User-Agent": UA, "Referer": "https://look.tongji.edu.cn/"}


def download(url, dest: Path, headers=None, force=False, quiet=False):
    """带 Range 续传的下载。返回 True/False。"""
    dest = Path(dest)
    part = dest.with_suffix(dest.suffix + ".part")
    if dest.exists() and not force:
        if not quiet:
            print(f"  已存在，跳过：{dest.name} ({dest.stat().st_size/1048576:.1f} MB)")
        return True

    have = part.stat().st_size if part.exists() else 0
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    if have:
        h["Range"] = f"bytes={have}-"

    r = requests.get(url, headers=h, stream=True, verify=False, timeout=60)
    if r.status_code not in (200, 206):
        print(f"  HTTP {r.status_code}: {r.text[:160]}")
        return False
    total = None
    cr = r.headers.get("content-range")
    if cr and "/" in cr:
        total = int(cr.split("/")[-1])
    elif r.headers.get("content-length"):
        total = have + int(r.headers["content-length"])
    mode = "ab" if (have and r.status_code == 206) else "wb"
    if mode == "wb":
        have = 0

    t0 = time.time()
    got = have
    last = 0.0
    with open(part, mode) as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
            got += len(chunk)
            if not quiet and time.time() - last > 4:
                last = time.time()
                sp = (got - have) / max(1e-6, time.time() - t0) / 1048576
                pct = f"{got*100/total:.0f}%" if total else "?"
                print(f"  {got/1048576:7.1f} MB  {pct:>4}  {sp:.1f} MB/s", flush=True)
    if total and part.stat().st_size < total:
        print(f"  没下完 {part.stat().st_size}/{total}，重跑会接着下")
        return False
    part.replace(dest)
    if not quiet:
        print(f"  完成 {dest.name}  {dest.stat().st_size/1048576:.1f} MB  {time.time()-t0:.0f}s")
    return True


def fetch_video(info, force=False):
    """info 来自 collect.collect()，取最后一个可用地址。"""
    w = Work(info["sub_id"])
    urls = info.get("video_urls") or []
    if not urls:
        print("  没有抓到视频地址——先在课程页按 F5，等扩展上报")
        return None
    last = None
    for u in reversed(urls[-3:]):
        if download(u, w.video, force=force):
            return w.video
        last = u
    print(f"  所有地址都失败，最后一个：{last[:100] if last else '-'}")
    return None


def extract_audio(video: Path, wav: Path, force=False):
    """16k 单声道 PCM，SenseVoice 吃这个。"""
    video, wav = Path(video), Path(wav)
    if wav.exists() and not force:
        print(f"  音频已存在，跳过：{wav.name} ({wav.stat().st_size/1048576:.0f} MB)")
        return wav
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav),
    ]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("  ffmpeg 失败：", (p.stderr or "")[-400:])
        return None
    print(f"  抽音频 {wav.name}  {wav.stat().st_size/1048576:.0f} MB  {time.time()-t0:.0f}s")
    return wav


def probe(video: Path):
    """返回 (时长秒, 视频描述) —— 用 ffmpeg -i 的 stderr 解析，不需要 ffprobe。"""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(video)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = p.stderr or ""
    dur, vinfo = None, None
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            try:
                h, m, s = hms.split(":")
                dur = int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                pass
        if "Video:" in line and vinfo is None:
            vinfo = line.strip()
    return dur, vinfo
