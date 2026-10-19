"""Turn the USDA FoodData Central Foundation Foods CSV zip into data/usda_foods.csv.

Download the CSV zip by hand from https://fdc.nal.usda.gov/download-datasets/ (Foundation Foods,
CSV) into data/usda/ (gitignored), then run from the repo root and commit the result:

    python scripts/prepare_usda.py [path/to/FoodData_Central_foundation_food_csv_<date>.zip]

With no argument the script uses the one Foundation Foods zip in data/usda/. It reads the zip as
it is (nothing is unpacked to disk) and makes no network request.
"""

import csv
import io
import math
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src import config
from src.tools.food import TABLE_COLUMNS

ZIP_GLOB = "FoodData_Central_foundation_food_csv_*.zip"
RELEASE_PATTERN = re.compile(r"FoodData_Central_foundation_food_csv_(\d{4}-\d{2}-\d{2})")
# The zip also holds the lab samples behind each food; only the foods themselves are kept.
FOUNDATION_DATA_TYPE = "foundation_food"

# Nutrient IDs (nutrient.csv) for each column, most preferred first. Energy: in release
# 2026-04-30, 312 foundation foods have both 2047 (Atwater general factors: 4, 9, 4 kcal per g)
# and 2048 (specific factors per food), 35 only 2047 and 31 only the older 1008,
# which mostly matches 2048 (within 1 kcal for 70 of the 98 foods with both). 2048 comes first
# (owner's choice in T4.3): it is more exact for each food (raw almonds 584 kcal instead of 626,
# creamy peanut butter 589 instead of 632) and closer to 1008. Carbohydrate is "by difference"
# (1005). Total dietary fiber is 1079 or, for some foods, 2033 (AOAC 2011.25 method).
NUTRIENT_IDS: dict[str, tuple[str, ...]] = {
    "kcal": ("2048", "2047", "1008"),
    "protein_g": ("1003",),
    "carbohydrate_g": ("1005",),
    "fat_g": ("1004",),
    "fiber_g": ("1079", "2033"),
}
# A food without one of these is left out; fiber may be missing (shown as "not reported").
REQUIRED_COLUMNS = ("kcal", "protein_g", "carbohydrate_g", "fat_g")

CREDIT_LINES = (
    f"Source: {config.USDA_CITATION}",
    f"Licence: {config.USDA_LICENSE}, {config.USDA_LICENSE_URL}. "
    "No endorsement by USDA is implied.",
    f"Changes: made by scripts/prepare_usda.py. {config.USDA_CHANGES}",
)


class PrepareError(RuntimeError):
    """The zip is missing, ambiguous or not the Foundation Foods CSV download."""


@dataclass(frozen=True)
class Summary:
    """What one run wrote and left out."""

    release: str
    written: int
    incomplete: int
    repeated: int


def find_zip(directory: Path | None = None) -> Path:
    """Return the one Foundation Foods CSV zip in the directory, or raise PrepareError."""
    directory = directory or config.USDA_RAW_DIR
    found = sorted(directory.glob(ZIP_GLOB))
    if not found:
        raise PrepareError(
            f"No {ZIP_GLOB} in {directory}. Download the Foundation Foods CSV from "
            "https://fdc.nal.usda.gov/download-datasets/ into that folder."
        )
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        raise PrepareError(f"Several zips in {directory} ({names}); pass the one to use.")
    return found[0]


