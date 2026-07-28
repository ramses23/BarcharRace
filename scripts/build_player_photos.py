from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

USER_AGENT = (
    "BarcharRace-photo-builder/1.1 "
    "(https://github.com/ramses23/BarcharRace; licensed asset preparation)"
)

# Every configured Commons file was selected for the named person. The script
# never substitutes a failed image with another player or an unrelated object.
SOURCES: list[dict[str, str | None]] = [
    {
        "player": "Cristiano Ronaldo",
        "file": "cristiano_ronaldo.png",
        "wikidata_id": "Q11571",
        "commons_file": "Cristiano Ronaldo Croatia v Portugal 2 July 2026-075 (cropped).jpg",
        "author": "Bryan Berlin",
        "license": "CC BY-SA 4.0",
    },
    {
        "player": "Lionel Messi",
        "file": "lionel_messi.png",
        "wikidata_id": "Q615",
        "commons_file": "Leo Messi Argentina v Egypt 7 July 2026-1.jpg",
        "author": "Bryan Berlin",
        "license": "CC BY-SA 4.0",
    },
    {
        "player": "Pelé",
        "file": "pele.png",
        "wikidata_id": "Q12897",
        "commons_file": "Pele con brasil (cropped).jpg",
        "author": "Unknown author",
        "license": "Public domain",
    },
    {
        "player": "Romário",
        "file": "romario.png",
        "wikidata_id": "Q178649",
        "commons_file": "Senadores da 57ª Legislatura (52689451805).jpg",
        "author": "Agência Senado",
        "license": "CC BY 2.0",
    },
    {
        "player": "Ferenc Puskás",
        "file": "ferenc_puskas.png",
        "wikidata_id": "Q482931",
        "commons_file": "Ferenc Puskás (cropped).jpg",
        "author": "Anefo",
        "license": "CC0",
    },
    {
        "player": "Josef Bican",
        "file": "josef_bican.png",
        "wikidata_id": "Q352017",
        "commons_file": "Josef Bican 1940.jpg",
        "author": "Unknown author; re-photo by David Sedlecký",
        "license": "Public domain",
    },
    {
        "player": "Robert Lewandowski",
        "file": "robert_lewandowski.png",
        "wikidata_id": "Q151269",
        "commons_file": "Robert Lewandowski 2018, JAP-POL (cropped).jpg",
        "author": "Svetlana Beketova",
        "license": "CC BY-SA 3.0",
    },
    {
        "player": "Jimmy Jones",
        "file": "jimmy_jones.png",
        "wikidata_id": "Q3179067",
        "commons_file": "Jimmy jones.jpg",
        "author": "Tumijo",
        "license": "CC BY-SA 4.0",
    },
    {
        "player": "Gerd Müller",
        "file": "gerd_muller.png",
        "wikidata_id": "Q152871",
        "commons_file": "BOMBERGERDMUELLER (headshot).JPG",
        "author": "Alexander Hauk / Promifotos.de",
        "license": "CC BY-SA 3.0",
    },
    {
        "player": "Joe Bambrick",
        "file": "joe_bambrick.png",
        "wikidata_id": "Q2056445",
        "commons_file": None,
        "author": None,
        "license": None,
    },
    {
        "player": "Abe Lenstra",
        "file": "abe_lenstra.png",
        "wikidata_id": "Q318173",
        "commons_file": "Abe Lenstra (Heerenveen) in het Olympisch Stadion in Amsterdam, enige dagen na d, Bestanddeelnr 191-1062.jpg",
        "author": "Willem van de Poll",
        "license": "CC0",
    },
    {
        "player": "Luis Suárez",
        "file": "luis_suarez.png",
        "wikidata_id": "Q26517",
        "commons_file": "U09 Luis Suárez 3470.jpg",
        "author": "Ailura",
        "license": "CC BY-SA 3.0 AT",
    },
    {
        "player": "Túlio Maravilha",
        "file": "tulio_maravilha.png",
        "wikidata_id": "Q714354",
        "commons_file": "Tulio no Itumbiara (cropped).JPG",
        "author": "Thiago Souza",
        "license": "CC BY-SA 3.0",
    },
    {
        "player": "Eusébio",
        "file": "eusebio.png",
        "wikidata_id": "Q17163",
        "commons_file": "Eusebio1972.jpg",
        "author": "Rob Mieremet",
        "license": "CC0",
    },
    {
        "player": "Zlatan Ibrahimović",
        "file": "zlatan_ibrahimovic.png",
        "wikidata_id": "Q46896",
        "commons_file": "Zlatan Ibrahimović.jpg",
        "author": "Gerard Reyes",
        "license": "CC BY 2.0",
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


def convert_square(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(
            image,
            (512, 512),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        image.save(destination, "PNG", optimize=True)

    with Image.open(destination) as check:
        check.verify()
    with Image.open(destination) as check:
        if check.format != "PNG" or check.size != (512, 512):
            raise RuntimeError(f"Invalid converted image: {destination}")


def main() -> int:
    root = Path("photos")
    raw = Path(".photo-downloads")
    root.mkdir(exist_ok=True)
    raw.mkdir(exist_ok=True)

    for old_png in root.glob("*.png"):
        old_png.unlink()

    manifest: list[dict[str, Any]] = []
    attributions = [
        "# Player photo attributions",
        "",
        "All included images are real photographs. Wikimedia Commons files were transformed only by centered square cropping and resizing to 512 × 512 pixels.",
        "",
        "| Player | Source | File URL | Author | License |",
        "|---|---|---|---|---|",
    ]
    failures: list[str] = []

    for index, source in enumerate(SOURCES):
        player = str(source["player"])
        output_name = str(source["file"])
        commons_file = source["commons_file"]
        record: dict[str, Any] = {
            "player": player,
            "file": output_name,
            "status": "failed",
            "dimensions": None,
            "sha256": None,
        }

        try:
            if not commons_file:
                raise RuntimeError(
                    "No eligible reusable portrait source found. Wikimedia Commons contains only plaque photographs; available trading-card scans do not provide a reusable licence."
                )

            commons_file = str(commons_file)
            source_url = commons_page_url(commons_file)
            raw_path = raw / f"{output_name}.download"
            destination = root / output_name

            download(commons_thumbnail_url(commons_file), raw_path)
            convert_square(raw_path, destination)
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
                }
            )
            author = str(source["author"]).replace("|", "/")
            license_name = str(source["license"]).replace("|", "/")
            attributions.append(
                f"| {player} | Wikimedia Commons | {source_url} | {author} | {license_name} |"
            )
            print(f"OK: {player} -> {output_name}")
        except Exception as exc:
            message = f"{player}: {type(exc).__name__}: {exc}"
            failures.append(message)
            record["error"] = message
            attributions.append(f"| {player} | FAILED | — | — | — |")
            print(f"FAILED: {message}", file=sys.stderr)

        manifest.append(record)
        if index < len(SOURCES) - 1:
            time.sleep(4)

    (root / "ATTRIBUTIONS.md").write_text("\n".join(attributions) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "expected_images": len(SOURCES),
                "successful_images": sum(item["status"] == "ok" for item in manifest),
                "failed_images": sum(item["status"] != "ok" for item in manifest),
                "items": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "DOWNLOAD_FAILURES.log").write_text(
        "\n".join(failures) + ("\n" if failures else "No download failures.\n"),
        encoding="utf-8",
    )

    with zipfile.ZipFile("photos.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            archive.write(path, arcname=f"photos/{path.name}")

    if failures:
        print(f"Artifact created with {len(failures)} failure(s).", file=sys.stderr)
        return 1

    print("Artifact created successfully with all 15 photographs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
