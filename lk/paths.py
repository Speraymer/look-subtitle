"""路径约定：所有产出都落在 works/<sub_id>/ 下，一步一个文件，可断点重跑。"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKS = ROOT / "works"
CAPTURES = ROOT / "captures"
MODELS = ROOT / "models"
EXTENSION = ROOT / "extension"

SENSE_DIR = MODELS / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"

for d in (WORKS, CAPTURES, MODELS):
    d.mkdir(parents=True, exist_ok=True)


class Work:
    """一节课的工作目录。"""

    def __init__(self, sub_id):
        self.sub_id = str(sub_id)
        self.dir = WORKS / self.sub_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # 基础
    @property
    def meta(self):
        return self.dir / "meta.json"

    @property
    def video(self):
        return self.dir / "video.mp4"

    @property
    def audio(self):
        return self.dir / "audio.wav"

    # 转写
    @property
    def segments(self):
        return self.dir / "segments.json"

    @property
    def segments_raw(self):
        return self.dir / "segments.raw.json"

    @property
    def review(self):
        return self.dir / "review.json"

    @property
    def srt(self):
        return self.dir / "sub.srt"

    @property
    def vtt(self):
        return self.dir / "sub.vtt"

    # 画面
    @property
    def ppt_dir(self):
        return self.dir / "ppt"

    @property
    def ppt_raw(self):
        return self.ppt_dir / "raw"

    @property
    def ppt_crop(self):
        return self.ppt_dir / "crop"

    @property
    def ppt_pages(self):
        return self.ppt_dir / "pages.json"

    @property
    def ppt_mapping(self):
        return self.ppt_dir / "mapping.json"

    @property
    def slide_text(self):
        return self.ppt_dir / "slide_text.json"

    # 成品
    @property
    def docx(self):
        return self.dir / "handout.docx"

    def ensure_dirs(self):
        for d in (self.ppt_raw, self.ppt_crop):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def rel(self, p):
        return os.path.relpath(str(p), str(self.dir))


def ffmpeg_exe():
    """优先 PATH 里的 ffmpeg，其次 imageio-ffmpeg 自带的。"""
    from shutil import which

    p = which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()
