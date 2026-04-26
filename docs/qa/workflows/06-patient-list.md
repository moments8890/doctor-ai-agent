# Workflow 06 — Patient list + search

Ship gate for the **患者** tab — patient browsing, text search, and
natural-language search. NL search is a differentiating feature ("show
me elderly male hypertension patients"), so the gate doubles as a
regression guard for the NL parser.

**Area:** `src/pages/doctor/PatientsPage.jsx`,
`/api/doctor/patients` (list), `/api/doctor/patients/search` (NL)
**Spec:** `frontend/web/tests/e2e/06-patient-list.spec.ts`
**Estimated runtime:** ~4 min manual / ~30 s automated

---

## Scope

**In scope**

- Empty state (zero patients) — prompts to add first patient.
- Populated list — stats header "最近 · N位患者", card layout.
- Patient card content: name, gender·age·record count line, relative date.
- Text search — substring match on name, live filter.
- "+ 新建患者「<query>」" autocomplete row when query doesn't match.
- Clear search (X button) restores full list.
- NL search — male / female / age+condition / surname queries.
- No-match empty state.
- Tapping a patient navigates to patient detail ([07](07-patient-detail.md)).
- Tapping "+ 新建患者「X」" creates a new patient with that name.

**Out of scope**

- Patient detail view — [07](07-patient-detail.md).
- Bulk patient operations.
- Patient delete / archive.
- Patient messaging directly from the list.

---

## Pre-flight

Seed 3-5 patients via `seed.registerPatient` (called multiple times) with
distinct names, genders, and birth years. At least one patient needs a
hypertension-related record via `seed.completePatientIntake` so NL
queries can find condition-based matches.

---

## Steps

### 1. Empty state

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Fresh doctor (no patients) → tap 患者 tab | Empty state visible with prompt to add first patient; no console errors |

### 2. Populated list

| # | Action | Verify |
|---|--------|--------|
| 2.1 | With ≥3 patients seeded, tap 患者 tab | Header "最近 · N位患者" (count matches seed); search bar with placeholder "搜索患者 (共N人)，或用自然语言描述" |
| 2.2 | Each patient card | Name, then "男/女 · N岁 · M份病历" line; relative last activity on right (e.g. "今天", "昨天", "3天前") |
| 2.3 | Activity format is relative, not ISO | No `2026-04-11T12:34:56Z` strings visible |
| 2.4 | Tap any card | Navigates to `/doctor/patients/<id>`; bottom nav hidden |

### 3. Text search

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Type `张` (or any seeded surname) | List filters to matching patients in real time; non-matches hidden |
| 3.2 | X clear button appears when search non-empty | Tap X → search cleared → full list restored |
| 3.3 | Type `张三` (non-existent) | Autocomplete row "+ 新建患者「张三」" shown at top of list |
| 3.4 | Tap the "+ 新建患者" row | Navigates to new-patient creation flow with name pre-filled (or confirm dialog) |

### 4. Natural-language search

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Type `最近来诊的男性` | Network request to `/api/doctor/patients/search`; results include all male patients — non-empty (BUG-06 gate) |
| 4.2 | Type `姓张的女性` | Returns female patients whose name starts with 张 |
| 4.3 | Type `60多岁高血压患者` | Returns patients aged 60-69 with hypertension in their record tags/conditions |
| 4.4 | Type `xyznotapatient` | Empty state: "没有找到匹配的患者" or similar, no crash |

### 5. Search UX

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Debounce timing | Network request fires ~300ms after last keystroke, not on every character |
| 5.2 | Rapid typing | No request pileup, final query wins |
| 5.3 | Special chars `!@#` in search | No crash, no matches |

---

## Edge cases

- **100+ patients** — list scrolls smoothly; no virtualization stutter.
- **Patient with missing birth year** — card hides "N岁" cleanly, no "NaN岁".
- **Patient with 0 records** — card shows "0份病历" (or hides the count).
- **Emoji in patient name** — rendered correctly.
- **Very long patient name (20+ chars)** — truncated with ellipsis, no
  wrap.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues:

- **BUG-06** — ✅ Fixed `795729ff`. Regression gate: step 4.1 must
  return non-empty results for "最近来诊的男性".

---

## Failure modes & debug tips

- **NL search returns empty despite matching patients** — BUG-06 was
  caused by gender filter not recognizing Chinese values. Verify
  `/api/doctor/patients/search` accepts 男/女 in addition to male/female.
- **List doesn't update after creating a new patient** — query cache
  `QK.patients(doctorId)` not invalidated. Check the new-patient save
  handler.
- **Relative date shows "-1天前"** — BUG-01 regression; re-check
  `relativeDate` util imports `formatRelativeDate` from `utils/time`.
- **Autocomplete "+ 新建患者" row doesn't appear** — the row is only
  shown when search is non-empty AND no existing patient matches
  exactly. Verify the condition.
