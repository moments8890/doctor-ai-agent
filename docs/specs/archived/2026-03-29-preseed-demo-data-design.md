# Preseed Demo Data — Design Spec

**Goal:** After a doctor finishes onboarding, automatically seed their account with 5 realistic LVB-for-AD patients showcasing every core feature: knowledge-driven AI diagnosis, smart message triage, auto-reply, and task generation.

**Target user:** Dr. 陆华 (Lu Hua) and team at Jiangnan University Affiliated Hospital — cervical deep lymphatic-venous bypass (LVB) surgery for Alzheimer's disease.

---

## What Gets Seeded

All data is created automatically when a doctor completes onboarding. No manual input required.

### Knowledge Items (2)

| ID | Title | Content Summary |
|----|-------|-----------------|
| KB-1 | LVB术后管理规范 | Post-op care: ICG follow-up timing, complication signs (lymphatic leak, anastomotic thrombosis, hyperperfusion), medication continuation, cognitive assessment schedule (MMSE/MoCA at 2w/3m/6m), nasal mucosal ICG injection method, activity restrictions |
| KB-2 | AD诊断与鉴别标准 | Diagnostic criteria: typical vs atypical AD (PCA, logopenic), differential from VCI/NPH/DLB, PET-CT Aβ imaging indications, MRI black blood sequence for lymphatic baseline, CSF biomarkers (Aβ42/p-tau), MMSE≥15 as LVB candidacy threshold |

All AI outputs in seeded data cite these as `[KB-1]` or `[KB-2]`.

### Patients (5)

| # | Name | Age/Sex | Stage | Showcase Focus |
|---|------|---------|-------|---------------|
| 1 | 张秀兰 | 72F | LVB术后2周，恢复顺利 | Routine auto-reply, cognitive tracking |
| 2 | 李建国 | 68M | LVB术后1月，颈部肿胀 | Urgent escalation, complication diagnosis |
| 3 | 王美华 | 65F | 新患者，首次就诊 | **New diagnosis**: AD vs VCI vs NPH |
| 4 | 陈伟强 | 71M | 新患者，非典型表现 | **New diagnosis**: PCA-AD vs DLB, visual/dizziness symptoms |
| 5 | 刘淑芬 | 70F | LVB术后6月，症状反复 | Relapse detection, anastomotic re-evaluation |

### Per Patient Data

| Patient | Records | AI Suggestions | Messages | Triage Mix | Tasks |
|---------|---------|---------------|----------|------------|-------|
| 张秀兰 | 3 (初诊 + 手术 + 复查) | 3 on pending record | 4 | 2 routine + 2 info → all auto | 2 |
| 李建国 | 3 (初诊 + 手术 + 复查) | 3 on pending record | 3 | 1 routine→auto, 2 urgent→doctor | 2 |
| 王美华 | 2 (外院 + 首诊) | 5 on pending record | 3 | 1 routine→auto, 2 question→doctor | 3 |
| 陈伟强 | 2 (外院 + 首诊) | 4 on pending record | 3 | 2 routine→auto, 1 question→doctor | 4 |
| 刘淑芬 | 3 (初诊 + 手术3月 + 随访6月) | 3 on pending record | 3 | 1 info→auto, 1 concern→doctor, 1 question→doctor | 2 |

**Totals:** 5 patients, 13 records, 18 AI suggestions, 16 messages, 13 tasks

### Message Triage Distribution

| Triage | Count | Handling | Purpose |
|--------|-------|----------|---------|
| routine | 5 | Auto-sent | Shows AI handles common questions |
| info | 3 | Auto-sent | Shows AI acknowledges updates |
| question | 4 | Doctor draft | Shows AI drafts answers using KB, waits for review |
| urgent | 2 | Doctor draft | Shows AI detects danger, escalates immediately |
| concern | 2 | Doctor draft | Shows AI recognizes worry, flags for attention |

**Auto-handled: 8 (50%)** — doctor sees "AI saved you time"
**Doctor review: 8 (50%)** — doctor sees "AI knows when to ask you"

---

## Architecture

> Revised after Codex review — addresses schema mismatch, transaction safety, provenance, and timestamp realism.

### Data Storage

All seeded content lives in a JSON seed file, validated through typed Pydantic models:

```
src/channels/web/ui/preseed_data.json    — content only
src/channels/web/ui/preseed_schema.py    — Pydantic models for JSON validation
src/channels/web/ui/preseed_service.py   — orchestrate seed/reset in one transaction
```

