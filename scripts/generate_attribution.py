"""Write ATTRIBUTION.md from the source manifest (data/sources.json).

Run from the repo root after changing the manifest, and commit the result:

    python scripts/generate_attribution.py

A test fails while the committed file differs from what this script writes.
"""

import sys
from pathlib import Path

from src import config
from src.rag.sources import ManifestError, load_manifest, render_attribution


def write_attribution(manifest: Path | None = None, target: Path | None = None) -> int:
    """Render the attribution for every manifest source into the target file; return the count."""
    target = target or config.ATTRIBUTION_PATH
    sources = load_manifest(manifest)
    target.write_text(render_attribution(sources), encoding="utf-8", newline="\n")
    return len(sources)


def main() -> int:
    """Write ATTRIBUTION.md; return 0 on success, 1 if the manifest is invalid."""
    try:
        count = write_attribution()
    except ManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {config.ATTRIBUTION_PATH.name} with {count} sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
