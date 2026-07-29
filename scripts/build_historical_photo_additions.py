from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

USER_AGENT = "BarcharRace-historical-assets/1.0 (ramses23/BarcharRace)"
OUTPUT = Path("historical_photo_additions")
RAW = Path(".historical-photo-downloads")

SOURCES = [
    {
        "player": "Fernando Peyroteo",
        "file": "fernando_peyroteo.png",
        "commons_file": "Fernando Peyroteo.jpg",
        "author": "Lobopt",
        "license": "CC BY-SA 4.0",
        "centering": [0.5, 0.45],
    },
    {
        "player": "Uwe Seeler",
        "file": "uwe_seeler.png",
        "commons_file": "Uwe Seeler (Kiel 56.303).jpg",
        "author": "Friedrich Magnussen / Stadtarchiv Kiel",
        "license": "CC BY-SA 3.0 DE",
        "centering": [0.5, 0.30],
    },
    {
        "player": "Jimmy McGrory",
        "file": "jimmy_mcgrory.png",
        "commons_file": "Jimmy McGrory.jpg",
        "author": "Unknown author",
        "license": "Public domain (UK anonymous work)",
        "centering": [0.5, 0.40],
    },
    {
        "player": "Imre Schlosser",
        "file": "imre_schlosser.png",
        "commons_file": "Schlosser Imre 1923 (cropped).jpg",
        "author": "Unknown author",
        "license": "Public domain (anonymous work published before 1931)",
        "centering": [0.5, 0.35],
    },
]


def file_page(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(
        title.replace(" ", "_"), safe="()_,.-"
    )


def thumbnail_url(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + urllib.parse.quote(
        title.replace(" ", "_"), safe="()_,.-"
    ) + "?width=1200"


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                destination.write_bytes(response.read())
            return
        except Exception as exc:
            last_error = exc
            time.sleep(min(5 * (2**attempt), 90))
    raise RuntimeError(f"Download failed: {url}: {last_error}")


def convert(source: Path, destination: Path, centering: tuple[float, float]) -> None:
    with Image.open(source) as image:
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(
            image,
            (512, 512),
            method=Image.Resampling.LANCZOS,
            centering=centering,
        )
        image.save(destination, "PNG", optimize=True)
    with Image.open(destination) as check:
        if check.format != "PNG" or check.size != (512, 512):
            raise RuntimeError(f"Invalid PNG: {destination}")


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    manifest = []
    attribution_lines = [
        "# Historical scorer photo additions",
        "",
        "All four files are real photographs sourced from Wikimedia Commons.",
        "",
        "| Player | Commons file | Author | License | SHA-256 |",
        "|---|---|---|---|---|",
    ]

    for source in SOURCES:
        raw_path = RAW / (source["file"] + ".download")
        out_path = OUTPUT / source["file"]
        download(thumbnail_url(source["commons_file"]), raw_path)
        convert(raw_path, out_path, tuple(source["centering"]))
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
        record = {
            **source,
            "status": "ok",
            "dimensions": [512, 512],
            "sha256": digest,
            "source_url": file_page(source["commons_file"]),
        }
        manifest.append(record)
        attribution_lines.append(
            f"| {source['player']} | {record['source_url']} | {source['author']} | {source['license']} | `{digest}` |"
        )
        print(f"OK: {source['player']} -> {out_path}")
        time.sleep(4)

    (OUTPUT / "manifest.json").write_text(
        json.dumps({"items": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "ATTRIBUTIONS.md").write_text(
        "\n".join(attribution_lines) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