JSON structure:
```json
{
  "knowledge_items": [
    { "key": "kb_lvb_postop", "title": "...", "content": "..." },
    { "key": "kb_ad_diagnosis", "title": "...", "content": "..." }
  ],
  "patients": [
    {
      "key": "zhang_xiulan",
      "name": "张秀兰", "gender": "female", "age": 72,
      "days_ago": 14,
      "records": [
        {
          "key": "initial_visit",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 30,
          "chief_complaint": "...",
          "present_illness": "...",
          "suggestions": []
        },
        {
          "key": "postop_2w",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "...",
          "suggestions": [
            { "section": "differential", "content": "...", "detail": "... [KB-1]", "confidence": "高", "urgency": "normal" }
          ]
        }
      ],
      "messages": [
        {
          "content": "...",
          "triage": "routine",
          "auto_send": true,
          "ai_reply": "...",
          "days_ago": 10
        }
      ],
      "tasks": [
        { "title": "...", "task_type": "follow_up", "due_days": 90 }
      ]
    }
  ]
}
```

### Provenance — `seed_source` column

> Codex finding: existing fields (`tags`, `triage_category`, `source_type`) are domain fields and should not be overloaded for provenance tracking.

Add a nullable `seed_source` VARCHAR column to the tables that need cleanup:

| Table | Column added | Value when seeded |
|-------|-------------|-------------------|
| `doctor_knowledge_items` | `seed_source` | `"onboarding_preseed"` |
| `medical_records` | `seed_source` | `"onboarding_preseed"` |
| `patient_messages` | `seed_source` | `"onboarding_preseed"` |
| `message_drafts` | `seed_source` | `"onboarding_preseed"` |
| `ai_suggestions` | `seed_source` | `"onboarding_preseed"` |
| `doctor_tasks` | `seed_source` | `"onboarding_preseed"` |
| `patients` | `seed_source` | `"onboarding_preseed"` |

Non-seeded rows have `seed_source = NULL`. Cleanup query: `DELETE FROM X WHERE doctor_id = ? AND seed_source = 'onboarding_preseed'`.

This keeps domain fields (`triage_category`, `source_type`, `tags`) clean for their intended purpose. Messages get real triage values (`routine`, `urgent`, etc.) AND `seed_source` for provenance.

### Timestamp Realism

> Codex finding: all objects created with `now()` looks fake.

Each JSON entry has a `days_ago` field. At seed time, timestamps are calculated relative to current time:

```python
created_at = datetime.now(timezone.utc) - timedelta(days=spec["days_ago"])
```

Example timeline for 张秀兰:
- Initial visit: 30 days ago
- Surgery: 16 days ago
- Post-op follow-up: today
- Messages: spread across 10, 7, 3, 1 days ago

### Transaction Safety

> Codex finding: per-helper commits create half-seeded accounts on failure.

The entire seed operation runs in **one database transaction**:

```python
async def seed_demo_data(db: AsyncSession, doctor_id: str) -> SeedResult:
    """Seed all demo data in one transaction. Rolls back on any failure."""
    # Phase 1: Create knowledge items
    kb_items = await _seed_knowledge(db, doctor_id, spec)
    # Phase 2: Create patients
    patients = await _seed_patients(db, doctor_id, spec)
    # Phase 3: Create records + AI suggestions
    await _seed_records(db, doctor_id, patients, kb_items, spec)
    # Phase 4: Create messages + drafts
    await _seed_messages(db, doctor_id, patients, kb_items, spec)
    # Phase 5: Create tasks
    await _seed_tasks(db, doctor_id, patients, spec)
    # Single commit at the end
    await db.commit()
    return result
```

No intermediate commits. If anything fails, the entire transaction rolls back — no half-seeded state.

### API

#### `POST /api/manage/onboarding/seed-demo`

**Non-destructive.** Creates seed data only if not already present. If seed data exists (any row with `seed_source = 'onboarding_preseed'` for this doctor), returns the existing data without modification. Safe for retry/double-submit.

**Request:**
```json
{ "doctor_id": "..." }
```

**Response:**
```json
{
  "status": "ok",
  "already_seeded": false,
  "knowledge_items": [{ "id": 1, "title": "..." }, ...],
  "patients": [
    { "id": 1, "name": "张秀兰", "record_count": 3, "message_count": 4, "task_count": 2 }
  ],
  "totals": { "patients": 5, "records": 13, "messages": 16, "tasks": 13 }
}
```

If already seeded: `{ "status": "ok", "already_seeded": true, ... }` with existing counts.

#### `POST /api/manage/onboarding/seed-demo/reset`

