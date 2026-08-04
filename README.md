# MKlending — 대출서류 페이지 분류기 (mk-doc-classifier)

대출 패키지 PDF가 페이지 순서 없이 섞여 있는 상태에서, 각 페이지를
`URLA_1003` / `INCOME_DOC` / `CREDIT_REPORT` / `TITLE_REPORT` / `OTHER`로
분류하고, 같은 문서에 속하는 페이지를 원래 순서로 재구성하는 파이프라인.

---

## 1. 실행 방법

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

이 순서와 커맨드는 Phase 8에서 프로젝트 디렉토리 밖의 새 venv +
`requirements.txt`만으로 실제 재현되는지 직접 검증했다 (자세한 내용은
5절 및 아래 "재현성" 항목 참고).

---

## 2. 사용한 기술 스택과 선택 이유

**Python 단일 언어.** PDF 텍스트/이미지 추출과 LLM API 호출 모두 Python
생태계 라이브러리가 가장 성숙해 있고, 별도 배포 요구사항이 없는 배치성
분류 파이프라인이라 다른 언어를 끌어올 이유가 없었다.

**텍스트 추출: pypdf (pdfplumber 아님).** 처음엔 pdfplumber로 시작했으나,
셔플본의 특정 CREDIT_REPORT 페이지(page_idx 6, 8, 12, 14, 22, 28, 32)에서
**줄 내부 문자가 역순으로 추출되는 버그**를 직접 재현·확인했다
(예: `"80091\nAP\n,llamoorB"`를 줄 단위로 뒤집으면 `"19008\nPA\nBroomall,"`
로 정상 판독됨). 같은 페이지를 pypdf로 추출하면 문제없이 정상 순서로
나온다는 것도 확인했다. 원인은 셔플 과정에서의 재인코딩으로 추정되나
완전히 규명하지는 못했다. 이 데이터셋 특유의 버그를 감지·보정하는 별도
로직을 만드는 대신, 애초에 표/레이아웃 인식 기능이 필요 없는 순수 텍스트
분류 작업이라는 점에 맞춰 **pypdf 단일 엔진으로 전환**했다. 전환 직후
재검증에서 package_01의 CONFIRMED 비율이 17/39(43.6%)에서 37/39(94.9%)로
뛰었고, 문제였던 7페이지 전부 정상 텍스트로 판독됨을 확인했다.

**분류 구조: 규칙기반(정규식 키워드) 1차 필터 + LLM 2차 분류의 하이브리드.**

- `URLA_1003`: 키워드 1개(`"uniform residential loan application"`)만
  걸려도 확정. 이 문구는 양식 자체의 고정 타이틀이라 오탐 위험이 낮다고
  판단했고, 실제로 11/11 커버리지·타 문서 오탐 0건을 직접 검증했다.
- `CREDIT_REPORT` / `TITLE_REPORT`: 서로 다른 키워드가 2개 이상 매칭되어야
  확정. 임계값을 1로 하면 URLA 본문 안에 우연히 등장하는 `"credit score"`,
  `"escrow"` 같은 단어 하나만으로 오탐이 발생하는 것을 직접 확인해서
  2로 설정했다. (CREDIT_REPORT 키워드셋은 최초 커버리지 검증이 "키워드
  아무거나 1개"만 기준으로 이뤄져 실제 threshold=2 로직과 불일치했던 걸
  나중에 발견해 키워드 4개를 보강했다 — 3절 Phase 3 참고.)
- `INCOME_DOC`: 규칙 없음. package_01에 P&L 샘플이 1건뿐이라 W-2/1040/
  VOE 같은 일반화된 키워드를 검증 없이 추가하는 건 오탐·silent
  misclassification 리스크를 검증 불가능한 채로 안고 가는 것이라 판단해,
  의도적으로 LLM 전담으로 넘겼다.
