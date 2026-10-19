"""Tests for scripts/prepare_usda.py on a small made-up USDA zip, and for the committed table."""

import csv
import zipfile
from pathlib import Path

import pytest

from scripts import prepare_usda
from src import config
from src.tools.food import TABLE_COLUMNS, load_food_table

FIXTURES = Path(__file__).parent / "fixtures" / "usda"
RELEASE_FOLDER = "FoodData_Central_foundation_food_csv_2026-04-30"


def make_zip(
    directory: Path,
    folder: str | None = RELEASE_FOLDER,
    members: tuple[str, ...] = ("food.csv", "food_nutrient.csv"),
    name: str = "FoodData_Central_foundation_food_csv_2026-04-30.zip",
) -> Path:
    """Zip the fixture CSVs as USDA ships them (inside a release folder); return the zip path."""
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            arcname = f"{folder}/{member}" if folder else member
            archive.write(FIXTURES / member, arcname)
    return path


def prepared(tmp_path: Path) -> tuple[prepare_usda.Summary, Path]:
    """Run the script's writer on the fixture zip into a temp file; return the summary and path."""
    target = tmp_path / "usda_foods.csv"
    summary = prepare_usda.write_table(make_zip(tmp_path), target)
    return summary, target


def table_rows(path: Path) -> dict[str, dict[str, str]]:
    """Read a written table (skipping the credit lines) into rows keyed by description."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line[:1] != "#"]
    return {row["description"]: row for row in csv.DictReader(lines)}


def test_only_complete_foundation_foods_are_written(tmp_path):
    """Lab samples, foods without energy or a macronutrient, and repeats are left out."""
    _, target = prepared(tmp_path)
    assert set(table_rows(target)) == {
        "Bananas, raw",
        "Broccoli, raw",
        "Chicken, breast, raw",
        "Oats, whole grain, rolled",
        "Rice, white, raw",
    }


def test_columns_are_the_ones_the_lookup_reads(tmp_path):
    """The header row is exactly the columns load_food_table expects."""
    _, target = prepared(tmp_path)
    header = next(
        line for line in target.read_text(encoding="utf-8").splitlines() if line[0] != "#"
    )
    assert tuple(header.split(",")) == TABLE_COLUMNS


def test_values_come_from_the_preferred_nutrient_ids(tmp_path):
    """Energy prefers 2048, then 2047, then 1008; fiber prefers 1079, then 2033."""
    _, target = prepared(tmp_path)
    rows = table_rows(target)
    oats = rows["Oats, whole grain, rolled"]
    assert (oats["kcal"], oats["protein_g"], oats["carbohydrate_g"], oats["fat_g"]) == (
        "370",
        "13.2",
        "68",
        "6.4",
    )
    assert oats["fiber_g"] == "10"
    assert rows["Bananas, raw"]["kcal"] == "97"
    assert rows["Bananas, raw"]["fiber_g"] == "1.7"
    assert rows["Chicken, breast, raw"]["kcal"] == "120"


def test_an_amount_that_is_not_a_number_counts_as_missing(tmp_path):
    """Rice's 2048 value is "n/a", so its energy falls back to 2047."""
    _, target = prepared(tmp_path)
    assert table_rows(target)["Rice, white, raw"]["kcal"] == "352"


def test_negative_values_become_zero(tmp_path):
    """A slightly negative carbohydrate-by-difference value is written as 0."""
    _, target = prepared(tmp_path)
    assert table_rows(target)["Chicken, breast, raw"]["carbohydrate_g"] == "0"


def test_missing_fiber_is_left_empty(tmp_path):
    """A food without a fiber value keeps an empty cell (not reported), not 0."""
    _, target = prepared(tmp_path)
    assert table_rows(target)["Chicken, breast, raw"]["fiber_g"] == ""


def test_a_repeated_name_keeps_the_latest_publication(tmp_path):
    """Two broccoli entries whose names differ only in spacing: the newer one is kept."""
    _, target = prepared(tmp_path)
    broccoli = table_rows(target)["Broccoli, raw"]
    assert (broccoli["fdc_id"], broccoli["kcal"]) == ("1006", "39")


def test_every_nutrient_column_has_its_ids():
    """The nutrient IDs cover the table's nutrient columns, in the order they are written."""
    assert tuple(prepare_usda.NUTRIENT_IDS) == TABLE_COLUMNS[2:]


def test_names_are_normalised():
    """No-break spaces, repeated and trailing whitespace are cleaned from a USDA name."""
    assert prepare_usda._clean_name("Beef,\u00a0tenderloin  steak, raw ") == (
        "Beef, tenderloin steak, raw"
    )


def test_the_file_credits_usda_fooddata_central(tmp_path):
    """The first lines credit USDA FoodData Central, the release, CC0 and say no endorsement."""
    _, target = prepared(tmp_path)
    credit = [line for line in target.read_text(encoding="utf-8").splitlines() if line[0] == "#"]
    text = " ".join(credit)
    assert target.read_text(encoding="utf-8").startswith("# Source: U.S. Department of Agriculture")
    assert "FoodData Central: Foundation Foods, release 2026-04-30" in text
    assert "https://fdc.nal.usda.gov/" in text
    assert "CC0 1.0" in text
    assert "No endorsement by USDA is implied." in text
    assert "Atwater specific factors where reported" in text


