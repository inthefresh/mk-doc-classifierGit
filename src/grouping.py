"""Phase 5: reconstruct original document order within each label group.

Adjacent-page merging doesn't work on this dataset (the shuffle interleaves
labels at single-page granularity, so consecutive same-label pages barely
occur). Instead, pages sharing a label are pooled together and ordered using
in-text page-number footers ("Page 4 of 11", "3 of 10", etc.).

Input: outputs/final_result_{package_name}.csv (page_idx, label, source)
       outputs/{package_name}_pages.json (page_idx -> text, from Phase 2)
Output: outputs/reconstructed_docs_{package_name}.csv
        (label, sub_doc_id, ordered_page_indices, total_pages_declared, ordering_method)

Limitation: ordering within a (label, total_pages_declared) cluster assumes
each such cluster is a single document instance. If a label had multiple
instances of the same form (e.g. a co-borrower's own URLA_1003, or a repeat
credit pull), pages from different instances could share the same total and
get merged into one sub_doc incorrectly. A secondary identifier (Report ID,
applicant name, order date) would be needed to split those apart. Verified
for package_01/02 that every label is a single instance (see README), so this
is not implemented here.
"""
from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"

PACKAGES = ["package01", "package02"]

# "Page 4 of 11", "Page 2" (no total), case-insensitive.
PAGE_OF_PATTERN = re.compile(r"Page\s+(\d+)\s*(?:of\s*(\d+))?", re.IGNORECASE)
# Bare "3 of 10" footer (form code glued to the left, e.g. "GURLA20S3 of 11").
BARE_OF_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s+of\s+(\d{1,3})(?!\d)", re.IGNORECASE)

# INCOME_DOC-only secondary clustering keys (IRS Wage and Income Transcript pages).
# "Tax Period Requested" only appears on a transcript's own first page; the
# masked EIN suffix ("XX-XXX7732") repeats on every page of that same
# transcript instance, including continuation pages, so it's used to link
# continuation pages back to the header page that carries the tax period.
TAX_PERIOD_PATTERN = re.compile(r"Tax Period Requested:\s*([\d-]+)")
EIN_SUFFIX_PATTERN = re.compile(r"XX-XXX(\d{4})")

# Known correction applied post-hoc at the grouping stage (see README): this
# page's own text is too sparse (97 chars, no EIN, no tax period -- just
# boilerplate + "PAGE 2 OF 2") for rules.py/llm_classify.py or the automatic
# EIN-matching below to place it. Confirmed by manual review of the source
# PDF that it is the second page of the 2024 Wage and Income Transcript.
INCOME_DOC_MANUAL_TAX_PERIOD = {
    38: "12-31-2024",
}

KNOWN_LABEL_CORRECTIONS = {
    "package02": {
        38: {
            "label": "INCOME_DOC",
            "reason": (
                "text too sparse for rules/LLM (just boilerplate + 'PAGE 2 OF 2'); "
                "confirmed via grouping-stage reconstruction (see INCOME_DOC_MANUAL_TAX_PERIOD) "
                "to be page 2 of the 2024 Wage and Income Transcript alongside page_idx=11"
            ),
        },
    },
}


def extract_page_number(text: str) -> tuple[int | None, int | None]:
    """Returns (current_page, total_pages); total_pages may be None."""
    match = PAGE_OF_PATTERN.search(text)
    if match:
        current = int(match.group(1))
        total = int(match.group(2)) if match.group(2) else None
        return current, total

    match = BARE_OF_PATTERN.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))

    return None, None


