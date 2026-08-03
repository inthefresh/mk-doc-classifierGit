"""Phase 4: LLM fallback classification for UNCERTAIN pages from Phase 3.

Input: outputs/rules_result_{package_name}.csv, outputs/{package_name}_pages.json,
and the original shuffled PDF (for rendering low-text pages to images).

- reason=low_text pages -> rendered to a PNG image and classified with a vision model.
- other UNCERTAIN pages -> classified from extracted text.

Merges rule-confirmed pages with LLM-classified pages into
outputs/final_result_{package_name}.csv (page_idx, label, source).
"""
from __future__ import annotations

import base64
import csv
import json
import logging
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

MODEL = "gpt-4o-mini"
RENDER_DPI = 300

PACKAGE_PDFS = {
    "package01": DATA_DIR / "01.990145627_shuffled.pdf",
    "package02": DATA_DIR / "02.990367284_shuffled.pdf",
}

Label = Literal["URLA_1003", "INCOME_DOC", "CREDIT_REPORT", "TITLE_REPORT", "OTHER"]


class PageClassification(BaseModel):
    label: Label
    confidence: Literal["high", "medium", "low"]
    reasoning: str


SYSTEM_PROMPT = """You are classifying a single page from a shuffled U.S. mortgage loan package PDF into exactly one of five categories.

- URLA_1003: The Uniform Residential Loan Application (Form 1003). Application form fields: borrower info, employment, assets/liabilities, loan terms.
- INCOME_DOC: Income/employment verification - paystubs, W-2, 1040 tax returns, 1099s, Verification of Employment (VOE), profit & loss (P&L) statements.
- CREDIT_REPORT: A credit bureau report - tradelines, credit scores, inquiries, public records, from bureaus like TransUnion/Experian/Equifax or resellers like Xactus.
- TITLE_REPORT: A title/escrow document. This includes BOTH the California-style "Preliminary Report" (CLTA) AND the "Commitment for Title Insurance" (ALTA) format used in other states. Look for title insurance, escrow numbers, legal property description, schedule of exceptions, underwriters like Fidelity National / First American / Old Republic.
- OTHER: Only when the page clearly does not belong to any of the four categories above (e.g. a blank page, a generic disclosure/signature page not tied to a specific document type, cover sheet, fax cover).

Respond with the single best label, a confidence level, and a one-sentence reasoning.

Example 1:
Page text: "SCHEDULE B - EXCEPTIONS\n1. Taxes for the fiscal year 2025-2026...\n2. Easement(s) for the purpose(s) shown below...\nSAID MATTERS AFFECT THE LAND DESCRIBED IN SCHEDULE A"
-> label=TITLE_REPORT, confidence=high, reasoning="Schedule B exceptions list is standard preliminary/commitment title report content."

Example 2:
Page text: "This page intentionally left blank."
-> label=OTHER, confidence=medium, reasoning="No content ties this page to any of the four specific document types."
"""


def get_client() -> OpenAI:
    return OpenAI()


def render_page_image_b64(pdf_path: Path, page_idx: int, dpi: int = RENDER_DPI) -> str:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_idx]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png_bytes = pix.tobytes("png")
    finally:
        doc.close()
    return base64.b64encode(png_bytes).decode("utf-8")


def classify_text_page(client: OpenAI, text: str) -> PageClassification:
    completion = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Page text:\n{text}"},
        ],
        response_format=PageClassification,
    )
    return completion.choices[0].message.parsed


def classify_image_page(client: OpenAI, image_b64: str) -> PageClassification:
    completion = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Classify this scanned page image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            },
        ],
        response_format=PageClassification,
    )
    return completion.choices[0].message.parsed


def load_pages_json(package_name: str) -> dict[int, dict]:
    path = OUTPUT_DIR / f"{package_name}_pages.json"
    with path.open(encoding="utf-8") as f:
        return {p["page_idx"]: p for p in json.load(f)}


def load_rules_result(package_name: str) -> list[dict]:
    path = OUTPUT_DIR / f"rules_result_{package_name}.csv"
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def process_package(client: OpenAI, package_name: str) -> None:
    rules_rows = load_rules_result(package_name)
    pages = load_pages_json(package_name)
    pdf_path = PACKAGE_PDFS[package_name]

    uncertain_rows = [r for r in rules_rows if r["status"] == "UNCERTAIN"]
    logger.info("%s: %d UNCERTAIN pages to classify via LLM", package_name, len(uncertain_rows))

    llm_results: list[dict] = []
    for row in uncertain_rows:
        page_idx = int(row["page_idx"])
        if row["reason"] == "low_text":
            image_b64 = render_page_image_b64(pdf_path, page_idx)
            result = classify_image_page(client, image_b64)
            method = "vision"
        else:
            text = pages[page_idx]["text"]
            result = classify_text_page(client, text)
            method = "text"

        logger.info(
            "%s page_idx=%d [%s]: %s (confidence=%s)",
            package_name, page_idx, method, result.label, result.confidence,
        )
        llm_results.append({
            "page_idx": page_idx,
            "label": result.label,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        })

    debug_path = OUTPUT_DIR / f"llm_result_{package_name}.csv"
    with debug_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page_idx", "label", "confidence", "reasoning"])
        writer.writeheader()
        writer.writerows(llm_results)
    logger.info("%s: wrote %d LLM results to %s", package_name, len(llm_results), debug_path)

    llm_by_idx = {r["page_idx"]: r for r in llm_results}
    final_rows = []
    for row in rules_rows:
        page_idx = int(row["page_idx"])
        if row["status"] == "CONFIRMED":
            final_rows.append({"page_idx": page_idx, "label": row["label"], "source": "rule"})
        else:
            final_rows.append({"page_idx": page_idx, "label": llm_by_idx[page_idx]["label"], "source": "llm"})
    final_rows.sort(key=lambda r: r["page_idx"])

    final_path = OUTPUT_DIR / f"final_result_{package_name}.csv"
    with final_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page_idx", "label", "source"])
        writer.writeheader()
        writer.writerows(final_rows)
    logger.info("%s: wrote %d rows to %s", package_name, len(final_rows), final_path)


def main() -> None:
    client = get_client()
    for package_name in PACKAGE_PDFS:
        process_package(client, package_name)


if __name__ == "__main__":
    main()