- 저텍스트(50자 미만) 페이지는 규칙 매칭 자체를 시도하지 않고 바로
  `UNCERTAIN`(`reason=low_text`)으로 분류해 다음 단계(LLM vision)로 넘긴다.

**LLM: OpenAI `gpt-4o-mini` 단일 모델.** 텍스트/이미지 입력을 모델
하나로 통일하기로 한 뒤(프롬프트·스키마 이중 관리 방지), 어떤 모델로
통일할지는 `gpt-4o-mini`와 `gpt-4.1-mini` 둘 다 vision을 지원한다는
점을 확인한 후, 가격(4o-mini $0.15/$0.60 vs 4.1-mini $0.40/$1.60)과
structured output(JSON schema strict) 지원 확실성(4o-mini는 공식
문서로 명확히 확인됨, 4.1-mini는 커뮤니티에서 지원 여부에 대한 상반된
리포트가 있어 불확실)을 근거로 `gpt-4o-mini`를 선택했다. API 호출은
`temperature=0`으로 고정했는데, 이는 애초 설계가 아니라 **Phase 8
재현성 검증 중 발견한 문제에 대한 사후 수정**이다(5절 참고).

**프롬프트에 CLTA/ALTA 둘 다 TITLE_REPORT로 매핑하도록 명시.**
package_01은 캘리포니아식 "CLTA Preliminary Report" 양식, package_02는
버지니아식 "ALTA Commitment for Title Insurance" 양식을 쓴다는 걸
데이터에서 직접 확인했다. 두 양식은 어휘가 상당히 다르기 때문에,
규칙기반 키워드셋(CLTA 기준으로만 검증됨)이 놓치는 ALTA 페이지를 LLM이
프롬프트 지시만으로 잡아낼 수 있도록 설계했다. 이 부분은 4절 정확도
측정에서 실제로 검증된다.

**Claude Code(PyCharm 프로젝트)는 개발 보조 도구로만 사용했다.** 실제
분류 로직은 전부 OpenAI API 호출로 구현되어 있으며, 개발에 쓰인 도구와
런타임에 동작하는 컴포넌트는 분리되어 있다.

---

## 3. 문제 해결 접근 방식 및 처리 흐름

파이프라인은 Phase 1~8로 나뉘며, 각 Phase는 `src/`의 독립 스크립트 하나에
대응하고 이전 Phase의 `outputs/` 산출물을 입력으로 받는다.

### Phase 1 — `build_ground_truth.py`
package_01 셔플본(39p)의 각 페이지 텍스트를 원본 4개 문서
(URLA 11p / Credit Report 18p / Income P&L 1p / Title Report 9p)의 페이지
텍스트와 대조한 결과, **exact string match로 39/39 전부 100% 일치**함을
확인했다. 이 성질을 이용해 정답 라벨(`ground_truth_package01.csv`)을
자동 생성했다 — 개발·검증 전용이며, 정답이 없는 package_02에는 적용하지
않는다.

### Phase 2 — `extract.py`
페이지별 텍스트, `char_count`, `is_low_text`(50자 미만) 플래그를 추출한다.
텍스트에 개행이 포함돼도 안전하게 다루기 위해 CSV 대신 **JSON**으로
저장한다(parquet은 pyarrow 등 추가 의존성이 필요해 제외). 추출 엔진을
pdfplumber에서 pypdf로 전환한 배경은 2절 참고. package_02에서는 저텍스트
페이지 3개(page_idx 10, 25, 39, char_count 0에 가까움)를 발견했는데,
이는 이미지/스캔 페이지로 추정되며 Phase 4에서 vision 입력으로 별도
처리된다.

