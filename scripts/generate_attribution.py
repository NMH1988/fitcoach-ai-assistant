"""Write ATTRIBUTION.md from the source manifest (data/sources.json) and the USDA foods table.

Run from the repo root after changing the manifest or the foods table, and commit the result:

    python scripts/generate_attribution.py

A test fails while the committed file differs from what this script writes.
"""

import sys
from pathlib import Path

from src import config
from src.rag.sources import ManifestError, load_manifest, render_attribution
from src.tools.food import FoodTableError, read_usda_release


def write_attribution(
    manifest: Path | None = None, target: Path | None = None, foods_table: Path | None = None
) -> int:
    """Render the credits for every manifest source and the USDA table; return the source count."""
    target = target or config.ATTRIBUTION_PATH
    sources = load_manifest(manifest)
    text = render_attribution(sources, usda_release=read_usda_release(foods_table))
    target.write_text(text, encoding="utf-8", newline="\n")
    return len(sources)


def main() -> int:
    """Write ATTRIBUTION.md; return 0 on success, 1 if the manifest or foods table is invalid."""
    try:
        count = write_attribution()
    except (ManifestError, FoodTableError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {config.ATTRIBUTION_PATH.name} with {count} sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
