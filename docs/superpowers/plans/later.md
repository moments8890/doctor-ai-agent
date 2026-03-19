# Deferred Items

## _collect_clinical_text — missing watermark for patient-scoped archive scan

**File:** `src/services/runtime/commit_engine.py` — `_collect_clinical_text()`

**Issue:** The patient-scoped query fetches the last 30 `role=user` ChatArchive rows
with no `created_at > last_record_created_at` boundary. Turns that already
contributed to a previous saved record for the same patient are re-included
in the next structuring call, potentially duplicating clinical content across
records.

**Docstring says:** "user turns since last completed record for the patient" —
but the implementation does not enforce this.

**Impact:** Low in practice when records are created frequently (30-turn window
is small). Becomes noticeable when the same patient has long gaps between
records — old turns bleed into the new record's structuring input.

**Design question:** Should `_collect_clinical_text` return full historical
context or only turns since the last record? The answer depends on whether
the structuring LLM benefits from repeated context or whether it causes
content duplication. Needs a product decision before implementing.

**Potential fix:** Add a subquery to find the most recent
`MedicalRecordDB.created_at` for this patient and filter
`ChatArchive.created_at >` that watermark.