**Explicit destructive.** Deletes all `seed_source = 'onboarding_preseed'` data for the doctor, then re-creates it. Used for "重新生成演示数据" button.

Deletion order (respects FK relationships):
1. `ai_suggestions` (FK → records)
2. `message_drafts` (FK → messages)
3. `doctor_tasks` (FK → patients/records)
4. `patient_messages` (FK → patients)
5. `medical_records` (FK → patients)
6. `doctor_knowledge_items`
7. `patients` (last — other tables reference patient_id)

#### `DELETE /api/manage/onboarding/seed-demo`

Removes all seed data without re-creating. Doctor wants a clean slate.

### Trigger

The seed endpoint is called from the frontend when:
1. Doctor completes the onboarding wizard (`markWizardDone`) → `POST seed-demo`
2. Doctor taps "重新生成演示数据" in settings → `POST seed-demo/reset`
3. Doctor taps "清除演示数据" in settings → `DELETE seed-demo`

### Guard

Single canonical guard: `ALLOW_DEMO_SEED` environment variable (default `true` in dev, `false` in prod). No ad-hoc environment sniffing.

```python
def _require_demo_seed_access():
    if os.environ.get("ALLOW_DEMO_SEED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")
```

### KB Reference Resolution

The JSON seed file uses `[KB-1]` and `[KB-2]` placeholders. At seed time, replaced with actual IDs within the same transaction (knowledge items are created first):

```python
def _resolve_kb_refs(text: str, kb_map: dict[str, int]) -> str:
    for placeholder, real_id in kb_map.items():
        text = text.replace(placeholder, f"[KB-{real_id}]")
    return text
```

---

## Medical Content Source

All medical content is derived from Dr. 陆华's published clinical experience:
- Nasal mucosal ICG injection method for cervical deep lymphatic visualization
- LVB post-op complications: lymphatic leak, anastomotic thrombosis
- Cognitive improvement patterns: MMSE changes, behavioral improvements
- PCA-variant AD with visual symptoms improving post-LVB
- Symptom relapse and anastomotic stenosis as differential
- LVB pump invention for reducing surgical complexity

Content preview: `docs/dev/preseed-demo-preview.html`

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/channels/web/ui/preseed_data.json` | All seed content (5 patients, 2 KB items) |
| Create | `src/channels/web/ui/preseed_schema.py` | Pydantic models for JSON validation |
| Create | `src/channels/web/ui/preseed_service.py` | Seed/reset orchestration in one transaction |
| Modify | `src/db/models/doctor.py` | Add `seed_source` column to `DoctorKnowledgeItem` |
| Modify | `src/db/models/patient.py` | Add `seed_source` column to `Patient` |
| Modify | `src/db/models/records.py` | Add `seed_source` column to `MedicalRecordDB` |
| Modify | `src/db/models/patient_message.py` | Add `seed_source` column to `PatientMessage` |
| Modify | `src/db/models/message_draft.py` | Add `seed_source` column to `MessageDraft` |
| Modify | `src/db/models/ai_suggestion.py` | Add `seed_source` column to `AISuggestion` |
| Modify | `src/db/models/tasks.py` | Add `seed_source` column to `DoctorTask` |
| Modify | `src/channels/web/ui/doctor_profile_handlers.py` | Add 3 seed-demo endpoints |
| Modify | `frontend/web/src/pages/doctor/OnboardingWizard.jsx` | Call seed-demo on completion |
| Modify | `frontend/web/src/api/mockApi.js` | Mock seed-demo response |

---

## Relationship to Existing Code

The current `ensureOnboardingExamples` endpoint and its helper functions (`_ensure_onboarding_patient`, `_ensure_diagnosis_example`, `_ensure_reply_example`, `_ensure_auto_handled_messages`) are kept as a dev/debug route until the new preseed system is proven. Then they can be removed.

The `create_onboarding_patient_entry` endpoint (for the intake demo patient) remains separate — it's used during the wizard's intake step, not for seeding demo data.

---

## Codex Review Notes

Issues addressed from Codex review (2026-03-29):
1. ~~Schema mismatch~~ → Added `seed_source` provenance column to all relevant tables
2. ~~Destructive POST~~ → POST is non-destructive; explicit `/reset` for destructive operation
3. ~~Patient name collision~~ → Patients get `seed_source` column; cleanup uses provenance not name
4. ~~`triage_category` overload~~ → Messages use real triage values + separate `seed_source`
5. ~~Partial failure~~ → Single transaction, rollback on any error
6. ~~Timestamp realism~~ → `days_ago` field in JSON, relative timestamp calculation at seed time
