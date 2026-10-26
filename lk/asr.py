"""语音识别：SenseVoice（sherpa-onnx，CPU 就够快）+ 自己写的能量分段。

为什么不用 sherpa 自带的 VAD：实测整段 160 秒不切，时间戳就没了。
这里按 20ms 帧算能量，自适应阈值切出语音段，每段不超过 25 秒。
"""

import json
import os
import time
import wave
from pathlib import Path

import numpy as np

from .paths import MODELS, SENSE_DIR

FRAME = 0.02
MIN_GAP = 0.30
MAX_SEG = 25.0
MIN_SEG = 0.60

MODEL_URL = (
    "https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)


def model_ready():
    return (SENSE_DIR / "model.int8.onnx").exists() and (SENSE_DIR / "tokens.txt").exists()


def ensure_model(download=True):
    """模型不在就下（1GB，走 gh-proxy 约 3~5 分钟）。"""
    if model_ready():
        return True
    print(f"  模型不在：{SENSE_DIR}")
    if not download:
        print(f"  手动准备：把模型解压到 {MODELS}")
        return False
    import tarfile

    import requests

    MODELS.mkdir(parents=True, exist_ok=True)
    tar = MODELS / "sense-voice.tar.bz2"
    if not tar.exists():
        print("  下载模型（约 1 GB）…", flush=True)
        r = requests.get(MODEL_URL, stream=True, timeout=60)
        r.raise_for_status()
        have = 0
        with open(tar, "wb") as f:
            for c in r.iter_content(1 << 17):
                f.write(c)
                have += len(c)
                if have % (64 << 20) < (1 << 17):
                    print(f"    {have/1048576:.0f} MB", flush=True)
    print("  解压…", flush=True)
    with tarfile.open(tar, "r:bz2") as t:
        t.extractall(MODELS)
    return model_ready()


def load_wav(path, start=None, end=None):
    with wave.open(str(path), "rb") as w:
        sr, ch, sw, total = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        f0 = 0 if start is None else int(start * sr)
        f1 = total if end is None else min(total, int(end * sr))
        w.setpos(f0)
        raw = w.readframes(f1 - f0)
    if sr != 16000 or sw != 2:
        raise SystemExit(f"需要 16k/16bit wav，拿到的是 {sr}Hz/{sw*8}bit")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr, f0 / sr


def energy_db(samples, sr):
    fl = int(FRAME * sr)
    n = len(samples) // fl
    if n == 0:
        return np.zeros(0), fl
    x = samples[: n * fl].reshape(n, fl)
    rms = np.sqrt((x * x).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-8), fl


def speech_mask(db):
    lo, hi = np.percentile(db, 20), np.percentile(db, 95)
    th = lo + 0.30 * (hi - lo)
    mask = db > th
    k = int(0.15 / FRAME)
    i = 0
    while i < len(mask):
        if not mask[i]:
            j = i
            while j < len(mask) and not mask[j]:
                j += 1
            if 0 < i and j < len(mask) and (j - i) < k:
                mask[i:j] = True
            i = j
        else:
            i += 1
    return mask


def segments_from_mask(mask, db, sr):
    fps = 1 / FRAME
    segs = []
    i, n = 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        s, e = i / fps, j / fps
        k = j
        while k < n and not mask[k]:
            k += 1
        gap_next = (k - j) / fps
        if e - s < MIN_SEG and gap_next is not None and gap_next < MIN_GAP * 2:
            i = k
            continue
        segs.append([s, e])
        i = j

    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < MIN_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    out = []
    for s, e in merged:
        while e - s > MAX_SEG:
            a = int((s + MAX_SEG * 0.55) * fps)
            b = int(min(e, s + MAX_SEG) * fps)
            if b <= a:
                break
            cut = max(a + int(np.argmin(db[a:b])), int((s + 2.0) * fps))
            out.append((s, cut / fps))
            s = cut / fps
        if e - s >= MIN_SEG:
            out.append((s, e))
    return out


def build_recognizer(threads=8):
    import sherpa_onnx

    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(SENSE_DIR / "model.int8.onnx"),
        tokens=str(SENSE_DIR / "tokens.txt"),
        num_threads=threads,
        use_itn=True,
        language="zh",
        debug=False,
    )


def transcribe(wav_path, out_json, threads=10, start=None, end=None, sub_id=None, quiet=False):
    if not model_ready():
        raise SystemExit("模型没准备好，先跑 `python look.py model`")
    t0 = time.time()
    samples, sr, offset = load_wav(wav_path, start, end)
    dur = len(samples) / sr
    print(f"  音频 {dur:.1f}s @{sr}Hz" + (f"（从 {offset:.0f}s 起）" if offset else ""), flush=True)

    db, _ = energy_db(samples, sr)
    segs = segments_from_mask(speech_mask(db), db, sr)
    print(f"  切出 {len(segs)} 段，平均 {sum(e-s for s, e in segs)/max(1,len(segs)):.1f}s", flush=True)

    rec = build_recognizer(threads)
    t1 = time.time()
    out = []
    for idx, (s, e) in enumerate(segs):
        buf = samples[int(s * sr): int(e * sr)]
        if len(buf) < int(0.2 * sr):
            continue
        st = rec.create_stream()
        st.accept_waveform(sr, buf)
        rec.decode_stream(st)
        text = (st.result.text or "").strip()
        if text:
            out.append({"start": round(s + offset, 2), "end": round(e + offset, 2), "text": text})
        if not quiet and (idx + 1) % 200 == 0:
            el = time.time() - t1
            print(f"    {idx+1}/{len(segs)}  {el:.0f}s  eta {el/(idx+1)*(len(segs)-idx-1):.0f}s", flush=True)

    asr_time = time.time() - t1
    speech = sum(x["end"] - x["start"] for x in out)
    print(f"  转写 {asr_time:.0f}s（RTF {asr_time/max(dur,1e-6):.3f}），有效语音 {speech:.0f}s", flush=True)

    payload = {"sub_id": sub_id, "duration": round(dur + (offset or 0), 2),
               "offset": offset, "segments": out}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"  -> {Path(out_json).name}（{len(out)} 段）", flush=True)
    return payload
