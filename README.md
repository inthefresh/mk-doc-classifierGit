# MKlending

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # then fill in OPENAI_API_KEY=sk-...
```

Place the input PDFs under `data/` (gitignored, not part of the repo):
`01.990145627_shuffled.pdf`, `1003 - URLA_990145627.pdf`,
`Credit Report_990145627.pdf`, `INCOME - P & L_990145627.pdf`,
`Title Report_990145627.pdf`, `02.990367284_shuffled.pdf`.

Run in order (each script is independent and reads the previous phase's
`outputs/` files):

```bash
python src/build_ground_truth.py   # Phase 1 -> ground_truth_package01.csv
python src/extract.py              # Phase 2 -> {package}_pages.json
python src/rules.py                # Phase 3 -> rules_result_{package}.csv
python src/llm_classify.py         # Phase 4 -> final_result_{package}.csv (calls OpenAI)
python src/grouping.py             # Phase 5 -> reconstructed_docs_{package}.csv
python src/evaluate.py             # Phase 6 -> evaluation_report_package01.csv (console summary)
python src/summarize_package02.py  # Phase 7 -> summary_package02.md, package02_visualization.png
```

## Phase 5 — src/grouping.py (document reconstruction)

Adjacent-page merging (Phase 5 draft 1) doesn't work on this dataset: the shuffle
interleaves labels at single-page granularity, so consecutive same-label pages
essentially never occur (package_01: 0/38 adjacent page pairs share a label).
Instead, pages sharing a label are pooled together and ordered using in-text
page-number footers ("Page 4 of 11", bare "3 of 10", etc. — two regex patterns,
tried in order). Pages where no page-number could be extracted (cover sheets,
anonymized/image-only pages) are left as their own unordered single-page group.

Output: `outputs/reconstructed_docs_{package_name}.csv`
(label, sub_doc_id, ordered_page_indices, total_pages_declared, ordering_method).

**Verification (package_01, ground truth known):** reconstructed order matches
the original document page order exactly for all three numbered clusters —
URLA_1003 (11/11 pages), CREDIT_REPORT body (11/11 pages), TITLE_REPORT body
(8/8 pages). Unnumbered pages (cover sheets, disclosures, cover letters) were
also correctly separated out as standalone pages, matching the true page set.

### Limitation

페이지 번호(X of N) 기반 정렬로 문서 내 원래 순서를 복원했다. 단, 이 방식은 동일 라벨 내 문서
인스턴스가 유니크하다는 전제에 의존하며, 공동신청인/재조회 등으로 동일 양식이 중복 존재하는
경우 보조 식별자(Report ID, 신청인 이름, 조회일자 등) 기반 클러스터링이 추가로 필요하다.
이번 구현에서는 실제 데이터가 단일 인스턴스임을 확인하고 이 부분까지는 구현하지 않았다.

**Update after verification**: this assumption holds for package_01 (all labels are
single-instance), but **does not hold for package_02** — confirmed, not
hypothetical, in two of five labels:

- `TITLE_REPORT total=5`: 10 pages share `current` values 1-5 duplicated exactly
  twice each. These are two separate ALTA "Commitment for Title Insurance"
  instances (confirmed via page text — both are Virginia/First American
  boilerplate). **Still unresolved**: the one field that would identify each
  instance, Commitment Number, is blank/anonymized on every page of both
  instances — there is no surviving in-text signal to split them by. Left
  merged into one 10-page `TITLE_REPORT_1` sub_doc; `grouping.py` logs a
  warning when it detects the size mismatch (10 pages vs. declared 5) but does
  not attempt a fix.
- `INCOME_DOC total=2`: pages 11 and 26 both declare "1 of 2" (IRS Wage &
  Income Transcripts for tax years 2024 and 2025 respectively — two separate
  documents). **Fixed**: unlike the title reports, these pages carry two
  usable secondary identifiers — a `Tax Period Requested: MM-DD-YYYY` field on
  each transcript's own first page, and a masked EIN suffix (e.g. `XX-XXX4415`)
  that repeats on every page of the same instance, including continuation
  pages that lack the tax period field. `grouping.py` (`reconstruct_income_doc`)
  uses the tax period as the clustering key and links tax-period-less
  continuation pages back to the right instance via matching EIN suffix. This
  automatically resolved page_idx=30 (EIN suffix `4415` matches page 26 → tax
  year 2025). One page, page_idx=38, had neither field (97 characters of pure
  boilerplate) and was resolved only by manually inspecting the source PDF —
  confirmed to be page 2 of the 2024 transcript alongside page_idx=11. That
  page had originally been misclassified `OTHER` by the LLM in Phase 4 (too
  little text to classify) and is corrected to `INCOME_DOC` at the grouping
  stage instead of re-running rules.py/llm_classify.py, since the root cause
  was insufficient text, not a classifier error — `final_result_package02.csv`
  records this row's `source` as `grouping_correction` rather than `rule`/`llm`.

**Why one was fixable and the other wasn't**: both cases lacked page-adjacency
information and needed a secondary identifier, but INCOME_DOC's identifier
(EIN suffix) happened to survive anonymization on every page, while
TITLE_REPORT's identifier (Commitment Number) was blanked out everywhere. The
fix is only as good as the weakest surviving field in the anonymized sample —
this is a property of the data, not of the two approaches.

## Phase 8 — reproducibility check

Verified the "How to run" steps above actually work from scratch: created a
fresh venv **outside** the project directory, `pip install -r requirements.txt`
only, then ran Phase 1-7 in order against the existing `data/` and diffed the
result against the previously committed `outputs/`.

**Result: the code and environment are fully reproducible. `requirements.txt`
was sufficient, no path/env-var/missing-directory issues came up.** One real
gap was found and fixed:

- **Non-determinism in Phase 4 (`llm_classify.py`)**: the two API calls didn't
  pin `temperature`, so a re-run flipped one label (`page_idx=35`,
  `OTHER` -> `INCOME_DOC`, package_01's only INCOME_DOC page — a genuinely
  ambiguous page, see Phase 6) and changed the `confidence`/`reasoning` text
  on another (`page_idx=7`), which cascaded into `evaluate.py`'s accuracy
  (94.9% vs. 97.4% depending on the run) and `grouping.py`'s output for that
  page. **Fixed**: added `temperature=0` to both `classify_text_page` and
  `classify_image_page`. This doesn't give OpenAI-side bit-for-bit guarantees,
  but removes the main source of run-to-run drift.
- Every deterministic stage (Phases 1, 2, 3, and the non-LLM parts of 5) was
  byte-identical across the fresh-venv run and the original: same
  `ground_truth_package01.csv`, same `{package}_pages.json`, same
  `rules_result_{package}.csv`.
- `requirements.txt` had an unused `pandas` pin (added early on, never
  actually imported by any script) — removed.
- `.env` / `.env.example` were both already present and correctly set up from
  earlier phases (`.env` gitignored with the real key, `.env.example` tracked
  as an empty template) — nothing to fix there this time.

The `outputs/` committed in this repo are from the original runs (pre-Phase-8,
`temperature` unset), kept as-is since they're what the rest of this README
and the misclassification analysis in Phase 6 reference. A from-scratch run
with the `temperature=0` fix in place should reproduce them closely, modulo
any remaining OpenAI-side non-determinism.