### Phase 3 — `rules.py`
키워드 임계값 기반 1차 필터로 각 페이지를 `CONFIRMED`/`UNCERTAIN`으로
나눈다. 라벨별 임계값과 그 근거는 2절에 정리했다. 라벨 2개 이상이
동시에 확정 조건을 만족하면 충돌(`conflict`)로 판단해 `UNCERTAIN`으로
강등하고 로그를 남기도록 했으나, 실제 실행에서는 두 패키지 모두
conflict 0건이었다. pypdf 전환과 키워드 보강을 마친 뒤 최종 결과는
package_01 `CONFIRMED` 37/39, `UNCERTAIN` 2/39.

### Phase 4 — `llm_classify.py`
`UNCERTAIN` 페이지만 LLM으로 넘긴다. Structured output(5라벨 enum:
`URLA_1003` / `INCOME_DOC` / `CREDIT_REPORT` / `TITLE_REPORT` / `OTHER`,
`confidence`, 짧은 `reasoning`)으로 응답을 받는다.
- `reason=low_text` 페이지: PyMuPDF(fitz)로 300dpi 이미지 렌더링 →
  base64 인코딩 → vision 입력.
- 그 외 `UNCERTAIN` 페이지: 추출된 텍스트를 그대로 입력.

규칙기반 `CONFIRMED` 행(`source=rule`)과 LLM 처리 결과(`source=llm`)를
합쳐 `outputs/final_result_{package}.csv`(`page_idx, label, source`)를
만든다.

### Phase 5 — `grouping.py` (문서 재구성)
**첫 시도(인접 페이지 병합)는 이 데이터셋에서 무의미했다.** 셔플이
문서 블록 단위가 아니라 **페이지 단위로 완전히 흩어지는 방식**이라는
걸 확인했다 — package_01은 인접한 두 페이지가 같은 라벨을 갖는 경우가
**0/38쌍**이었다. 이 때문에 인접 병합 로직은 항상 1페이지짜리 그룹으로만
수렴한다(39/39, 44/44 전부 singleton). 버그가 아니라 셔플 방식 자체의
구조적 특성임을 원본 ground truth로 직접 확인했다.

이를 바탕으로 접근을 바꿔서, **같은 라벨의 페이지를 전부 모은 뒤
텍스트 안의 페이지 번호 푸터**("Page 4 of 11", bare "3 of 10" 등, 정규식
두 패턴을 순서대로 시도)로 원래 순서를 복원하는 방식으로 재설계했다.
페이지 번호가 없는 페이지(표지, 익명화·이미지 페이지)는 무리하게
순서를 유추하지 않고 단독 그룹으로 남긴다.

**검증(package_01, 정답 있음):** 원본 4개 PDF를 직접 읽어 대조한 결과,
번호 기반으로 복원한 순서가 **URLA_1003 11/11, CREDIT_REPORT 본문 11/11,
TITLE_REPORT 본문 8/8 전부 원본과 정확히 일치**했다. 번호 없는 페이지들도
정확히 맞는 페이지 집합으로 분리됐다.

**package_02에서 실제로 터진 문제 — 동일 라벨 내 중복 인스턴스.**
페이지 번호 기반 정렬은 "같은 `total_pages_declared` 값을 가진 페이지는
모두 한 문서"라는 전제에 의존하는데, 이 전제가 package_02의 두 라벨에서
실제로 깨졌다:

- **`TITLE_REPORT total=5`**: 10페이지가 `current` 값 1~5를 정확히 두
  번씩 중복해서 가짐 — 실제로는 별도의 ALTA "Commitment for Title
  Insurance" 인스턴스 2건(버지니아, First American 서식)이었다.
  **미해결로 남김**: 두 인스턴스를 구분할 유일한 필드인 Commitment
  Number가 양쪽 다 익명화되어 비어 있어, 텍스트만으로는 구분할 수단이
  없었다. 10페이지짜리 `TITLE_REPORT_1`로 병합된 채 남겨두고,
  `grouping.py`가 크기 불일치(10 vs 선언된 5)를 감지해 경고 로그만
  남기도록 했다.