def test_summary_counts_what_was_left_out(tmp_path):
    """Two incomplete foods (olive oil, butter) and one repeated name are counted."""
    summary, _ = prepared(tmp_path)
    assert summary == prepare_usda.Summary(
        release="2026-04-30", written=5, incomplete=2, repeated=1
    )


def test_output_is_sorted_and_reproducible(tmp_path):
    """Rows are sorted by name, and a second run writes the same bytes."""
    _, target = prepared(tmp_path)
    first = target.read_bytes()
    names = list(table_rows(target))
    assert names == sorted(names, key=str.casefold)
    prepare_usda.write_table(make_zip(tmp_path), target)
    assert target.read_bytes() == first


def test_written_table_loads_in_the_lookup(tmp_path):
    """The lookup's loader reads the written file."""
    _, target = prepared(tmp_path)
    foods = load_food_table(target)
    assert len(foods) == 5


def test_release_date_from_the_zip_name_when_there_is_no_folder(tmp_path):
    """A zip with the CSVs at its root still gets the release date from its own name."""
    target = tmp_path / "out.csv"
    summary = prepare_usda.write_table(make_zip(tmp_path, folder=None), target)
    assert summary.release == "2026-04-30"


def test_a_zip_without_a_release_date_is_refused(tmp_path):
    """Neither the folder nor the file name gives a date: refused."""
    path = make_zip(tmp_path, folder="data", name="foods.zip")
    with pytest.raises(prepare_usda.PrepareError, match="release date"):
        prepare_usda.write_table(path, tmp_path / "out.csv")


def test_a_zip_without_the_nutrient_file_is_refused(tmp_path):
    """The zip must hold food_nutrient.csv."""
    path = make_zip(tmp_path, members=("food.csv",))
    with pytest.raises(prepare_usda.PrepareError, match="food_nutrient.csv"):
        prepare_usda.write_table(path, tmp_path / "out.csv")


def test_an_oversized_member_is_refused(tmp_path, monkeypatch):
    """A CSV bigger than the configured limit is not read (zip bomb guard)."""
    monkeypatch.setattr(config, "USDA_MAX_MEMBER_BYTES", 100)
    with pytest.raises(prepare_usda.PrepareError, match="too large"):
        prepare_usda.write_table(make_zip(tmp_path), tmp_path / "out.csv")


def test_find_zip_needs_exactly_one_zip(tmp_path):
    """No zip and several zips are errors; one zip is found."""
    with pytest.raises(prepare_usda.PrepareError, match="Download the Foundation Foods CSV"):
        prepare_usda.find_zip(tmp_path)
    first = make_zip(tmp_path)
    assert prepare_usda.find_zip(tmp_path) == first
    make_zip(tmp_path, name="FoodData_Central_foundation_food_csv_2025-12-18.zip")
    with pytest.raises(prepare_usda.PrepareError, match="Several zips"):
        prepare_usda.find_zip(tmp_path)


def test_main_writes_the_table_from_the_only_zip(tmp_path, monkeypatch, capsys):
    """With no argument the script uses the zip in the USDA folder and reports the counts."""
    make_zip(tmp_path)
    monkeypatch.setattr(config, "USDA_RAW_DIR", tmp_path)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "usda_foods.csv")
    assert prepare_usda.main([]) == 0
    assert (tmp_path / "usda_foods.csv").exists()
    assert "5 foods from the 2026-04-30 release" in capsys.readouterr().out


def test_main_reports_a_missing_zip(tmp_path, monkeypatch, capsys):
    """No zip in the folder: exit code 1 and a hint where to download it."""
    monkeypatch.setattr(config, "USDA_RAW_DIR", tmp_path)
    assert prepare_usda.main([]) == 1
    assert "https://fdc.nal.usda.gov/download-datasets/" in capsys.readouterr().err


def test_main_reports_a_broken_zip(tmp_path, monkeypatch, capsys):
    """A file that is not a zip gives exit code 1, not a traceback."""
    broken = tmp_path / "FoodData_Central_foundation_food_csv_2026-04-30.zip"
    broken.write_text("not a zip", encoding="utf-8")
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "usda_foods.csv")
    assert prepare_usda.main([str(broken)]) == 1
    assert "Error:" in capsys.readouterr().err


@pytest.mark.parametrize("error", [RuntimeError, NotImplementedError])
def test_main_reports_an_unreadable_member(tmp_path, monkeypatch, capsys, error):
    """An encrypted or unsupported-compression member gives exit code 1, not a traceback."""

    def refuse(*_, **__):
        """Raise what zipfile raises for an encrypted or unsupported member."""
        raise error("cannot read")

    path = make_zip(tmp_path)
    monkeypatch.setattr(zipfile.ZipFile, "open", refuse)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "usda_foods.csv")
    assert prepare_usda.main([str(path)]) == 1
    assert "encrypted or uses an unsupported compression method" in capsys.readouterr().err
    assert not (tmp_path / "usda_foods.csv").exists()


def test_committed_table_is_valid_and_credits_usda():
    """data/usda_foods.csv loads, credits USDA FoodData Central and has no repeated names."""
    text = config.USDA_FOODS_PATH.read_text(encoding="utf-8")
    assert text.startswith("# Source: U.S. Department of Agriculture")
    assert "FoodData Central: Foundation Foods" in text
    foods = load_food_table(config.USDA_FOODS_PATH)
    names = [food.description.casefold() for food in foods]
    assert len(names) == len(set(names))
    assert len(foods) > 100
