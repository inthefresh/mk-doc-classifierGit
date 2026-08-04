"""Phase 7: package_02 submission summary (no ground truth available).

Input: outputs/final_result_package02.csv, outputs/reconstructed_docs_package02.csv,
       outputs/llm_result_package02.csv.
Output: outputs/summary_package02.md, outputs/package02_visualization.png.
"""
from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"

LABELS = ["URLA_1003", "INCOME_DOC", "CREDIT_REPORT", "TITLE_REPORT", "OTHER"]
LABEL_COLORS = {
    "URLA_1003": "#4C72B0",
    "INCOME_DOC": "#DD8452",
    "CREDIT_REPORT": "#55A868",
    "TITLE_REPORT": "#C44E52",
    "OTHER": "#8C8C8C",
}


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_summary_md(final_rows: list[dict], sub_docs: list[dict], llm_rows: list[dict]) -> str:
    total_pages = len(final_rows)
    label_counts = Counter(r["label"] for r in final_rows)
    subdoc_counts = Counter(d["label"] for d in sub_docs)
    source_counts = Counter(r["source"] for r in final_rows)
    llm_by_idx = {int(r["page_idx"]): r for r in llm_rows}

    lines = ["# package_02 submission summary", ""]

    lines.append("## Label distribution")
    lines.append("")
    lines.append("| label | pages | sub-documents |")
    lines.append("|---|---|---|")
    for label in LABELS:
        lines.append(f"| {label} | {label_counts.get(label, 0)} | {subdoc_counts.get(label, 0)} |")
    lines.append(f"| **total** | **{total_pages}** | **{len(sub_docs)}** |")
    lines.append("")

    lines.append("## Classification source")
    lines.append("")
    lines.append("| source | pages | share |")
    lines.append("|---|---|---|")
    for source in sorted(source_counts):
        count = source_counts[source]
        lines.append(f"| {source} | {count} | {count / total_pages:.1%} |")
    lines.append("")

    lines.append("## Sub-documents")
    lines.append("")
    lines.append("| label | sub_doc_id | start_page | end_page | page_count | total_pages_declared | ordering_method |")
    lines.append("|---|---|---|---|---|---|---|")
    for d in sub_docs:
        indices = [int(x) for x in d["ordered_page_indices"].split(",")]
        lines.append(
            f"| {d['label']} | {d['sub_doc_id']} | {indices[0]} | {indices[-1]} | "
            f"{len(indices)} | {d['total_pages_declared'] or '-'} | {d['ordering_method']} |"
        )
    lines.append("")

    lines.append("## Known unresolved cases")
    lines.append("")
    issues = []
    for d in sub_docs:
        if d["ordering_method"] != "page_number" or not d["total_pages_declared"]:
            continue
        indices = [int(x) for x in d["ordered_page_indices"].split(",")]
        declared = int(d["total_pages_declared"])
        if len(indices) > declared:
            issues.append(
                f"- **{d['sub_doc_id']}**: {len(indices)} pages collected but the form declares "
                f"\"of {declared}\" -- likely {round(len(indices) / declared)} separate document instances "
                f"merged into one sub_doc (same total_pages_declared, no distinguishing ID left in the "
                f"anonymized text). Pages: {d['ordered_page_indices']}"
            )
        elif len(indices) < declared:
            issues.append(
                f"- **{d['sub_doc_id']}**: only {len(indices)} of the {declared} declared pages carry this "
                f"label. The remaining page(s) of this document may be classified under a different label "
                f"or missing from the package. Pages: {d['ordered_page_indices']}"
            )
    final_by_idx = {int(r["page_idx"]): r for r in final_rows}
    for page_idx, llm_row in sorted(llm_by_idx.items()):
        current_source = final_by_idx[page_idx]["source"]
        if llm_row["confidence"] != "high" and current_source == "llm":
            issues.append(
                f"- **page_idx={page_idx}** classified `{llm_row['label']}` with confidence=`{llm_row['confidence']}`: "
                f"{llm_row['reasoning']}"
            )
    if issues:
        lines.extend(issues)
    else:
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def build_visualization(final_rows: list[dict], output_path: Path) -> None:
    rows_by_idx = {int(r["page_idx"]): r for r in final_rows}
    n_pages = len(rows_by_idx)

    fig, ax = plt.subplots(figsize=(14, 2.2))
    for page_idx in range(n_pages):
        label = rows_by_idx[page_idx]["label"]
        ax.add_patch(mpatches.Rectangle((page_idx, 0), 1, 1, color=LABEL_COLORS[label]))

    ax.set_xlim(0, n_pages)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xticks(range(0, n_pages, 2))
    ax.set_xlabel("shuffled page_idx")
    ax.set_title(f"package_02: label per shuffled page ({n_pages} pages) -- label-interleaved shuffle pattern")

    handles = [mpatches.Patch(color=color, label=label) for label, color in LABEL_COLORS.items()]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=5, frameon=False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> None:
    final_rows = load_csv(OUTPUT_DIR / "final_result_package02.csv")
    sub_docs = load_csv(OUTPUT_DIR / "reconstructed_docs_package02.csv")
    llm_rows = load_csv(OUTPUT_DIR / "llm_result_package02.csv")

    summary_md = build_summary_md(final_rows, sub_docs, llm_rows)
    summary_path = OUTPUT_DIR / "summary_package02.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    logger.info("Wrote %s", summary_path)

    viz_path = OUTPUT_DIR / "package02_visualization.png"
    build_visualization(final_rows, viz_path)
    logger.info("Wrote %s", viz_path)


if __name__ == "__main__":
    main()
