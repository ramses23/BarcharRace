from __future__ import annotations

import csv
import io
import math
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "BarcharRace-photo-pack/2.1 (https://github.com/ramses23/BarcharRace; curated portrait correction)"
MAX_BYTES = 130 * 1024
TARGET = 512
ZIP_PATH = Path("football_player_photos_batch01_png_max130kb.zip")
WORK = Path("photo_pack_patch")

OVERRIDES = [
    {"filename": "roberto_porta.png", "person_name": "Roberto Porta", "commons_file": "Roberto Porta.jpg"},
    {"filename": "samuel_eto_o.png", "person_name": "Samuel Eto'o", "commons_file": "Samuel Eto'o.jpg"},
    {"filename": "wayne_rooney.png", "person_name": "Wayne Rooney", "commons_file": "Wayne Rooney.jpg"},
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def commons_info(file_name: str) -> dict[str, str]:
    title = "File:" + file_name
    response = SESSION.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1400,
            "titles": title,
        },
        timeout=60,
    )
    response.raise_for_status()
    page = next(iter(response.json()["query"]["pages"].values()))
    info = page["imageinfo"][0]
    ext = info.get("extmetadata", {})
    return {
        "image_url": info.get("thumburl") or info["url"],
        "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":()_,-.'"),
        "license": clean_html(ext.get("LicenseShortName", {}).get("value", "")),
        "artist": clean_html(ext.get("Artist", {}).get("value", "")),
    }


def best_face_crop(image: Image.Image) -> tuple[Image.Image, bool]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(30, 30))
    w, h = image.size
    if len(faces):
        # Prefer a large face in the upper 75% of the image; reject detections very low in frame.
        candidates = []
        for x, y, fw, fh in faces:
            cy = y + fh / 2
            if cy <= h * 0.78:
                candidates.append((int(fw) * int(fh), x, y, fw, fh))
        if candidates:
            _, x, y, fw, fh = max(candidates)
            cx = x + fw / 2
            cy = y + fh / 2
            side = max(fw * 2.8, fh * 3.0)
            side = min(side, max(w, h))
            left = int(cx - side / 2)
            top = int(cy - side * 0.42)
            right = left + int(side)
            bottom = top + int(side)
            if left < 0:
                right -= left
                left = 0
            if top < 0:
                bottom -= top
                top = 0
            if right > w:
                left -= right - w
                right = w
            if bottom > h:
                top -= bottom - h
                bottom = h
            crop = image.crop((max(0, left), max(0, top), min(w, right), min(h, bottom)))
            return ImageOps.fit(crop, (TARGET, TARGET), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45)), True
    # Known override sources are portrait-oriented; an upper-centered fallback keeps the face visible.
    return ImageOps.fit(image, (TARGET, TARGET), method=Image.Resampling.LANCZOS, centering=(0.5, 0.27)), False


def save_small_png(image: Image.Image, destination: Path) -> tuple[int, int, int]:
    best: tuple[bytes, int] | None = None
    for side in (512, 448, 384, 320):
        resized = image if image.size == (side, side) else image.resize((side, side), Image.Resampling.LANCZOS)
        for colors in (192, 128, 96, 64):
            q = resized.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            buf = io.BytesIO()
            q.save(buf, "PNG", optimize=True)
            data = buf.getvalue()
            if best is None or len(data) < len(best[0]):
                best = (data, side)
            if len(data) <= MAX_BYTES:
                destination.write_bytes(data)
                return side, side, len(data)
    assert best is not None
    destination.write_bytes(best[0])
    return best[1], best[1], len(best[0])


def regenerate_preview(rows: list[dict[str, str]], root: Path) -> None:
    cols, card, label_h, pad = 5, 180, 36, 12
    nrows = math.ceil(len(rows) / cols)
    preview = Image.new("RGB", (pad + cols * (card + pad), pad + nrows * (card + label_h + pad)), "#f2f2f2")
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    for idx, row in enumerate(rows):
        r, c = divmod(idx, cols)
        x, y = pad + c * (card + pad), pad + r * (card + label_h + pad)
        with Image.open(root / row["filename"]) as im:
            tile = ImageOps.fit(im.convert("RGB"), (card, card), method=Image.Resampling.LANCZOS)
        preview.paste(tile, (x, y))
        draw.text((x, y + card + 7), row["filename"].removesuffix(".png")[:28], fill="#111111", font=font)
    preview.save(root / "preview.jpg", "JPEG", quality=90, optimize=True)


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(WORK)

    manifest_path = WORK / "manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fields = list(rows[0].keys())
    by_file = {row["filename"]: row for row in rows}

    for item in OVERRIDES:
        info = commons_info(item["commons_file"])
        response = SESSION.get(info["image_url"], timeout=120)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            processed, face_found = best_face_crop(image)
        dest = WORK / item["filename"]
        width, height, size_bytes = save_small_png(processed, dest)
        row = by_file[item["filename"]]
        row.update({
            "width": str(width),
            "height": str(height),
            "size_bytes": str(size_bytes),
            "size_kb": str(round(size_bytes / 1024, 2)),
            "status": "OK" if size_bytes <= MAX_BYTES else "OK_OVER_TARGET",
            "face_detected": "yes" if face_found else "no",
            "source_file": item["commons_file"],
            "source_url": info["page_url"],
            "license": info["license"],
            "artist": info["artist"],
            "resolution_method": "Curated Commons override",
        })
        print(f"OVERRIDE OK {item['filename']} {size_bytes/1024:.1f} KB face={face_found}")

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    regenerate_preview(rows, WORK)

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(WORK.iterdir()):
            archive.write(path, arcname=path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
