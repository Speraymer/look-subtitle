import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from lk.deck import _monotone_match
from lk.polish import _slide_for, clean_oral


class UpgradeTests(unittest.TestCase):
    def test_oral_duplicate_cleanup_is_conservative(self):
        self.assertEqual(clean_oral("那么那么这里这里这个这个结论对不对对不对"), "那么这里这个结论对不对")
        self.assertEqual(clean_oral("进程和线程不同"), "进程和线程不同")
        self.assertEqual(clean_oral("Unix   V6++"), "Unix V6++")
        self.assertEqual(
            clean_oral("它是一个指向 Process 结构的指针，它是一个指向 Process 的结构指针。"),
            "它是一个指向 Process 结构的指针。",
        )
        self.assertEqual(clean_oral("呃，没毛病。那么继续。"), "那么继续。")
        self.assertEqual(clean_oral("进程有代码段，进程有数据段。"), "进程有代码段，进程有数据段。")
        self.assertEqual(_slide_for(1, [{"t": 0}], {}), (-1, 0))

    def test_slide_matching_stays_monotone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slides = []
            for i in range(4):
                p = root / f"slide-{i}.png"
                im = Image.new("RGB", (640, 360), "white")
                d = ImageDraw.Draw(im)
                d.rectangle((30 + i*80, 40, 190 + i*80, 260), fill=(20*i, 60, 180))
                d.text((50, 300), f"slide {i}", fill="black")
                for k in range(24):
                    x, y = (k*37 + i*53) % 610, (k*k*13 + i*29) % 330
                    d.ellipse((x, y, x + 5, y + 5), fill=(40*i, 30*k % 255, 90))
                im.save(p)
                slides.append(p)
            rows = _monotone_match([slides[1], slides[1], slides[3]], slides)
            self.assertEqual([r["slide"] for r in rows], [1, 1, 3])
            self.assertTrue(all(r["confident"] for r in rows))
            json.dumps(rows)

            camera = root / "camera.jpg"
            with Image.open(slides[2]) as im:
                im.resize((360, 203)).save(camera)
            self.assertEqual(_monotone_match([camera], slides)[0]["slide"], 2)


if __name__ == "__main__":
    unittest.main()
