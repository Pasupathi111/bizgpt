#!/usr/bin/env python3
"""Generate illustrative maintenance site photos for the Monthly Report POC demo.

    python3 dev/make_sample_photos.py [out_dir]

Makes 16 JPEGs for project "Taman Park Landscape Maintenance": Zone A grass cutting
(before/during/after), Zone B tree maintenance (before/after only, so "During" is missing),
Zone C drain cleaning (before/during/after), plus a photo with no site sign (location unknown).
Photos carry a site signboard and a timestamp-camera stamp like real field photos; some also
carry EXIF DateTimeOriginal. Needs Pillow.
"""

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 768
SKY, GROUND = (150, 195, 235), (120, 100, 70)


def font(size):
    for name in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def base(rng):
    img = Image.new('RGB', (W, H), SKY)
    d = ImageDraw.Draw(img)
    for i in range(6):  # distant trees
        x = rng.randint(0, W)
        d.ellipse([x - 90, 170, x + 90, 330], fill=(60, 110, 60))
    d.rectangle([0, 320, W, H], fill=(95, 150, 70))
    return img, d


def sign(d, text):
    d.rectangle([60, 180, 72, 330], fill=(90, 70, 50))
    d.rectangle([20, 150, 300, 215], fill=(20, 90, 50), outline='white', width=4)
    d.text((34, 162), text, font=font(34), fill='white')


def stamp(d, text):
    d.rectangle([0, H - 56, W, H], fill=(0, 0, 0))
    d.text((18, H - 46), text, font=font(28), fill=(255, 220, 0))


def worker(d, x, y, tool='trimmer'):
    d.ellipse([x - 16, y - 120, x + 16, y - 88], fill=(230, 190, 150))  # head
    d.rectangle([x - 20, y - 125, x + 20, y - 112], fill=(250, 200, 0))  # helmet
    d.rectangle([x - 24, y - 88, x + 24, y - 30], fill=(255, 120, 0))  # hi-vis vest
    d.line([x - 12, y - 30, x - 18, y], fill=(40, 40, 90), width=12)
    d.line([x + 12, y - 30, x + 18, y], fill=(40, 40, 90), width=12)
    if tool == 'trimmer':
        d.line([x + 20, y - 70, x + 110, y + 10], fill=(60, 60, 60), width=7)
        d.ellipse([x + 100, y, x + 130, y + 20], fill=(200, 30, 30))
    else:  # shovel
        d.line([x + 20, y - 70, x + 80, y + 20], fill=(110, 80, 40), width=7)
        d.polygon([(x + 70, y + 15), (x + 100, y + 25), (x + 85, y + 50)], fill=(120, 120, 130))


def grass(d, rng, x0, x1, tall):
    for _ in range(1400 if tall else 500):
        x = rng.randint(x0, x1)
        y = rng.randint(335, H - 60)
        h = rng.randint(40, 90) if tall else rng.randint(4, 9)
        c = (rng.randint(40, 90), rng.randint(110, 160), rng.randint(30, 60))
        d.line([x, y, x + rng.randint(-8, 8), y - h], fill=c, width=2)
    if tall:
        for _ in range(12):  # weeds and litter
            x, y = rng.randint(x0, x1), rng.randint(360, H - 80)
            d.ellipse([x, y, x + 18, y + 18], fill=(230, 220, 60))
        for _ in range(5):
            x, y = rng.randint(x0, x1), rng.randint(380, H - 90)
            d.rectangle([x, y, x + 26, y + 14], fill=(240, 240, 240))
    else:
        for i in range(x0, x1, 80):  # mowing stripes
            d.rectangle([i, 330, i + 40, H - 56], fill=(105, 165, 80))


def tree(d, x, fallen=False, trimmed=False):
    d.rectangle([x - 22, 250, x + 22, 560], fill=(100, 70, 40))
    crown = 110 if trimmed else 170
    d.ellipse([x - crown, 90, x + crown, 330], fill=(50, 120, 50))
    d.rectangle([0, 560, W, 640], fill=(170, 170, 165))  # footpath
    if fallen:
        d.line([x + 40, 420, x + 380, 610], fill=(100, 70, 40), width=26)
        for i in range(6):
            d.ellipse([x + 120 + i * 45, 470 + i * 20, x + 190 + i * 45, 540 + i * 20], fill=(60, 130, 50))


