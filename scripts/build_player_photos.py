from __future__ import annotations

import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = (
    "BarcharRace-photo-builder/1.2 "
    "(https://github.com/ramses23/BarcharRace; licensed asset preparation)"
)

SOURCES: list[dict[str, Any]] = [
    {
        "player": "Cristiano Ronaldo",
        "file": "cristiano_ronaldo.png",
        "kind": "photo",
        "wikidata_id": "Q11571",
        "commons_file": "Cristiano Ronaldo Croatia v Portugal 2 July 2026-075 (cropped).jpg",
        "author": "Bryan Berlin",
        "license": "CC BY-SA 4.0",
        "centering": [0.5, 0.42],
    },
    {
        "player": "Lionel Messi",
        "file": "lionel_messi.png",
        "kind": "photo",
        "wikidata_id": "Q615",
        "commons_file": "Leo Messi Argentina v Egypt 7 July 2026-1.jpg",
        "author": "Bryan Berlin",
        "license": "CC BY-SA 4.0",
        "centering": [0.5, 0.38],
    },
    {
        "player": "Pelé",
        "file": "pele.png",
        "kind": "photo",
        "wikidata_id": "Q12897",
        "commons_file": "Pele con brasil (cropped).jpg",
        "author": "Unknown author",
        "license": "Public domain",
        "centering": [0.5, 0.42],
    },
    {
        "player": "Romário",
        "file": "romario.png",
        "kind": "photo",
        "wikidata_id": "Q178649",
        "commons_file": "Senadores da 57ª Legislatura (52689451805).jpg",
        "author": "Agência Senado",
        "license": "CC BY 2.0",
        "centering": [0.5, 0.36],
    },
    {
        "player": "Ferenc Puskás",
        "file": "ferenc_puskas.png",
        "kind": "photo",
        "wikidata_id": "Q482931",
        "commons_file": "Ferenc Puskás (cropped).jpg",
        "author": "Anefo",
        "license": "CC0",
        "centering": [0.5, 0.44],
    },
    {
        "player": "Josef Bican",
        "file": "josef_bican.png",
        "kind": "photo",
        "wikidata_id": "Q352017",
        "commons_file": "Josef Bican 1940.jpg",
        "author": "Unknown author; re-photo by David Sedlecký",
        "license": "Public domain",
        "centering": [0.5, 0.38],
    },
    {
        "player": "Robert Lewandowski",
        "file": "robert_lewandowski.png",
        "kind": "photo",
        "wikidata_id": "Q151269",
        "commons_file": "Robert Lewandowski 2018, JAP-POL (cropped).jpg",
        "author": "Svetlana Beketova",
        "license": "CC BY-SA 3.0",
        "centering": [0.5, 0.38],
    },
    {
        "player": "Jimmy Jones",
        "file": "jimmy_jones.png",
        "kind": "photo",
        "wikidata_id": "Q3179067",
        "commons_file": "Jimmy jones.jpg",
        "author": "Tumijo",
        "license": "CC BY-SA 4.0",
        "centering": [0.5, 0.43],
    },
    {
        "player": "Gerd Müller",
        "file": "gerd_muller.png",
        "kind": "photo",
        "wikidata_id": "Q152871",
        "commons_file": "BOMBERGERDMUELLER (headshot).JPG",
        "author": "Alexander Hauk / Promifotos.de",
        "license": "CC BY-SA 3.0",
        "centering": [0.5, 0.42],
    },
    {
        "player": "Joe Bambrick",
        "file": "joe_bambrick.png",
        "kind": "placeholder",
        "wikidata_id": "Q2056445",
        "note": "No reusable photograph was identified; an approved neutral football emblem is used intentionally.",
    },
    {
        "player": "Abe Lenstra",
        "file": "abe_lenstra.png",
        "kind": "photo",
        "wikidata_id": "Q318173",
        "commons_file": "Abe Lenstra (Heerenveen) in het Olympisch Stadion in Amsterdam, enige dagen na d, Bestanddeelnr 191-1062.jpg",
        "author": "Willem van de Poll",
        "license": "CC0",
        "centering": [0.5, 0.42],
    },
    {
        "player": "Luis Suárez",
        "file": "luis_suarez.png",
        "kind": "photo",
        "wikidata_id": "Q26517",
        "commons_file": "U09 Luis Suárez 3470.jpg",
        "author": "Ailura",
        "license": "CC BY-SA 3.0 AT",
        "centering": [0.5, 0.16],
    },
    {
        "player": "Túlio Maravilha",
        "file": "tulio_maravilha.png",
        "kind": "photo",
        "wikidata_id": "Q714354",
        "commons_file": "Tulio no Itumbiara (cropped).JPG",
        "author": "Thiago Souza",
        "license": "CC BY-SA 3.0",
        "centering": [0.5, 0.16],
    },
    {
        "player": "Eusébio",
        "file": "eusebio.png",
        "kind": "photo",
        "wikidata_id": "Q17163",
        "commons_file": "Eusebio (1963 version2).jpg",
        "author": "Harry Pot / Anefo",
        "license": "CC BY-SA 3.0 NL",
        "centering": [0.5, 0.38],
    },
    {
        "player": "Zlatan Ibrahimović",
        "file": "zlatan_ibrahimovic.png",
        "kind": "photo",
        "wikidata_id": "Q46896",
        "commons_file": "Zlatan Ibrahimović-13 (cropped).jpg",
        "author": "Frankie Fouganthin",
        "license": "CC BY-SA 3.0",
        "centering": [0.5, 0.5],
    },
]