- **`INCOME_DOC total=2`**: page_idx 11과 26이 둘 다 "1 of 2"를 선언 —
  실제로는 2024년/2025년 IRS Wage and Income Transcript라는 별개
  문서였고, page_idx 30까지 한 그룹으로 잘못 병합돼 있었다. **해결함**:
  이 문서들은 각 인스턴스 첫 페이지에만 있는 `Tax Period Requested:
  MM-DD-YYYY` 필드와, 연속 페이지에도 반복되는 마스킹된 EIN 접미사
  (예: `XX-XXX4415`) 두 가지 보조 식별자를 갖고 있었다. `Tax Period`를
  1차 클러스터링 키로 쓰고, 이 필드가 없는 연속 페이지는 EIN 접미사
  일치로 원래 인스턴스에 연결하도록 구현했다 — page_idx=30이 EIN
  접미사 `4415`로 page_idx=26(2025년)과 자동 매칭됐다. page_idx=38만은
  텍스트가 97자(boilerplate뿐)라 두 신호 모두 없었는데, 원본 PDF를
  직접 확인해 2024년 트랜스크립트의 2쪽(page_idx=11과 같은 문서)임을
  수동으로 확정했다. 이 페이지는 애초에 Phase 4에서 텍스트 부족으로
  LLM이 `OTHER`로 오분류했던 페이지인데, 원인이 분류 모델의 오류가
  아니라 애초에 텍스트 단서 부족이었으므로 rules.py/llm_classify.py를
  재실행하지 않고 **그룹핑 단계에서 `INCOME_DOC`으로 재라벨링**했다
  (`final_result_package02.csv`에 `source=grouping_correction`으로 기록).

**왜 하나는 고치고 하나는 한계로 남겼는가**: 두 케이스 모두 페이지
인접성 정보가 없어 보조 식별자가 필요했다는 점은 같지만, INCOME_DOC의
식별자(EIN 접미사)는 익명화 이후에도 모든 페이지에 살아남았고,
TITLE_REPORT의 식별자(Commitment Number)는 전부 지워져 있었다. 즉 이
차이는 두 접근법의 우열이 아니라 **익명화된 샘플에 어떤 필드가
살아남았는지에 따른 데이터의 속성**이다.

### Phase 6 — `evaluate.py`
package_01(정답 있는 유일한 패키지)의 `final_result`를 `ground_truth`와
페이지 단위로 대조해 정확도를 측정한다. 자세한 수치는 4절.

### Phase 7 — `summarize_package02.py`
정답이 없는 package_02의 결과를 제출 가능한 형태로 정리한다:
라벨별 페이지 수·하위문서 개수, `source`(rule/llm/grouping_correction)
비율, 하위문서별 시작/끝 페이지와 순서 복원 방식(`page_number`/
`unordered_single`), 알려진 미해결 케이스(TITLE_REPORT 중복 병합) 목록을
`outputs/summary_package02.md`로 만들고, 44페이지 전체를 셔플된 순서
그대로 라벨별로 색칠한 타임라인(`outputs/package02_visualization.png`)을
그려 앞서 설명한 "라벨 연속 방지형 인터리빙" 셔플 패턴을 한눈에
보여주도록 했다.

### Phase 8 — 재현성 검증
README의 "1. 실행 방법"이 실제로 처음부터 재현되는지 확인했다. 프로젝트
디렉토리 밖에 새 venv를 만들고 `requirements.txt`만으로 설치한 뒤
Phase 1~7을 순서대로 실행하고 결과를 기존 산출물과 diff했다.

- **결정론적 구간(Phase 1~3, Phase 5의 rule 기반 로직)은 전부
  byte-identical**하게 재현됐다 — `ground_truth_package01.csv`,
  `{package}_pages.json`, `rules_result_{package}.csv` 모두 동일.
- **`requirements.txt`에 안 쓰는 `pandas` 의존성**을 발견해 제거했다
  (Phase 1 초반에 넣었으나 이후 어떤 스크립트도 import하지 않음).
