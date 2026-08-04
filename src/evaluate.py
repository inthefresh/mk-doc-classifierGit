"""Phase 6: evaluate final_result_package01.csv against ground truth.

package_01 only -- the one package with known labels.

Input: outputs/final_result_package01.csv, outputs/ground_truth_package01.csv,
       outputs/llm_result_package01.csv (for reasoning/confidence on LLM rows),
       outputs/package01_pages.json (for text preview on misclassified pages).
Output: outputs/evaluation_report_package01.csv (misclassification detail).
Console: accuracy, confusion matrix, per-source accuracy.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"

LABELS = ["URLA_1003", "INCOME_DOC", "CREDIT_REPORT", "TITLE_REPORT", "OTHER"]

TEXT_PREVIEW_LEN = 100


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_pages_text(package_name: str) -> dict[int, str]:
    path = OUTPUT_DIR / f"{package_name}_pages.json"
    with path.open(encoding="utf-8") as f:
        return {p["page_idx"]: p["text"] for p in json.load(f)}


def build_confusion_matrix(rows: list[dict]) -> dict[tuple[str, str], int]:
    matrix: dict[tuple[str, str], int] = Counter()
    for row in rows:
        matrix[(row["actual"], row["predicted"])] += 1
    return matrix


def print_confusion_matrix(matrix: dict[tuple[str, str], int]) -> None:
    row_label_width = max(len(label) for label in LABELS) + 2
    col_width = max(len(label) for label in LABELS) + 2
    header = " " * row_label_width + "".join(f"{label:>{col_width}}" for label in LABELS)
    print(header)
    for actual in LABELS:
        row_str = f"{actual:<{row_label_width}}" + "".join(
            f"{matrix.get((actual, predicted), 0):>{col_width}}" for predicted in LABELS
        )
        print(row_str)


def main() -> None:
    final_rows = load_csv(OUTPUT_DIR / "final_result_package01.csv")
    gt_rows = load_csv(OUTPUT_DIR / "ground_truth_package01.csv")
    llm_rows = load_csv(OUTPUT_DIR / "llm_result_package01.csv")
    pages_text = load_pages_text("package01")

    gt_by_idx = {int(r["page_idx"]): r["label"] for r in gt_rows}
    llm_by_idx = {int(r["page_idx"]): r for r in llm_rows}
    final_by_idx = {int(r["page_idx"]): r for r in final_rows}

    eval_rows = []
    for page_idx in sorted(final_by_idx):
        final_row = final_by_idx[page_idx]
        actual = gt_by_idx[page_idx]
        predicted = final_row["label"]
        source = final_row["source"]
        eval_rows.append({
            "page_idx": page_idx,
            "actual": actual,
            "predicted": predicted,
            "source": source,
            "correct": actual == predicted,
        })

    total = len(eval_rows)
    correct = sum(1 for r in eval_rows if r["correct"])
    accuracy = correct / total

    print(f"\n=== package_01 evaluation ({total} pages) ===")
    print(f"Overall accuracy: {correct}/{total} ({accuracy:.1%})")

    print("\nConfusion matrix (rows=actual, cols=predicted):")
    matrix = build_confusion_matrix(eval_rows)
    print_confusion_matrix(matrix)

    print("\nAccuracy by source:")
    for source in ["rule", "llm"]:
        source_rows = [r for r in eval_rows if r["source"] == source]
        if not source_rows:
            continue
        source_correct = sum(1 for r in source_rows if r["correct"])
        print(f"  {source}: {source_correct}/{len(source_rows)} ({source_correct / len(source_rows):.1%})")

    misclassified = [r for r in eval_rows if not r["correct"]]
    print(f"\nMisclassified pages: {len(misclassified)}")

    report_rows = []
    for r in misclassified:
        page_idx = r["page_idx"]
        text_preview = pages_text[page_idx][:TEXT_PREVIEW_LEN].replace("\n", " ")
        llm_info = llm_by_idx.get(page_idx)
        report_rows.append({
            "page_idx": page_idx,
            "actual": r["actual"],
            "predicted": r["predicted"],
            "source": r["source"],
            "text_preview": text_preview,
            "confidence": llm_info["confidence"] if llm_info else "",
            "reasoning": llm_info["reasoning"] if llm_info else "",
        })

    report_path = OUTPUT_DIR / "evaluation_report_package01.csv"
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "page_idx", "actual", "predicted", "source", "text_preview", "confidence", "reasoning",
        ])
        writer.writeheader()
        writer.writerows(report_rows)

    logger.info("Wrote %d misclassification rows to %s", len(report_rows), report_path)


if __name__ == "__main__":
    main()
