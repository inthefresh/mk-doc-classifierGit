# MKlending

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
single-instance), but **does not hold for package_02**. `grouping.py` logs a
warning when it detects this:

- `TITLE_REPORT total=5`: 10 pages share `current` values 1-5 duplicated exactly
  twice each. These are two separate ALTA "Commitment for Title Insurance"
  instances (confirmed via page text — both are Virginia/First American
  boilerplate; the actual Commitment Number field is blank/anonymized in this
  sample, so there's no in-text ID left to split them by), merged into one
  10-page `TITLE_REPORT_1` sub_doc instead of two 5-page ones.
- `INCOME_DOC total=2`: pages 11 and 26 both declare "1 of 2" (IRS Wage & Income
  Transcripts for tax years 2024 and 2025 respectively — two separate
  documents), merged with page 30 into one bogus 3-page `INCOME_DOC_1` sub_doc.

Both are flagged by the code's warning log but not split apart, per scope above.