- **Phase 4가 비결정적이었다**: `temperature`를 지정하지 않은 채
  재실행하니 page_idx=35(package_01의 유일한 INCOME_DOC 페이지) 라벨이
  `OTHER`→`INCOME_DOC`으로 실제로 바뀌었고, 이 때문에 `evaluate.py`
  정확도가 94.9%→97.4%로, `grouping.py`의 하위문서 배정도 그만큼
  달라졌다. `classify_text_page`/`classify_image_page` 양쪽에
  `temperature=0`을 추가해 수정했다(OpenAI 쪽 완전한 비트 단위 재현은
  보장되지 않지만 주요 변동 요인은 제거됨).
- 이 저장소에 커밋된 `outputs/`는 `temperature` 고정 이전의 원본 실행
  결과이며, 이 README의 4절 정확도 수치도 이 버전 기준이다.

---

## 4. package_01 기준 자체 측정 정확도

측정 방법: Phase 1에서 만든 `ground_truth_package01.csv`와
`final_result_package01.csv`를 페이지 단위로 직접 비교(`evaluate.py`).

**전체 정확도: 37/39 (94.9%)**

**source(rule/llm)별 분리 집계**

| source | 정확도 |
|---|---|
| rule | **37/37 (100.0%)** |
| llm | 0/2 (0.0%) |

**Confusion matrix** (행=정답, 열=예측, `OTHER` 포함 5x5)

```
                     URLA_1003     INCOME_DOC  CREDIT_REPORT   TITLE_REPORT          OTHER
URLA_1003                   11              0              0              0              0
INCOME_DOC                   0              0              0              0              1
CREDIT_REPORT                0              0             18              0              0
TITLE_REPORT                 0              0              0              8              1
OTHER                        0              0              0              0              0
```

`OTHER` 행/열이 전부 0인 것은 정상이다 — ground truth 자체에 `OTHER`
라벨이 없다(package_01은 4개 원본 문서로만 구성).

**오분류 2건, 둘 다 정답이 `OTHER`로 잘못 예측된 케이스:**

- **page_idx=7 (TITLE_REPORT → OTHER)**: 텍스트가
  `"[ Plat map removed in anonymized sample ]"` 뿐이다. 익명화 샘플에서
  실제 지적도(plat map) 내용이 통째로 제거된 placeholder라, 어떤
  모델도 이 텍스트만으로는 TITLE_REPORT임을 알 수 없는 원천적으로
  판단 불가능한 케이스다.
- **page_idx=35 (INCOME_DOC → OTHER)**: package_01의 유일한 INCOME_DOC
  샘플인데, 텍스트가 이름·금액 나열뿐이고 W-2·paystub·P&L 같은 명시적
  문서 단서가 전혀 없어 LLM이 애매하게 OTHER로 판단했다. INCOME_DOC
  규칙을 애초에 만들지 않은 이유(검증 샘플 1건뿐)와 같은 맥락의
  어려움이다.

**결론**: 규칙기반이 `CONFIRMED`로 확정한 페이지는 **오분류 0건**이었고,
오분류는 전부 "규칙으로도 LLM으로도 텍스트 자체가 부족해 원천적으로
어려운" 데이터의 한계에서만 발생했다. 이는 규칙기반(높은 정밀도) +
LLM(낮은 재현율 구간 커버) 하이브리드 설계가 의도대로 동작했음을
보여주는 핵심 근거다.

---

## 5. 현재 구현의 한계 및 개선 방향

1. **INCOME_DOC 규칙기반 부재.** 검증 샘플이 package_01의 P&L 1건뿐이라
   일반화된 키워드를 검증 없이 만드는 리스크를 감수하지 않기로
   의도적으로 결정했고, 전량 LLM에 의존한다. 실사용 데이터가 쌓이면
   W-2/1040/1099/VOE 등 문서 유형별 키워드셋을 검증 후 추가할 수 있다.