def _member(archive: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
    """Return the one member of the archive with this file name, checking its unpacked size."""
    matches = [i for i in archive.infolist() if PurePosixPath(i.filename).name == name]
    if len(matches) != 1:
        raise PrepareError(f"Expected one {name} in the zip, found {len(matches)}.")
    info = matches[0]
    if info.file_size > config.USDA_MAX_MEMBER_BYTES:
        raise PrepareError(f"{name} in the zip is too large ({info.file_size} bytes).")
    return info


def _rows(archive: zipfile.ZipFile, info: zipfile.ZipInfo):
    """Yield the rows of a CSV member as dicts, streaming it from the zip."""
    with archive.open(info) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def _release(archive: zipfile.ZipFile, zip_path: Path) -> str:
    """Return the release date (YYYY-MM-DD) from the folder inside the zip or the zip's name."""
    for name in [*archive.namelist(), zip_path.name]:
        match = RELEASE_PATTERN.search(name)
        if match:
            return match.group(1)
    raise PrepareError("Cannot tell the release date from the zip.")


def _clean_name(text: str) -> str:
    """Normalise Unicode (e.g. no-break spaces) and collapse runs of whitespace."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _amount(text: str) -> float | None:
    """Parse a nutrient amount; None if it is not a finite number. Negatives become 0."""
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    # Carbohydrate "by difference" can come out slightly below zero for meat and fish.
    return max(value, 0.0)


def _format(value: float | None) -> str:
    """Write a value with at most two decimals and no trailing zeros; empty if missing."""
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def read_table(zip_path: Path) -> tuple[str, list[dict[str, object]], int, int]:
    """Read the zip; return the release, the food rows, and the incomplete and repeated counts."""
    with zipfile.ZipFile(zip_path) as archive:
        release = _release(archive, zip_path)
        food_info = _member(archive, "food.csv")
        nutrient_info = _member(archive, "food_nutrient.csv")

        foods: dict[str, dict[str, object]] = {}
        for row in _rows(archive, food_info):
            if row.get("data_type") != FOUNDATION_DATA_TYPE:
                continue
            name = _clean_name(row.get("description") or "")
            fdc_id = (row.get("fdc_id") or "").strip()
            if name and fdc_id.isdigit():
                foods[fdc_id] = {
                    "fdc_id": fdc_id,
                    "description": name,
                    "published": row.get("publication_date") or "",
                }

        wanted = {nid for ids in NUTRIENT_IDS.values() for nid in ids}
        amounts: dict[str, dict[str, float]] = {}
        for row in _rows(archive, nutrient_info):
            fdc_id, nid = row.get("fdc_id"), row.get("nutrient_id")
            if fdc_id in foods and nid in wanted:
                value = _amount(row.get("amount") or "")
                if value is not None:
                    amounts.setdefault(fdc_id, {})[nid] = value

    complete: list[dict[str, object]] = []
    for fdc_id, food in foods.items():
        found = amounts.get(fdc_id, {})
        for column, ids in NUTRIENT_IDS.items():
            food[column] = next((found[nid] for nid in ids if nid in found), None)
        if all(food[column] is not None for column in REQUIRED_COLUMNS):
            complete.append(food)

    # The same food can appear in several releases; keep the latest publication of each name.
    latest: dict[str, dict[str, object]] = {}
    for food in complete:
        key = str(food["description"]).casefold()
        kept = latest.get(key)
        if kept is None or (food["published"], int(food["fdc_id"])) > (
            kept["published"],
            int(kept["fdc_id"]),
        ):
            latest[key] = food
    rows = sorted(latest.values(), key=lambda f: (str(f["description"]).casefold(), f["fdc_id"]))
    return release, rows, len(foods) - len(complete), len(complete) - len(rows)


def write_table(zip_path: Path, target: Path | None = None) -> Summary:
    """Write the trimmed table, with the USDA credit on top, and return a summary."""
    target = target or config.USDA_FOODS_PATH
    release, rows, incomplete, repeated = read_table(zip_path)
    if not rows:
        raise PrepareError("No foundation food with energy and macronutrients in the zip.")
    out = io.StringIO()
    for line in CREDIT_LINES:
        out.write(f"# {line.format(release=release)}\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(TABLE_COLUMNS)
    for food in rows:
        writer.writerow(
            [food["fdc_id"], food["description"]]
            + [_format(food[column]) for column in TABLE_COLUMNS[2:]]
        )
    target.write_text(out.getvalue(), encoding="utf-8", newline="\n")
    return Summary(release, len(rows), incomplete, repeated)


def main(argv: list[str] | None = None) -> int:
    """Write data/usda_foods.csv from the given or the only zip; return 0, or 1 on an error."""
    args = sys.argv[1:] if argv is None else argv
    try:
        zip_path = Path(args[0]) if args else find_zip()
        summary = write_table(zip_path)
    except (PrepareError, zipfile.BadZipFile, OSError, UnicodeDecodeError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {config.USDA_FOODS_PATH.name}: {summary.written} foods from the "
        f"{summary.release} release; left out {summary.incomplete} without energy or a "
        f"macronutrient; merged {summary.repeated} repeated names."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
