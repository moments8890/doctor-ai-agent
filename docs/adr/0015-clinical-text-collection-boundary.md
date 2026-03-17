# ADR 0015 — Clinical Text Collection Boundary

**Status:** Accepted
**Date:** 2026-03-17
**Supersedes:** ADR 0012 §8 (partial — refines archive scan behavior)

## Context

`_collect_clinical_text()` in `commit_engine.py` accumulates user turns from
`chat_archive` to build the input for the structuring LLM when creating a new
record. This supports multi-message dictation where a doctor sends clinical
content across several messages:

```
Message 1: "王芳，女45岁"
Message 2: "胸痛3天，活动后加重"
Message 3: "血压140/90，诊断高血压"
→ All three should be merged into one structured record
```

### Problem

The current implementation fetches the **last 30 user turns** for the patient
with no temporal boundary:

```python
stmt = (
    select(ChatArchive)
    .where(
        ChatArchive.doctor_id == doctor_id,
        ChatArchive.patient_id == patient_id,
        ChatArchive.role == "user",
    )
    .order_by(ChatArchive.created_at.desc())
    .limit(30)
)
```

This causes two defects:

1. **Cross-record contamination:** After saving a record, the next record for
   the same patient re-ingests all previous turns. Old clinical data (symptoms,
   diagnoses, exam results) leaks into the new record.

2. **Stale turn accumulation:** Turns from hours or days ago are included even
   when they belong to a prior clinical encounter.

**Observed impact (MVP-ACC-025):**
- Input: "创建患者王芳，胸痛，说错了，头痛"
- Structuring received 6 old turns + current input
- Output included "头痛2小时伴大汗，心电图提示下壁ST段抬高" — data from a
  previous record that was never in the current input.

### Scope of impact

| Action type | Uses archive scan | Affected |
|-------------|-------------------|----------|
| record      | Yes (`_collect_clinical_text`) | **Yes** |
| update      | No (existing record + instruction) | No |
| task        | No (args from understand) | No |
| query       | No (read-only) | No |
| none        | No (chat reply) | No |

## Decision

Apply a **dual boundary** to `_collect_clinical_text`:

### Boundary 1: Last saved record cutoff

Only fetch archive turns created **after** the most recent `medical_records`
row for the same patient + doctor. This ensures each new record starts from a
clean slate.

```sql
SELECT MAX(created_at) FROM medical_records
WHERE doctor_id = ? AND patient_id = ?
```

Archive turns before this timestamp are excluded.

### Boundary 2: Recency window (30 minutes)

Even before the first record is saved for a patient, cap the lookback to
**30 minutes**. This prevents stale turns from prior sessions leaking in.

The effective cutoff is:

```python
cutoff = max(last_record_timestamp, now - 30_minutes)
```

If no record exists for this patient, only the 30-minute window applies.

### Boundary 3: Retain limit(30) as safety cap

The existing `LIMIT 30` remains as a hard cap to prevent unbounded queries,
but the temporal boundaries above will be the primary filter in practice.

## Implementation

Single function change in `commit_engine.py:_collect_clinical_text`:

1. Query `MAX(medical_records.created_at)` for the patient + doctor.
2. Compute `cutoff = max(last_record_ts, now - timedelta(minutes=30))`.
3. Add `.where(ChatArchive.created_at > cutoff)` to the archive query.
4. Keep `LIMIT 30` and `user_input` append logic unchanged.

No schema changes. No prompt changes. No changes to other action types.

## Consequences

### Positive

- Records no longer contain clinical data from prior encounters.
- Multi-message dictation within a session still works (30-min window).
- Self-correction patterns ("说错了") work naturally — only current session
  turns are included.
- Zero impact on update, task, query, none action paths.

### Negative

- One additional DB query per record creation (MAX on indexed column —
  negligible cost, `ix_records_doctor_created` covers it).
- If a doctor takes >30 minutes between messages for the same patient
  within a single encounter, earlier messages are excluded. Acceptable
  trade-off — real dictation sessions are much shorter.

### Risks

- Edge case: doctor sends messages 31 minutes apart for the same patient.
  Mitigation: 30 minutes is conservative; can be tuned via env var if needed.

## Follow-up: Update workflow context

The `update` action path (`_update_record`) is not affected by this ADR — it
uses `existing.content` + doctor's instruction, no archive scan. However, a
related improvement exists:

Currently update feeds the human-readable `content` string back through
structuring as the source of truth:

```python
combined = f"{existing_content}\n\n---\n医生修改指令：{instruction}"
record = await structure_medical_record(combined)
```

With the `structured` field now stored (see structuring.md dual-output), a
future optimization could feed `existing.structured` (the machine-readable
dict) instead of `existing.content` to the structuring LLM. This would:

- Avoid lossy round-trip through content → re-parse → content
- Give the LLM precise field boundaries to apply the modification to
- Produce more accurate updates for field-specific instructions
  (e.g. "把诊断改成冠心病" → only touch `diagnosis` field)

**Status:** Deferred — current approach works; optimize when update accuracy
becomes a priority.