2. **TITLE_REPORT 양식이 주(state)별로 다르다.** package_01(CLTA,
   캘리포니아)과 package_02(ALTA, 버지니아)의 어휘가 다르다는 걸
   확인했고, 규칙기반 키워드는 CLTA만으로 검증되어 있다. ALTA는
   프롬프트에 명시적으로 지시해 LLM이 대신 처리하도록 설계했으며,
   package_02에서 TITLE_REPORT 14/14 전부가 LLM 단계에서 (규칙기반은
   0건) 정상 처리됨을 실제로 확인했다. 주(state)가 늘어나면 각 양식별
   어휘 확인과 프롬프트/키워드 보강이 반복적으로 필요하다.
3. **동일 라벨 내 중복 문서 인스턴스.** 페이지번호 기반 재정렬은
   "같은 라벨·같은 선언 총페이지수는 한 인스턴스"라는 전제에 의존하는데,
   package_02에서 실제로 2건 충돌이 발생했다(TITLE_REPORT는 Commitment
   Number 익명화로 미해결, INCOME_DOC은 Tax Period+EIN 접미사로 해결).
   실제 운영 규모의 데이터에서는 공동신청인·재조회 시나리오가 흔할 수
   있으므로, Report ID·신청인 이름·조회일자 등 보조 식별자 기반
   클러스터링을 더 견고하게 갖출 필요가 있다.
4. **LLM 비결정성.** `temperature=0`으로 완화했으나 OpenAI 쪽에서
   완전한 재현을 보장하지는 않는다(Phase 8에서 실측 확인). 완전한
   재현이 요구되는 환경이라면 응답 캐싱이나 다수결(self-consistency)
   같은 보완이 필요하다.
5. **OTHER 카테고리 검증 부족.** package_02에서 1건 트리거됐으나, 그마저
   그룹핑 단계 검증 과정에서 실제로는 INCOME_DOC이었음이 밝혀져
   재분류됐다. 즉 이 파이프라인에서 OTHER가 "진짜로 필요한" 케이스를
   충분히 검증하지 못한 상태이며, 프롬프트의 OTHER 기준(4개 카테고리
   어디에도 안 맞을 때)이 실전에서 잘 작동하는지는 더 다양한 표본이
   필요하다.
6. **pdfplumber 역순 추출 버그.** 근본 원인(셔플 과정의 재인코딩으로
   추정)을 완전히 규명하지 못한 채 pypdf 전환으로 우회했다. 다른 PDF
   소스나 다른 셔플 도구에서 유사한 문제가 재발할 가능성을 배제할 수
   없다.

### 실무 확장성 (참고, 구현 아님)

- **문서 유형 추가 시**: 현재는 `rules.py`의 키워드셋, LLM structured
  output의 JSON schema enum, 프롬프트의 라벨 설명까지 총 3곳을 각각
  수정해야 한다(결합도가 높음). 라벨 정의를 단일 config(YAML/JSON)로
  분리하면 새 문서 유형 추가 시 수정 지점을 1곳으로 줄일 수 있다.
- **대량 처리**: 현재는 페이지 단위로 순차적으로 OpenAI API를 호출한다.
  수백~수천 페이지 규모로 커지면 OpenAI Batch API(비용 할인) 또는
  비동기 병렬 호출 + rate limit 핸들링으로 전환이 필요하다.
- **데이터 추출 단계와의 연동**: `reconstructed_docs_{package}.csv`의
  `{label, sub_doc_id, ordered_page_indices}` 구조를, 다음 단계(소득·
  신용 정보 등 필드 추출)의 입력 스키마로 그대로 활용할 것을 제안한다.
- **다중 인스턴스 대응**: 위 한계 3번과 연결되며, 실제 운영 규모에서는
  Report ID·신청인 이름·조회일자 등 보조 식별자 기반 클러스터링을
  일반화된 형태로 추가해야 한다.
