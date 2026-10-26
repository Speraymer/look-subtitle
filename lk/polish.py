"""保守清理转写，并把课件文字和相邻语句整理成可复核材料。"""

import json
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ORAL_DUPLICATES = (
    "这个", "那个", "这里", "后面", "然后", "那么", "就是", "所以", "我们", "你看",
    "对不对", "是不是", "呃", "嗯", "啊",
)
FILLER_CLAUSES = {"呃", "嗯", "啊", "呃嗯", "嗯嗯", "没毛病"}


def _clause_key(text):
    key = re.sub(r"[\s，。！？；、,.!?;]", "", text.casefold())
    key = re.sub(r"^(?:它是|这是|这个是|那是)(?:一个)?", "", key)
    return key.replace("的", "")


def clean_oral(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    for word in ORAL_DUPLICATES:
        text = re.sub(rf"(?:{re.escape(word)}[，、, ]*){{2,}}", word, text)
    text = re.sub(r"([，。！？；、])\1+", r"\1", text)

    kept = []
    for match in re.finditer(r"([^，。！？；、,!?;]+)([，。！？；、,!?;]*)", text):
        clause, punctuation = match.group(1).strip(), match.group(2)
        if clause in FILLER_CLAUSES:
            # 口癖被删掉了，它本来收尾的那句话要自己收干净，别留下半个逗号
            if kept and punctuation and punctuation[-1] in "。！？；.!?;":
                kept[-1][1] = "。"
            continue
        key = _clause_key(clause)
        if kept and len(key) >= 6 and key == kept[-1][2]:
            if punctuation and punctuation[-1] in "。！？；.!?;":
                kept[-1][1] = punctuation[-1]
            continue
        kept.append([clause, punctuation, key])
    return "".join(clause + punctuation for clause, punctuation, _ in kept)


def _pptx_text(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"\d+", Path(n).stem).group()))
        for name in names:
            root = ElementTree.fromstring(z.read(name))
            words = [e.text or "" for e in root.iter() if e.tag.endswith("}t")]
            out.append(" ".join(x.strip() for x in words if x.strip()))
    return out


def extract_slide_text(source):
    source = Path(source)
    suffix = source.suffix.lower()
    if suffix in (".pptx", ".pptm"):
        return _pptx_text(source)
    if suffix == ".pdf":
        try:
            import pymupdf as fitz
        except ImportError as e:
            raise SystemExit("读取 PDF 文字需要 PyMuPDF：python -m pip install pymupdf") from e
        with fitz.open(source) as doc:
            return [page.get_text("text").replace("\n", " ").strip() for page in doc]
    return []


def _slide_for(start, pages, mapping):
    frame = 0
    for i, page in enumerate(pages):
        if page.get("t", 0) / 1000.0 <= start:
            frame = i
        else:
            break
    return mapping.get(frame, -1), frame


def polish(w, source, corrections_file=None):
    if not w.segments.exists():
        raise SystemExit("没有 segments.json，先跑 `look transcribe`")

    if not w.segments_raw.exists():
        shutil.copy2(w.segments, w.segments_raw)
    data = json.load(open(w.segments_raw, encoding="utf-8"))

    corrections = {}
    if corrections_file:
        corrections = json.load(open(corrections_file, encoding="utf-8"))
    replacements = corrections.get("replace", {})
    overrides = {int(k): v for k, v in corrections.get("segments", {}).items()}

    for i, seg in enumerate(data.get("segments", [])):
        text = clean_oral(seg.get("text", ""))
        for old, new in replacements.items():
            text = text.replace(old, new)
        if i in overrides:
            text = overrides[i]
        seg["text"] = text

    slide_text = extract_slide_text(source)
    w.ppt_dir.mkdir(parents=True, exist_ok=True)
    with open(w.slide_text, "w", encoding="utf-8") as f:
        json.dump(slide_text, f, ensure_ascii=False, indent=1)

    pages = json.load(open(w.ppt_pages, encoding="utf-8")) if w.ppt_pages.exists() else []
    mapping = {}
    if w.ppt_mapping.exists():
        rows = json.load(open(w.ppt_mapping, encoding="utf-8")).get("matches", [])
        mapping = {int(r["frame"]): int(r["slide"]) for r in rows if r.get("confident")}

    segs = data.get("segments", [])
    review = []
    for i, seg in enumerate(segs):
        slide, frame = _slide_for(float(seg.get("start", 0)), pages, mapping)
        review.append({
            "index": i,
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg.get("text", ""),
            "before": segs[i - 1].get("text", "") if i else "",
            "after": segs[i + 1].get("text", "") if i + 1 < len(segs) else "",
            "frame": frame,
            "slide": slide,
            "slide_text": slide_text[slide] if 0 <= slide < len(slide_text) else "",
        })

    with open(w.segments, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(w.review, "w", encoding="utf-8") as f:
        json.dump({"source": str(source), "segments": review}, f, ensure_ascii=False, indent=1)
    print(f"  保留原始转写 -> {w.segments_raw.name}")
    print(f"  清理转写 {len(segs)} 段 -> {w.segments.name}")
    print(f"  上下文复核材料 -> {w.review.name}")
    return data