def commons_page_url(file_title: str) -> str:
    encoded = urllib.parse.quote(file_title.replace(" ", "_"), safe="()_,.-")
    return f"https://commons.wikimedia.org/wiki/File:{encoded}"


def commons_thumbnail_url(file_title: str) -> str:
    encoded = urllib.parse.quote(file_title.replace(" ", "_"), safe="()_,.-")
    return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{encoded}?width=1200"


def retry_delay(exc: Exception, attempt: int) -> float:
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            try:
                return max(float(retry_after), 20.0)
            except ValueError:
                pass
        return min(30.0 * (attempt + 1), 180.0)
    return min(4.0 * (2**attempt), 60.0)


def download(url: str, destination: Path, attempts: int = 8) -> None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    raise RuntimeError(f"Unexpected content type {content_type!r} from {url}")
                destination.write_bytes(response.read())
            return
        except Exception as exc:
            if attempt == attempts - 1:
                raise
            delay = retry_delay(exc, attempt)
            print(
                f"Retry {attempt + 1}/{attempts - 1} after {delay:.0f}s: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            time.sleep(delay)


def validate_png(path: Path) -> None:
    with Image.open(path) as check:
        check.verify()
    with Image.open(path) as check:
        if check.format != "PNG" or check.size != (512, 512):
            raise RuntimeError(f"Invalid PNG asset: {path}")


def convert_square(source: Path, destination: Path, centering: tuple[float, float]) -> None:
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
    validate_png(destination)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text((xy[0] - width / 2, xy[1] - height / 2), text, font=font, fill=fill)


def create_placeholder(destination: Path) -> None:
    image = Image.new("RGB", (512, 512), "#10253f")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (28, 28, 484, 484),
        radius=70,
        fill="#173b62",
        outline="#d8e4ef",
        width=8,
    )
    draw.ellipse((146, 72, 366, 292), fill="#f7f7f2", outline="#0b1726", width=8)

    cx, cy, radius = 256, 182, 38
    points = []
    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill="#0b1726")
    for x, y in points:
        draw.line((cx, cy, x, y), fill="#0b1726", width=7)

    centered_text(draw, (256, 345), "JB", load_font(92, bold=True), "#ffffff")
    centered_text(draw, (256, 430), "JOE BAMBRICK", load_font(34, bold=True), "#d8e4ef")
    centered_text(draw, (256, 472), "NO PHOTO AVAILABLE", load_font(20), "#b9c9d7")

    image.save(destination, "PNG", optimize=True)
    validate_png(destination)


