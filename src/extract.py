"""Phase 2: extract per-page text and low-text flags for a shuffled package PDF."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pypdf import PdfReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

LOW_TEXT_THRESHOLD = 50

PACKAGES = {
    "package01": DATA_DIR / "01.990145627_shuffled.pdf",
    "package02": DATA_DIR / "02.990367284_shuffled.pdf",
}

# Known from prior manual inspection; checked against actual output below.
EXPECTED_LOW_TEXT = {
    "package02": [10, 25, 39],
}


def extract_pages(pdf_path: Path) -> list[dict]:
    rows = []
    reader = PdfReader(str(pdf_path))
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        char_count = len(text)
        rows.append({
            "page_idx": page_idx,
            "char_count": char_count,
            "is_low_text": char_count < LOW_TEXT_THRESHOLD,
            "text": text,
        })
    return rows


def write_json(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def low_text_indices(rows: list[dict]) -> list[int]:
    return [r["page_idx"] for r in rows if r["is_low_text"]]


def process_package(package_name: str, pdf_path: Path) -> list[dict]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing input file: {pdf_path}")

    rows = extract_pages(pdf_path)
    output_path = OUTPUT_DIR / f"{package_name}_pages.json"
    write_json(rows, output_path)

    low_idx = low_text_indices(rows)
    logger.info("%s: wrote %d pages to %s", package_name, len(rows), output_path)
    logger.info("%s: is_low_text page_idx = %s", package_name, low_idx)

    expected = EXPECTED_LOW_TEXT.get(package_name)
    if expected is not None and low_idx != expected:
        logger.warning(
            "%s: is_low_text mismatch. expected=%s actual=%s",
            package_name, expected, low_idx,
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages", nargs="*", default=list(PACKAGES.keys()),
        help="package names to process (default: all known packages)",
    )
    args = parser.parse_args()

    for name in args.packages:
        pdf_path = PACKAGES.get(name)
        if pdf_path is None:
            logger.warning("Unknown package %s, skipping", name)
            continue
        process_package(name, pdf_path)


if __name__ == "__main__":
    main()
