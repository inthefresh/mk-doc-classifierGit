# package_02 submission summary

## Label distribution

| label | pages | sub-documents |
|---|---|---|
| URLA_1003 | 10 | 1 |
| INCOME_DOC | 5 | 3 |
| CREDIT_REPORT | 15 | 7 |
| TITLE_REPORT | 14 | 5 |
| OTHER | 0 | 0 |
| **total** | **44** | **16** |

## Classification source

| source | pages | share |
|---|---|---|
| grouping_correction | 1 | 2.3% |
| llm | 19 | 43.2% |
| rule | 24 | 54.5% |

## Sub-documents

| label | sub_doc_id | first_page_idx | last_page_idx | page_count | total_pages_declared | ordering_method |
|---|---|---|---|---|---|---|
| CREDIT_REPORT | CREDIT_REPORT_1 | 1 | 1 | 1 | - | unordered_single |
| CREDIT_REPORT | CREDIT_REPORT_2 | 3 | 3 | 1 | - | unordered_single |
| CREDIT_REPORT | CREDIT_REPORT_3 | 7 | 9 | 9 | 9 | page_number |
| CREDIT_REPORT | CREDIT_REPORT_4 | 13 | 13 | 1 | - | unordered_single |
| CREDIT_REPORT | CREDIT_REPORT_5 | 18 | 18 | 1 | - | unordered_single |
| CREDIT_REPORT | CREDIT_REPORT_6 | 23 | 23 | 1 | - | unordered_single |
| CREDIT_REPORT | CREDIT_REPORT_7 | 31 | 31 | 1 | - | unordered_single |
| INCOME_DOC | INCOME_DOC_1 | 11 | 38 | 2 | 2 | page_number |
| INCOME_DOC | INCOME_DOC_2 | 26 | 30 | 2 | 2 | page_number |
| INCOME_DOC | INCOME_DOC_3 | 35 | 35 | 1 | - | unordered_single |
| TITLE_REPORT | TITLE_REPORT_1 | 2 | 6 | 10 | 5 | page_number |
| TITLE_REPORT | TITLE_REPORT_2 | 10 | 10 | 1 | - | unordered_single |
| TITLE_REPORT | TITLE_REPORT_3 | 25 | 25 | 1 | - | unordered_single |
| TITLE_REPORT | TITLE_REPORT_4 | 29 | 29 | 1 | - | unordered_single |
| TITLE_REPORT | TITLE_REPORT_5 | 39 | 39 | 1 | - | unordered_single |
| URLA_1003 | URLA_1003_1 | 19 | 36 | 10 | 10 | page_number |

## Known unresolved cases

- **TITLE_REPORT_1**: 10 pages collected but the form declares "of 5" -- likely 2 separate document instances merged into one sub_doc (same total_pages_declared, no distinguishing ID left in the anonymized text). Pages: 2,16,0,41,8,32,14,21,4,6
