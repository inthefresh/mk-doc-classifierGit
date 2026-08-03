"""Phase 3: keyword-rule based page classification (CONFIRMED/UNCERTAIN).

Input: outputs/{package_name}_pages.json (Phase 2 output).
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"

UNCERTAIN = "UNCERTAIN"
LOW_TEXT_REASON = "low_text"
NO_MATCH_REASON = "no_match"
CONFLICT_REASON = "conflict"

# Verified against package_01's 4 source documents (coverage + false-positive check).
KEYWORDS: dict[str, list[str]] = {
    "URLA_1003": ["uniform residential loan application"],
    "CREDIT_REPORT": [
        "broomall", "transunion", "experian", "equifax", "credit score",
        "repositories", "client code", "order verifications", "xactus",
    ],
    "TITLE_REPORT": ["title insurance", "preliminary report", "title company", "fidelity national", "clta", "escrow"],
    # INCOME_DOC: intentionally no keywords. package_01 has only 1 P&L page,
    # not enough to validate a generalized rule -> always falls through to UNCERTAIN.
}

# URLA_1003 has one highly specific keyword: a single match confirms it.
# CREDIT_REPORT / TITLE_REPORT need >=2 matches to confirm.
MIN_MATCHES = {
    "URLA_1003": 1,
    "CREDIT_REPORT": 2,
    "TITLE_REPORT": 2,
}

PACKAGES = ["package01", "package02"]


def classify_page(text: str, is_low_text: bool) -> dict:
    if is_low_text:
        return {"label": UNCERTAIN, "matched_keywords": "", "status": "UNCERTAIN", "reason": LOW_TEXT_REASON}

    text_lower = text.lower()
    matches_by_label = {
        label: [kw for kw in keywords if kw in text_lower]
        for label, keywords in KEYWORDS.items()
    }
    confirmed = [label for label, matched in matches_by_label.items() if len(matched) >= MIN_MATCHES[label]]
    all_matched = [kw for matched in matches_by_label.values() for kw in matched]

    if len(confirmed) == 1:
        label = confirmed[0]
        return {
            "label": label,
            "matched_keywords": ", ".join(matches_by_label[label]),
            "status": "CONFIRMED",
            "reason": "",
        }

    if len(confirmed) >= 2:
        return {
            "label": UNCERTAIN,
            "matched_keywords": ", ".join(all_matched),
            "status": "UNCERTAIN",
            "reason": CONFLICT_REASON,
        }

    return {
        "label": UNCERTAIN,
        "matched_keywords": ", ".join(all_matched),
        "status": "UNCERTAIN",
        "reason": NO_MATCH_REASON,
    }


def process_package(package_name: str) -> list[dict]:
    input_path = OUTPUT_DIR / f"{package_name}_pages.json"
    if not input_path.exists():
        raise FileNotFoundError(f"Missing Phase 2 output: {input_path}")

    with input_path.open(encoding="utf-8") as f:
        pages = json.load(f)

    rows = []
    for page in pages:
        result = classify_page(page["text"], page["is_low_text"])
        if result["reason"] == CONFLICT_REASON:
            logger.warning(
                "%s page_idx=%d: conflicting labels matched -> UNCERTAIN. matched_keywords=%s",
                package_name, page["page_idx"], result["matched_keywords"],
            )
        rows.append({"page_idx": page["page_idx"], **result})

    output_path = OUTPUT_DIR / f"rules_result_{package_name}.csv"
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page_idx", "label", "matched_keywords", "status", "reason"])
        writer.writeheader()
        writer.writerows(rows)

    confirmed_count = sum(1 for r in rows if r["status"] == "CONFIRMED")
    logger.info(
        "%s: wrote %d rows to %s (CONFIRMED=%d, UNCERTAIN=%d)",
        package_name, len(rows), output_path, confirmed_count, len(rows) - confirmed_count,
    )
    return rows


def main() -> None:
    for package_name in PACKAGES:
        process_package(package_name)


if __name__ == "__main__":
    main()
