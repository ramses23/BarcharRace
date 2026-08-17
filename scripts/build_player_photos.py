from __future__ import annotations

import csv
import io
import math
import re
import shutil
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "BarcharRace-photo-pack/2.0 (https://github.com/ramses23/BarcharRace; BarChartStudio asset preparation)"
MAX_BYTES = 130 * 1024
TARGET = 512

PLAYERS: list[dict[str, str]] = [
    {"player": "Cristiano Ronaldo", "file": "cristiano_ronaldo.png", "wikipedia": "Cristiano Ronaldo"},
    {"player": "Erling Haaland", "file": "erling_haaland.png", "wikipedia": "Erling Haaland"},
    {"player": "Gary Lineker", "file": "gary_lineker.png", "wikipedia": "Gary Lineker"},
    {"player": "Hristo Stoichkov", "file": "hristo_stoichkov.png", "wikipedia": "Hristo Stoichkov"},
    {"player": "Johan Cruyff", "file": "johan_cruyff.png", "wikipedia": "Johan Cruyff"},
    {"player": "Jürgen Klinsmann", "file": "j_rgen_klinsmann.png", "wikipedia": "Jürgen Klinsmann"},
    {"player": "Karim Bagheri", "file": "karim_bagheri.png", "wikipedia": "Karim Bagheri"},
    {"player": "Landon Donovan", "file": "landon_donovan.png", "wikipedia": "Landon Donovan"},
    {"player": "Michel Platini", "file": "michel_platini.png", "wikipedia": "Michel Platini"},
    {"player": "Paulo Wanchope", "file": "paulo_wanchope.png", "wikipedia": "Paulo Wanchope"},
    {"player": "Roberto Porta", "file": "roberto_porta.png", "wikipedia": "Roberto Porta"},
    {"player": "Samuel Eto'o", "file": "samuel_eto_o.png", "wikipedia": "Samuel Eto'o"},
    {"player": "Wayne Rooney", "file": "wayne_rooney.png", "wikipedia": "Wayne Rooney"},
    {"player": "Andriy Shevchenko", "file": "andriy_shevchenko.png", "wikipedia": "Andriy Shevchenko"},
    {"player": "Harry Kane", "file": "harry_kane.png", "wikipedia": "Harry Kane"},
    {"player": "Lionel Messi", "file": "lionel_messi.png", "wikipedia": "Lionel Messi"},
    {"player": "Robbie Keane", "file": "robbie_keane.png", "wikipedia": "Robbie Keane"},
    {"player": "Romelu Lukaku", "file": "romelu_lukaku.png", "wikipedia": "Romelu Lukaku"},
    {"player": "Thierry Henry", "file": "thierry_henry.png", "wikipedia": "Thierry Henry"},
    {"player": "Zlatan Ibrahimović", "file": "zlatan_ibrahimovi.png", "wikipedia": "Zlatan Ibrahimović"},
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def get_json(url: str, params: dict[str, Any] | None = None, attempts: int = 5) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = SESSION.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"JSON request failed: {url}: {last}")


def download_bytes(url: str, attempts: int = 5) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = SESSION.get(url, timeout=120)
            response.raise_for_status()
            return response.content
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Image download failed: {url}: {last}")


def wikipedia_wikidata_id(title: str) -> str | None:
    data = get_json(
        "https://en.wikipedia.org/w/api.php",
        {"action": "query", "format": "json", "redirects": 1, "prop": "pageprops", "titles": title},
    )
    page = next(iter(data["query"]["pages"].values()))
    return page.get("pageprops", {}).get("wikibase_item")


def wikidata_p18(qid: str) -> str | None:
    data = get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    claims = data["entities"][qid].get("claims", {}).get("P18", [])
    if not claims:
        return None
    try:
        return claims[0]["mainsnak"]["datavalue"]["value"]
    except Exception:
        return None


def wikipedia_pageimage(title: str) -> tuple[str, str] | None:
    data = get_json(
        "https://en.wikipedia.org/w/api.php",
        {
            "action": "query",
            "format": "json",
            "redirects": 1,
            "prop": "pageimages",
            "piprop": "thumbnail|name",
            "pithumbsize": 1400,
            "titles": title,
        },
    )
    page = next(iter(data["query"]["pages"].values()))
    thumb = page.get("thumbnail", {}).get("source")
    name = page.get("pageimage")
    return (name, thumb) if name and thumb else None


def commons_image_info(file_name: str) -> dict[str, Any]:
    title = "File:" + file_name
    data = get_json(
        "https://commons.wikimedia.org/w/api.php",
        {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1400,
            "titles": title,
        },
    )
    page = next(iter(data["query"]["pages"].values()))
    infos = page.get("imageinfo", [])
    if not infos:
        raise RuntimeError(f"No Commons imageinfo for {file_name}")
    info = infos[0]
    ext = info.get("extmetadata", {})
    return {
        "file_name": file_name,
        "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":()_,-."),
        "image_url": info.get("thumburl") or info.get("url"),
        "license": ext.get("LicenseShortName", {}).get("value", ""),
        "artist": ext.get("Artist", {}).get("value", ""),
    }