def main() -> int:
    root = Path("photos")
    raw = Path(".photo-downloads")
    root.mkdir(exist_ok=True)
    raw.mkdir(exist_ok=True)

    for old_png in root.glob("*.png"):
        old_png.unlink()

    manifest: list[dict[str, Any]] = []
    attributions = [
        "# Player asset attributions",
        "",
        "The package contains 14 real photographs and one explicitly approved neutral placeholder for Joe Bambrick. Photographs were transformed only by square cropping and resizing to 512 × 512 pixels.",
        "",
        "| Player | Asset type | Source | File URL | Author | License / note |",
        "|---|---|---|---|---|---|",
    ]
    failures: list[str] = []

    for index, source in enumerate(SOURCES):
        player = str(source["player"])
        output_name = str(source["file"])
        kind = str(source["kind"])
        destination = root / output_name
        record: dict[str, Any] = {
            "player": player,
            "file": output_name,
            "status": "failed",
            "asset_type": kind,
            "dimensions": None,
            "sha256": None,
        }

        try:
            if kind == "placeholder":
                create_placeholder(destination)
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                note = str(source["note"])
                record.update(
                    {
                        "status": "placeholder",
                        "dimensions": [512, 512],
                        "sha256": digest,
                        "wikidata_id": source["wikidata_id"],
                        "note": note,
                    }
                )
                attributions.append(
                    f"| {player} | Placeholder | Generated locally | — | BarcharRace asset workflow | {note} |"
                )
                print(f"PLACEHOLDER: {player} -> {output_name}")
            else:
                commons_file = str(source["commons_file"])
                source_url = commons_page_url(commons_file)
                raw_path = raw / f"{output_name}.download"
                centering_values = source.get("centering", [0.5, 0.5])
                centering = (float(centering_values[0]), float(centering_values[1]))

                download(commons_thumbnail_url(commons_file), raw_path)
                convert_square(raw_path, destination, centering)
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()

                record.update(
                    {
                        "status": "ok",
                        "dimensions": [512, 512],
                        "sha256": digest,
                        "wikidata_id": source["wikidata_id"],
                        "commons_file": commons_file,
                        "source_url": source_url,
                        "author": source["author"],
                        "license": source["license"],
                        "centering": list(centering),
                    }
                )
                author = str(source["author"]).replace("|", "/")
                license_name = str(source["license"]).replace("|", "/")
                attributions.append(
                    f"| {player} | Photograph | Wikimedia Commons | {source_url} | {author} | {license_name} |"
                )
                print(f"OK: {player} -> {output_name}")
        except Exception as exc:
            message = f"{player}: {type(exc).__name__}: {exc}"
            failures.append(message)
            record["error"] = message
            attributions.append(
                f"| {player} | FAILED | — | — | — | {message.replace('|', '/')} |"
            )
            print(f"FAILED: {message}", file=sys.stderr)

        manifest.append(record)
        if kind == "photo" and index < len(SOURCES) - 1:
            time.sleep(4)

    photo_count = sum(item["status"] == "ok" for item in manifest)
    placeholder_count = sum(item["status"] == "placeholder" for item in manifest)
    valid_asset_count = photo_count + placeholder_count

    (root / "ATTRIBUTIONS.md").write_text("\n".join(attributions) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "expected_assets": len(SOURCES),
                "valid_assets": valid_asset_count,
                "photograph_count": photo_count,
                "placeholder_count": placeholder_count,
                "failed_assets": len(failures),
                "items": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "DOWNLOAD_FAILURES.log").write_text(
        "\n".join(failures) + ("\n" if failures else "No asset failures.\n"),
        encoding="utf-8",
    )

    with zipfile.ZipFile("photos.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            archive.write(path, arcname=f"photos/{path.name}")

    if failures or valid_asset_count != len(SOURCES):
        print(f"Artifact created with {len(failures)} failure(s).", file=sys.stderr)
        return 1

    print("Artifact created successfully with 14 photographs and 1 approved placeholder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