def drain(d, rng, state):
    d.rectangle([0, 520, W, H - 56], fill=(165, 165, 160))
    d.rectangle([80, 560, W - 80, 640], fill=(70, 70, 75))  # drain channel
    if state in ('before', 'during'):
        stop = W - 80 if state == 'before' else W // 2
        for _ in range(160 if state == 'before' else 70):
            x, y = rng.randint(90, stop), rng.randint(555, 615)
            d.ellipse([x, y, x + rng.randint(15, 40), y + rng.randint(12, 30)],
                      fill=rng.choice([(110, 85, 50), (60, 100, 40), (200, 200, 190), (90, 70, 40)]))
    if state == 'after':
        d.rectangle([90, 600, W - 90, 630], fill=(80, 110, 140))  # clear flowing water


def exif_bytes(dt):
    exif = Image.Exif()
    exif[0x0132] = dt
    exif.get_ifd(0x8769)[0x9003] = dt
    return exif


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    shots = [
        ('IMG_0101.jpg', 'A', 'grass', 'before', '2026-09-03 08:12'),
        ('IMG_0102.jpg', 'A', 'grass', 'before', '2026-09-03 08:14'),
        ('IMG_0103.jpg', 'A', 'grass', 'during', '2026-09-03 09:40'),
        ('IMG_0104.jpg', 'A', 'grass', 'during', '2026-09-03 10:05'),
        ('IMG_0105.jpg', 'A', 'grass', 'after', '2026-09-03 11:30'),
        ('IMG_0106.jpg', 'A', 'grass', 'after', '2026-09-03 11:32'),
        ('IMG_0201.jpg', 'B', 'tree', 'before', '2026-09-10 08:05'),
        ('IMG_0202.jpg', 'B', 'tree', 'before', '2026-09-10 08:07'),
        ('IMG_0203.jpg', 'B', 'tree', 'after', '2026-09-10 12:20'),
        ('IMG_0204.jpg', 'B', 'tree', 'after', '2026-09-10 12:25'),
        ('IMG_0301.jpg', 'C', 'drain', 'before', '2026-09-17 07:50'),
        ('IMG_0302.jpg', 'C', 'drain', 'during', '2026-09-17 09:15'),
        ('IMG_0303.jpg', 'C', 'drain', 'during', '2026-09-17 09:45'),
        ('IMG_0304.jpg', 'C', 'drain', 'after', '2026-09-17 11:10'),
        ('IMG_0305.jpg', 'C', 'drain', 'after', '2026-09-17 11:12'),
        ('IMG_0999.jpg', None, 'grass', 'after', None),  # no sign, no stamp: location unknown
    ]
    for i, (name, zone, kind, stage, when) in enumerate(shots):
        img, d = base(rng)
        if kind == 'grass':
            grass(d, rng, 0, W if stage != 'during' else W // 2, tall=stage in ('before', 'during'))
            if stage == 'during':
                grass(d, rng, W // 2, W, tall=False)
                worker(d, W // 2 - 40, 560)
        elif kind == 'tree':
            tree(d, 560, fallen=stage == 'before', trimmed=stage == 'after')
            if stage == 'after':
                for x in range(700, 900, 60):  # cut logs stacked
                    d.ellipse([x, 500, x + 50, 550], fill=(150, 110, 70), outline=(100, 70, 40), width=4)
        else:
            drain(d, rng, stage)
            if stage == 'during':
                worker(d, W // 2 + 60, 560, tool='shovel')
                d.rectangle([W - 260, 430, W - 120, 520], fill=(40, 90, 160))  # debris bin
        if zone:
            sign(d, f'ZONE {zone}')
            stamp(d, f'Taman Park - Zone {zone}   {when}')
        path = out / name
        if when and i % 3 == 0:
            img.save(path, 'JPEG', quality=88, exif=exif_bytes(when.replace('-', ':') + ':00'))
        else:
            img.save(path, 'JPEG', quality=88)
    print(f'wrote {len(shots)} photos to {out}')


if __name__ == '__main__':
    main(Path(sys.argv[1] if len(sys.argv) > 1 else 'sample-photos'))
