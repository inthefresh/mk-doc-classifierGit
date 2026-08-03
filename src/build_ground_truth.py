"""Phase 1: build ground-truth labels for package_01.

Extracts page text from each original (unshuffled) document, then labels every
page of the shuffled package PDF by exact string match against that text.
"""
from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

SHUFFLED_PDF = DATA_DIR / "01.990145627_shuffled.pdf"

SOURCE_DOCS = {
    DATA_DIR / "1003 - URLA_990145627.pdf": "URLA_1003",
    DATA_DIR / "Credit Report_990145627.pdf": "CREDIT_REPORT",
    DATA_DIR / "INCOME - P & L_990145627.pdf": "INCOME_DOC",
    DATA_DIR / "Title Report_990145627.pdf": "TITLE_REPORT",
}

OUTPUT_CSV = OUTPUT_DIR / "ground_truth_package01.csv"


def extract_page_texts(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def build_label_lookup(source_docs: dict[Path, str]) -> dict[str, str]:
    """Map page text -> label, built from all original documents."""
    lookup: dict[str, str] = {}
    for pdf_path, label in source_docs.items():
        for page_num, text in enumerate(extract_page_texts(pdf_path)):
            if text in lookup and lookup[text] != label:
                logger.warning(
                    "Same page text maps to two different labels (%s vs %s): %s p.%d",
                    lookup[text], label, pdf_path.name, page_num,
                )
            lookup[text] = label
    return lookup


def label_shuffled_pages(shuffled_pdf: Path, lookup: dict[str, str]) -> list[tuple[int, str]]:
    """page_idx is 0-based, in shuffled-PDF page order."""
    rows: list[tuple[int, str]] = []
    for page_idx, text in enumerate(extract_page_texts(shuffled_pdf)):
        label = lookup.get(text, "UNMATCHED")
        if label == "UNMATCHED":
            preview = text[:80].replace("\n", " ")
            logger.warning("page_idx=%d did not match any source page. preview=%r", page_idx, preview)
        rows.append((page_idx, label))
    return rows


def write_csv(rows: list[tuple[int, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["page_idx", "label"])
        writer.writerows(rows)


def main() -> None:
    for path in [SHUFFLED_PDF, *SOURCE_DOCS.keys()]:
        if not path.exists():
            raise FileNotFoundError(f"Missing input file: {path}")

    lookup = build_label_lookup(SOURCE_DOCS)
    rows = label_shuffled_pages(SHUFFLED_PDF, lookup)
    write_csv(rows, OUTPUT_CSV)

    counts = Counter(label for _, label in rows)
    logger.info("Wrote %d rows to %s", len(rows), OUTPUT_CSV)
    logger.info("Label distribution: %s", dict(counts))


if __name__ == "__main__":
    main()