def resolve_source(player: dict[str, str]) -> dict[str, Any]:
    title = player["wikipedia"]
    qid = wikipedia_wikidata_id(title)
    if qid:
        p18 = wikidata_p18(qid)
        if p18:
            info = commons_image_info(p18)
            info.update({"wikidata_id": qid, "resolution_method": "Wikidata P18"})
            return info
    fallback = wikipedia_pageimage(title)
    if fallback:
        file_name, thumb_url = fallback
        try:
            info = commons_image_info(file_name)
        except Exception:
            info = {
                "file_name": file_name,
                "page_url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                "image_url": thumb_url,
                "license": "",
                "artist": "",
            }
        info.update({"wikidata_id": qid or "", "resolution_method": "Wikipedia pageimage"})
        return info
    raise RuntimeError(f"No image resolved for {title}")


def face_crop(image: Image.Image) -> tuple[Image.Image, bool]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(45, 45))
    w, h = image.size
    if len(faces):
        x, y, fw, fh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        cx = x + fw / 2
        cy = y + fh / 2
        side = min(max(fw * 3.0, fh * 3.2), max(w, h))
        left = int(cx - side / 2)
        top = int(cy - side * 0.43)
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
        return ImageOps.fit(crop, (TARGET, TARGET), method=Image.Resampling.LANCZOS, centering=(0.5, 0.46)), True
    return ImageOps.fit(image, (TARGET, TARGET), method=Image.Resampling.LANCZOS, centering=(0.5, 0.34)), False


def save_small_png(image: Image.Image, destination: Path) -> tuple[int, int, int]:
    best: tuple[bytes, int] | None = None
    for side in (512, 448, 384, 320):
        resized = image if image.size == (side, side) else image.resize((side, side), Image.Resampling.LANCZOS)
        for colors in (192, 128, 96, 64):
            quantized = resized.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            buf = io.BytesIO()
            quantized.save(buf, "PNG", optimize=True)
            data = buf.getvalue()
            if best is None or len(data) < len(best[0]):
                best = (data, side)
            if len(data) <= MAX_BYTES:
                destination.write_bytes(data)
                return side, side, len(data)
    assert best is not None
    destination.write_bytes(best[0])
    return best[1], best[1], len(best[0])


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def make_preview(rows: list[dict[str, Any]], root: Path) -> None:
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
    root = Path("photo_pack_batch01")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for player in PLAYERS:
        print(f"Resolving {player['player']}...", flush=True)
        try:
            source = resolve_source(player)
            raw = download_bytes(source["image_url"])
            with Image.open(io.BytesIO(raw)) as image:
                processed, face_found = face_crop(image)
            destination = root / player["file"]
            width, height, size_bytes = save_small_png(processed, destination)
            rows.append(
                {
                    "filename": player["file"],
                    "person_name": player["player"],
                    "width": width,
                    "height": height,
                    "size_bytes": size_bytes,
                    "size_kb": round(size_bytes / 1024, 2),
                    "status": "OK" if size_bytes <= MAX_BYTES else "OK_OVER_TARGET",
                    "face_detected": "yes" if face_found else "no",
                    "source_file": source.get("file_name", ""),
                    "source_url": source.get("page_url", ""),
                    "license": clean_html(source.get("license", "")),
                    "artist": clean_html(source.get("artist", "")),
                    "wikidata_id": source.get("wikidata_id", ""),
                    "resolution_method": source.get("resolution_method", ""),
                }
            )
            print(f"OK {player['file']} {size_bytes / 1024:.1f} KB face={face_found}", flush=True)
        except Exception as exc:
            message = f"{player['player']}: {type(exc).__name__}: {exc}"
            failures.append(message)
            print("FAILED " + message, flush=True)

    fields = [
        "filename", "person_name", "width", "height", "size_bytes", "size_kb", "status",
        "face_detected", "source_file", "source_url", "license", "artist", "wikidata_id", "resolution_method",
    ]
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    if failures:
        (root / "DOWNLOAD_FAILURES.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")
    make_preview(rows, root)

    zip_path = Path("football_player_photos_batch01_png_max130kb.zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            archive.write(path, arcname=path.name)

    expected = {p["file"] for p in PLAYERS}
    created = {row["filename"] for row in rows}
    missing = sorted(expected - created)
    print(f"Created {len(created)}/{len(expected)} player assets.")
    if missing:
        print("Missing: " + ", ".join(missing))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