def load_final_result(package_name: str) -> list[dict]:
    path = OUTPUT_DIR / f"final_result_{package_name}.csv"
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_final_result(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page_idx", "label", "source"])
        writer.writeheader()
        writer.writerows(rows)


def apply_known_corrections(package_name: str, rows: list[dict]) -> tuple[list[dict], bool]:
    corrections = KNOWN_LABEL_CORRECTIONS.get(package_name, {})
    if not corrections:
        return rows, False

    changed = False
    for row in rows:
        page_idx = int(row["page_idx"])
        correction = corrections.get(page_idx)
        if correction and row["label"] != correction["label"]:
            logger.warning(
                "%s page_idx=%s: relabeled %s -> %s (grouping-stage correction: %s)",
                package_name, page_idx, row["label"], correction["label"], correction["reason"],
            )
            row["label"] = correction["label"]
            row["source"] = "grouping_correction"
            changed = True
    return rows, changed


def load_pages_text(package_name: str) -> dict[int, str]:
    path = OUTPUT_DIR / f"{package_name}_pages.json"
    with path.open(encoding="utf-8") as f:
        return {p["page_idx"]: p["text"] for p in json.load(f)}


def group_by_label(rows: list[dict]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for row in sorted(rows, key=lambda r: int(r["page_idx"])):
        groups.setdefault(row["label"], []).append(int(row["page_idx"]))
    return groups


def reconstruct_label_generic(label: str, page_idxs: list[int], pages_text: dict[int, str]) -> list[dict]:
    numbered: dict[int | None, list[tuple[int, int]]] = {}
    unnumbered: list[int] = []

    for page_idx in page_idxs:
        current, total = extract_page_number(pages_text[page_idx])
        if current is None:
            unnumbered.append(page_idx)
        else:
            numbered.setdefault(total, []).append((current, page_idx))

    sub_docs = []
    for total, entries in numbered.items():
        entries.sort(key=lambda entry: entry[0])
        currents = [current for current, _ in entries]
        duplicated = {c for c in currents if currents.count(c) > 1}
        if duplicated:
            logger.warning(
                "%s total=%s: duplicate page-number(s) %s within one cluster "
                "(pages=%s) -- likely two merged document instances, not split apart",
                label, total, sorted(duplicated), [page_idx for _, page_idx in entries],
            )
        sub_docs.append({
            "label": label,
            "ordered_page_indices": [page_idx for _, page_idx in entries],
            "total_pages_declared": total,
            "ordering_method": "page_number",
        })
    for page_idx in unnumbered:
        sub_docs.append({
            "label": label,
            "ordered_page_indices": [page_idx],
            "total_pages_declared": None,
            "ordering_method": "unordered_single",
        })
    return sub_docs


def reconstruct_income_doc(page_idxs: list[int], pages_text: dict[int, str]) -> list[dict]:
    """INCOME_DOC-only: secondary-cluster each total_pages_declared bucket by
    tax period, so pages from different Wage and Income Transcript instances
    (e.g. two tax years) aren't merged just because they share the same total.
    """
    numbered: dict[int | None, list[tuple[int, int]]] = {}
    unnumbered: list[int] = []

    for page_idx in page_idxs:
        current, total = extract_page_number(pages_text[page_idx])
        if current is None:
            unnumbered.append(page_idx)
        else:
            numbered.setdefault(total, []).append((current, page_idx))

    sub_docs = []
    for total, entries in numbered.items():
        if total is None:
            # No declared total to sub-cluster by -- fall back to generic handling.
            entries.sort(key=lambda entry: entry[0])
            sub_docs.append({
                "label": "INCOME_DOC",
                "ordered_page_indices": [page_idx for _, page_idx in entries],
                "total_pages_declared": total,
                "ordering_method": "page_number",
            })
            continue

        tax_period_of: dict[int, str] = {}
        ein_suffix_of: dict[int, str] = {}
        for _, page_idx in entries:
            text = pages_text[page_idx]
            tp_match = TAX_PERIOD_PATTERN.search(text)
            if tp_match:
                tax_period_of[page_idx] = tp_match.group(1)
            ein_match = EIN_SUFFIX_PATTERN.search(text)
            if ein_match:
                ein_suffix_of[page_idx] = ein_match.group(1)

        # Link continuation pages (no tax period of their own) to a header
        # page's tax period via shared masked EIN suffix.
        ein_to_tax_period = {
            ein_suffix_of[pid]: tp for pid, tp in tax_period_of.items() if pid in ein_suffix_of
        }
        for _, page_idx in entries:
            if page_idx in tax_period_of:
                continue
            ein = ein_suffix_of.get(page_idx)
            if ein and ein in ein_to_tax_period:
                tax_period_of[page_idx] = ein_to_tax_period[ein]
                logger.info(
                    "INCOME_DOC total=%s: page_idx=%s linked to tax_period=%s via matching EIN suffix %s",
                    total, page_idx, tax_period_of[page_idx], ein,
                )

        # Last resort: the one manually-verified case with no in-text signal at all.
        for _, page_idx in entries:
            if page_idx not in tax_period_of and page_idx in INCOME_DOC_MANUAL_TAX_PERIOD:
                tax_period_of[page_idx] = INCOME_DOC_MANUAL_TAX_PERIOD[page_idx]
                logger.warning(
                    "INCOME_DOC total=%s: page_idx=%s has no in-text signal, "
                    "assigned tax_period=%s from manual verification",
                    total, page_idx, tax_period_of[page_idx],
                )

        clusters: dict[str, list[tuple[int, int]]] = {}
        unresolved: list[tuple[int, int]] = []
        for current, page_idx in entries:
            tax_period = tax_period_of.get(page_idx)
            if tax_period is None:
                unresolved.append((current, page_idx))
            else:
                clusters.setdefault(tax_period, []).append((current, page_idx))

        for tax_period, members in clusters.items():
            members.sort(key=lambda entry: entry[0])
            sub_docs.append({
                "label": "INCOME_DOC",
                "ordered_page_indices": [page_idx for _, page_idx in members],
                "total_pages_declared": total,
                "ordering_method": "page_number",
            })

        for current, page_idx in unresolved:
            logger.warning(
                "INCOME_DOC total=%s: page_idx=%s (current=%s) has no tax-period clue -- "
                "left as unassigned INCOME_DOC PAGE %s",
                total, page_idx, current, current,
            )
            sub_docs.append({
                "label": "INCOME_DOC",
                "ordered_page_indices": [page_idx],
                "total_pages_declared": None,
                "ordering_method": "unassigned",
            })

    for page_idx in unnumbered:
        sub_docs.append({
            "label": "INCOME_DOC",
            "ordered_page_indices": [page_idx],
            "total_pages_declared": None,
            "ordering_method": "unordered_single",
        })
    return sub_docs


def reconstruct_label(label: str, page_idxs: list[int], pages_text: dict[int, str]) -> list[dict]:
    if label == "INCOME_DOC":
        sub_docs = reconstruct_income_doc(page_idxs, pages_text)
    else:
        sub_docs = reconstruct_label_generic(label, page_idxs, pages_text)

    sub_docs.sort(key=lambda d: min(d["ordered_page_indices"]))
    for i, sub_doc in enumerate(sub_docs, start=1):
        sub_doc["sub_doc_id"] = f"{label}_{i}"
    return sub_docs


def write_reconstructed_docs(sub_docs: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "label", "sub_doc_id", "ordered_page_indices", "total_pages_declared", "ordering_method",
        ])
        writer.writeheader()
        for sub_doc in sub_docs:
            writer.writerow({
                "label": sub_doc["label"],
                "sub_doc_id": sub_doc["sub_doc_id"],
                "ordered_page_indices": ",".join(str(p) for p in sub_doc["ordered_page_indices"]),
                "total_pages_declared": sub_doc["total_pages_declared"] if sub_doc["total_pages_declared"] is not None else "",
                "ordering_method": sub_doc["ordering_method"],
            })


def process_package(package_name: str) -> list[dict]:
    rows = load_final_result(package_name)
    rows, corrected = apply_known_corrections(package_name, rows)
    if corrected:
        final_result_path = OUTPUT_DIR / f"final_result_{package_name}.csv"
        write_final_result(rows, final_result_path)
        logger.info("%s: applied known label correction(s), rewrote %s", package_name, final_result_path)

    pages_text = load_pages_text(package_name)
    label_groups = group_by_label(rows)

    all_sub_docs: list[dict] = []
    for label, page_idxs in label_groups.items():
        all_sub_docs.extend(reconstruct_label(label, page_idxs, pages_text))
    all_sub_docs.sort(key=lambda d: (d["label"], d["sub_doc_id"]))

    output_path = OUTPUT_DIR / f"reconstructed_docs_{package_name}.csv"
    write_reconstructed_docs(all_sub_docs, output_path)

    numbered_count = sum(1 for d in all_sub_docs if d["ordering_method"] == "page_number")
    single_count = sum(1 for d in all_sub_docs if d["ordering_method"] == "unordered_single")
    logger.info(
        "%s: %d pages -> %d sub-documents (%d page_number, %d unordered_single), wrote %s",
        package_name, len(rows), len(all_sub_docs), numbered_count, single_count, output_path,
    )
    return all_sub_docs


def main() -> None:
    for package_name in PACKAGES:
        process_package(package_name)


if __name__ == "__main__":
    main()
