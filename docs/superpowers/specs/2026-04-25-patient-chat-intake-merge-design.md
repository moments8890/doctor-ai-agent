# Patient Chat–Interview Merge — v1 Design Spec

> **Status:** v1.2 — strategy converged across 4 Codex review rounds. Ready for implementation plan.
> **Author:** Claude (synthesizing user intent + Codex rounds 1, 2, 3, 4 reviews)
> **Date:** 2026-04-25
> **Round-3 verdict:** "no ship-blockers, no longer strategy-stalled" — folded entry-counter observability and dedup auto-merge logic.
> **Round-4 verdict (dedup pressure-test):** caught three new failure modes — folded into v1.2: (a) merges are now **append-only with per-segment provenance**, never silent field overwrites; (b) merges into already-doctor-reviewed records are **pending supplements requiring doctor accept**, not auto-merge-and-notify; (c) dedup decision now factors **episode-boundary signals** (time gap, status change, treatment intervention) alongside chief_complaint similarity.

---

## What changed (v0 → v1 → v1.2)

| Area | v0 | v1 | v1.2 (round-4 fixes) |
|------|-----|-----|----------------------|
| Intake entry rule | classifier ≥ 0.7 **AND** lexical conjunct | classifier ≥ 0.65, lexicon **boosts** confidence, never gates | unchanged + entry-branch counters required |
| Write model | silent write → passive chip → 5min undo | draft → explicit confirm → promote | unchanged |
| Whitelist | 4 intents incl. `medication_timing_faq` | 3 intents only | unchanged |
| `extraction_confidence` | LLM self-report | **deterministic**: filled / 7 | unchanged |
| Dedup detection | not specified | chief_complaint similarity ≥ 0.7 within 24h | similarity AND **episode-boundary signals** (time, treatment event, status change) |
| Dedup auto-merge | n/a | "latest non-empty wins; concat present_illness" | **append-only with provenance**; no silent field overwrites; doctor view shows per-entry timestamps |
| Reviewed-record merges | n/a | auto-merge + notify doctor | **`RecordSupplementDB` pending doctor accept**; never auto-mutate reviewed work product |
| Red-flag ordering | not specified | retract whitelist reply if `urgent` fires same segment | unchanged |
| KB curation | per-item opt-in | one-shot doctor onboarding pass | unchanged |
| `qa_window` exit | 2-turn cap | tied to intent, 30min decay | unchanged |
| Rollback bookkeeping | soft-cancel rows | `cancellation_reason` enum | unchanged |

---

## Goal

Collapse the patient app's separate "新建问诊" entry into the main ChatTab so the patient experiences a single conversation surface. The system silently detects when a casual message becomes clinical intake, runs a sticky interview state with always-on red-flag protection, holds the structured fields in a draft, and only writes a doctor-visible record after a lightweight explicit confirmation. A small whitelist of intents gets autonomous AI replies; everything else is intake or doctor-routed.

The win is **one mental model for a 40+ WeChat-native patient population** — no CTA to find, no concept of "interview mode" to learn. The risk we are explicitly accepting is that intent classification becomes load-bearing on a model call, so the spec spends most of its weight on the safety scaffolding around that call.

## Non-goals

- Removing the doctor-facing review queue. Records remain the unit of doctor work; chat is intake.
- Letting AI directly answer diagnosis-adjacent or personalized clinical judgment questions. Whitelist is operational only.
- Big-bang replacement. The explicit `InterviewPage` stays as a control arm and fallback button until the merged flow proves equal-or-better on capture quality and routing safety.
- Re-enabling RAG / embeddings. Whitelist matches against doctor KB use the existing token-overlap scoring (`triage._check_kb_can_answer`).

---

## What exists today (one-screen recap)

- **ChatTab** (`frontend/web/src/v2/pages/patient/ChatTab.jsx`) calls `POST /api/patient/chat`, polls `GET /api/patient/chat/messages`. Per-turn `triage.classify()` → `{informational, symptom_report, side_effect, general_question, urgent}` → handler. KB-overlap downgrade already turns `side_effect`/`general_question` into auto-reply when a doctor KB item scores ≥ 4.
- **InterviewPage** (separate route) calls `start/turn/confirm/cancel`. `InterviewEngine` runs a template (`medical_general_v1`), then `MedicalRecordWriter.persist()` creates `MedicalRecordDB` with the 7 history fields.
- **MedicalRecordDB** has `status: interview_active|pending_review|diagnosis_failed|completed` and a `seed_source` column already wired for provenance.
- **Urgent** is a per-turn category that bypasses the 3-per-6h escalation rate limit and emits a static safety message.
- **Doctor review queue** (`/api/manage/review/queue`) sorts by urgency + ts, joins `AISuggestion` and `MedicalRecordDB`. Does **not** filter by `seed_source` today.

The merge therefore reuses the triage classifier as the **mode signal**, reuses `MedicalRecordDB` (no new table), and consumes the existing `seed_source` column for provenance. Most of the work is state machine, draft semantics, dedup matching, patient-visible UX, and doctor-side filter.

---

## Architecture: four primitives

### 1. ChatSessionState — sticky state machine on the chat thread

Per Codex round 1: a per-turn dispatcher will flap. Sticky state attached to the chat thread (one per patient).

```
States: { idle, intake, qa_window }
```

- **idle** — default. No active intake. Whitelist QA is allowed (returns templated answer). Anything not whitelist-eligible is routed to doctor as today.
- **intake** — entered when the per-turn classifier emits `symptom_report` with confidence ≥ 0.65 (see §1a). Carries a `MedicalRecordDB` row at `status=interview_active` and a partial `collected` dict. Doctor cannot see this row in the queue (`pending_review` filter excludes it).
- **qa_window** — short-lived state entered when, mid-`intake`, the patient asks a whitelist QA question (e.g., "顺便问一下，挂号怎么改时间"). System answers the QA, returns to `intake` on the patient's next intake-relevant turn or explicit "回到问诊" signal (see §1b — turn-count cap removed).

#### 1a. Entry rule (idle → intake) — trust the classifier, boost with lexicon

Codex round 2 was right: a lexical conjunct misses "头晕两天了" and "胃不舒服". v1 trusts the classifier as the primary signal:

```
enter_intake = (classifier.intent == symptom_report AND classifier.confidence >= 0.65)
            OR (classifier.intent == symptom_report AND classifier.confidence >= 0.50 AND lexicon_match)
```

Where `lexicon_match` is **any** of: a body-site term (头/胸/肚子/...), a symptom term (痛/晕/喘/...), a duration phrase (X天/几天/最近/...). The lexicon **boosts** a borderline classifier call into intake; it never **blocks** a confident one. This means a confident classifier call enters intake even on a sentence the lexicon misses, and a low-confidence call needs the lexicon as corroboration.

The 0.65 / 0.50 thresholds are tunable in pilot. Both default conservative — if pilot data shows we're missing intake we lower them; if we're false-positive-heavy we raise them.

**Required observability** (Codex round 3 ask): every intake entry logs which branch fired — `entered_by_primary_threshold` (classifier ≥ 0.65 alone) vs `entered_by_lexicon_boost` (classifier 0.50–0.65 with lexicon corroboration). Pilot dashboards must show false-positive rate split by branch. Without this, we can't tell which branch is causing problems and tuning becomes guesswork.

#### 1b. Sticky exit (intake → idle)

Intake exits only on:
1. Patient explicitly confirms record creation via the threshold-confirm gate (see §3) AND `MedicalRecordWriter.persist()` succeeds → record promoted to `pending_review`.
2. Patient explicitly cancels via `intake_cancel` micro-classifier (positive list: "我只是问问 / 不用记录 / 忽略 / 别记下来", confidence ≥ 0.85). Record soft-deleted with `cancellation_reason='patient_cancel'`.
3. Idle decay: 24h since last intake-relevant turn → record auto-cancelled with `cancellation_reason='idle_decay'`. Hidden from doctor queue, retained for audit.

Classifier confidence on its own cannot exit intake. We need a positive cancellation signal or a hard timeout.

#### 1c. qa_window exit (qa_window → intake)

qa_window exits when **any** of:
1. Patient's next message classifies as `symptom_report` or contains an intake-relevant signal (resumes intake naturally).
2. Patient sends an explicit "回到问诊 / 继续刚才的" signal (positive list, classifier confidence ≥ 0.85).
3. Patient sends another whitelist QA question — qa_window stays open (this is the "patient is genuinely doing logistics" case).
4. 30 minutes elapse with no message → return to intake silently with the in-progress draft preserved.

Codex round 2 noted "tied to intent completion, not turn count." The 2-turn cap is gone. qa_window exists as long as the patient is doing logistics and exits the moment they resume intake or signal it explicitly.

**Per-turn red-flag pass — runs in parallel regardless of state.** `urgent` classifier output bypasses the state machine entirely, fires the existing static safety message + immediate doctor notification, and flags the active record (if any) with `red_flag=true`. This is the Codex-mandated safety floor primitive. See §4 for the ordering rule when red-flag fires after a whitelist reply.

### 2. Whitelist for autonomous AI replies (positive list, narrow)

v0 had 4 intents. v1 drops `medication_timing_faq` per Codex round 2 — "is this med safe with my BP pills" looks like timing and is actually interaction. Patient phrasing collapses categories.

| Intent | Source of answer | Example trigger |
|--------|------------------|-----------------|
| `app_howto` | Static templates | "怎么改头像 / 字体太小怎么调" |
| `appointment_logistics` | Static + clinic config | "下次复诊几号 / 怎么改时间" |
| `procedure_prep_generic` | Doctor-pre-approved KB items only (`KnowledgeCategory.followup` with `patient_safe=true`) | "肠镜前一晚能吃什么" |

A reply is autonomous **only if** classifier confidence ≥ 0.8 AND (intent is template-backed OR a KB item scores ≥ 4 AND that KB item carries `patient_safe=true`). Everything else: ask one clarifier ("您指的是 A 还是 B?") or route to doctor.

`patient_safe` is a new boolean on `DoctorKnowledgeItem` — defaults `false`. v1 adds the KB curation onboarding requirement (see §6) — bulk per-item flipping without explicit doctor review is blocked.

`medication_timing_faq` is a v1+ candidate. We re-evaluate after observing how patients actually phrase medication questions in the merged-chat pilot data. Decision criterion before adding: a clinician-approved disambiguation prompt that distinguishes pure timing from interaction/missed-dose/tolerance/causality questions, plus a separate `patient_safe_medication=true` flag (different from `patient_safe`) that doctors must individually set per drug-instruction KB item.

### 3. Auto-record creation — draft-first, explicit confirm, then promote

Codex round 2 was right: silent writes at threshold pollute the queue. v1 reverses the order.

#### Schema additions

To `MedicalRecordDB`:
```sql
seed_source: enum('explicit_interview', 'chat_detected', 'imported')  -- existing column; backfilled
extraction_confidence: float NULL  -- DETERMINISTIC: see §3a
patient_confirmed_at: datetime NULL  -- set when patient confirms via threshold gate
cancellation_reason: enum('patient_cancel', 'patient_cancel_late', 'idle_decay', 'system_rollback', 'merged_into_existing') NULL
red_flag: boolean DEFAULT false  -- set by per-turn red-flag pass
intake_segment_id: string NULL  -- groups records that came from one continuous chat segment, see §5
dedup_skipped_by_patient: boolean DEFAULT false  -- patient explicitly chose 新开一条
```

**The 7 history fields change shape** (Codex round 4 — append-only with provenance). Each field becomes a list of entries instead of a single string:

```sql
-- Conceptual shape; concrete schema TBD in plan (likely a related table FieldEntryDB
-- with FK to MedicalRecordDB + field_name + text + intake_segment_id + created_at).
chief_complaint: list[(text, intake_segment_id, created_at)]
present_illness: list[(text, intake_segment_id, created_at)]
-- ... same for past_history, allergy_history, personal_history, marital_reproductive, family_history
```

Doctor view renders entries chronologically with visible separators ("初次描述" / "之后补充"). Existing single-string rows are migrated to a single-entry list with `created_at = record.created_at`.

New table `RecordSupplementDB` (Edge case 2 in §5b):
```sql
id: pk
record_id: fk → MedicalRecordDB
status: enum('pending_doctor_review', 'accepted', 'rejected_create_new', 'rejected_ignored')
field_entries: list[(field_name, text, intake_segment_id, created_at)]
created_at: datetime
doctor_decision_at: datetime NULL
doctor_decision_by: fk → doctor NULL
```

#### 3a. `extraction_confidence` — deterministic, not vibes

Codex round 2: "a fake confidence number is worse than no number." v1 defines it concretely.

```
extraction_confidence = (count of required history fields with non-empty values) / 7
```

Where the 7 fields are: `chief_complaint`, `present_illness`, `past_history`, `allergy_history`, `personal_history`, `marital_reproductive`, `family_history`. Range [0, 1.0]. Doctor-interpretable: 0.43 means 3 of 7 fields filled; 1.0 means all 7.

This is not a model self-report. It's a structural completeness measure. The doctor learns to read it as "how much of the standard intake the patient actually answered." That's a useful signal; LLM self-confidence is not.

#### 3b. Threshold for confirm gate

When `intake` reaches `chief_complaint + present_illness + (duration OR severity)` — the same "minimum useful intake" threshold from v0 — the system inserts a special chat message:

> 鲸鱼: 您刚才提到的情况，要为您整理成一条就诊记录给医生看吗?
> [整理给医生] [继续聊]

Two buttons. Default is no action (no implicit promotion).

- **整理给医生**: `MedicalRecordWriter.persist()` runs, record promoted from `interview_active` to `pending_review`, `patient_confirmed_at` set, state machine returns to `idle`. Doctor sees it in the review queue with `seed_source=chat_detected` and the `extraction_confidence` value.
- **继续聊**: state machine stays in `intake`. The draft persists. Threshold gate may re-fire later if more fields get filled.

If the patient ignores the gate (sends another message instead of tapping):
- If the new message is intake-relevant, treat as **implicit reinforcement** — the patient is still describing the issue. Update the draft and re-evaluate threshold; do not re-show the gate for at least 3 turns.
- If the new message is `intake_cancel` or whitelist QA, handle accordingly (cancel record, or enter qa_window).
- If 24h passes, idle decay applies (cancellation_reason='idle_decay').

The draft is never doctor-visible until the patient confirms. This is the v1 fix to the v0 "silent writes pollute the queue" problem. The cost is that intake-active records that never confirm sit in `interview_active` and consume DB rows; idle decay handles cleanup.

#### 3c. After-the-fact correction

Even after explicit confirmation, the patient retains correction surfaces:
- 5 minutes from `patient_confirmed_at`: an "[撤销刚才的整理]" chip stays attached to the chat message that confirmed creation. Tap → record reverts to `interview_active`, state machine re-enters intake.
- Beyond 5 minutes: RecordsTab swipe-delete (existing affordance). Triggers `cancellation_reason='patient_cancel_late'`.

This is the only place a passive chip survives in v1, and it's explicitly post-confirmation, so it can't pollute on its own.

### 4. Red-flag ordering — retract whitelist replies if red-flag fires same segment

The per-turn red-flag classifier runs in parallel with the state machine. If `urgent` fires on turn N **after** a whitelist autonomous reply was sent on turn N-K (K ≥ 1) within the same `intake_segment_id`:

1. Send a chat message: "鲸鱼: 抱歉，刚才的回答可能不够稳妥。请稍等，医生会立刻处理。"
2. Run the existing static urgent safety message + doctor notification.
3. Mark the prior whitelist reply with `retracted=true` (new column on chat messages) — visually struck through in the UI so the patient sees it was withdrawn.
4. Set `red_flag=true` on the active intake record (or create a `chat_detected` record at `interview_active` if none exists, so the doctor has context for the urgent escalation).

Codex round 2: "the ordering and suppression rules matter." This is the rule. The whitelist is allowed to be wrong if the safety net catches it; what's not allowed is the patient walking away from a stale low-risk answer when a red-flag has since fired.

---

## Deduplication — same-day, same-complaint matching

Codex round 2: "duplicate and fragmented record creation will wreck doctor trust faster than almost anything else." v1 defines the policy explicitly.

### 5a. Detection — similarity is necessary but not sufficient

When the threshold confirm gate is about to fire (§3b) for a patient who has another `pending_review` or `interview_active` record from the **same patient within the last 24h**, run a same-episode check that combines text similarity with episode-boundary signals (Codex round 4: "same complaint text can represent worsening, recurrence, or post-treatment change").

```
chief_complaint_similarity = LLM-judged 0..1 on whether two chief complaints describe the same clinical issue
hours_since_last = elapsed time since last patient turn on the candidate target record
treatment_event_since_last = boolean — did an AISuggestion get sent or doctor decision get made on the candidate target since its last patient input?
status_change_since_last = boolean — did the candidate target advance in status (interview_active → pending_review, pending_review → completed) since its last patient input?

same_episode = chief_complaint_similarity >= 0.5
            AND hours_since_last <= 24
            AND treatment_event_since_last == false
            AND status_change_since_last == false
```

If `same_episode` is true, dedup logic in §5b applies. If similarity is high but a treatment event or status change has occurred since the candidate's last patient input, dedup is **suppressed** — the patient is now describing post-treatment evolution, not a duplicate intake. A new record is created normally.

Episode-boundary signals are the round-4 fix to "complaint similarity is carrying too much weight." Same complaint text after a doctor's reply or status advance is by definition a new clinical episode.

Below 0.5 similarity, no dedup. Above 0.7 with all episode signals clear, auto-merge (§5b common case). Between 0.5 and 0.7 with episode signals clear, prompt the patient (§5b edge case).

### 5b. Append-only auto-merge for not-yet-reviewed; pending-supplement for reviewed; prompt for ambiguous

Codex round 3: "patients should confirm 'send this to doctor.' They should not also be asked to adjudicate your record-normalization problem every time the system sees overlap." Codex round 4: silent auto-merge into pre-existing pending records "fixed silent record creation and reintroduced silent record mutation." Both fixes are encoded below.

The behavior splits by candidate target status:

**Common case — target is `interview_active` or `pending_review` with no doctor decision yet, similarity ≥ 0.7:** auto-merge **append-only with provenance**. Show the standard confirm gate (§3b) with continuity-aware copy: "继续您之前的就诊记录，整理给医生? [整理给医生] [继续聊]". The patient confirms once.

The merge rules — Codex round 4's "append-only and provenance-preserving":
- **No silent overwrites of any prior field, ever.** Each field stores a list of `(text, intake_segment_id, timestamp)` entries, not a single string. The doctor view renders them in order with visible timestamps and a soft separator ("初次描述" / "之后补充"). The doctor reads exactly what the patient described, when they described it, never a stitched narrative pretending to be one coherent intake.
- `chief_complaint`: append only if the new value differs from all prior entries; otherwise drop the duplicate addition.
- All 7 history fields: append the new non-empty value with its provenance entry. Prior entries are not edited.
- `extraction_confidence` recomputed against the union of filled fields.

**Edge case 1 — similarity in [0.5, 0.7] with episode signals clear:** prompt the patient explicitly with three options:

> 鲸鱼: 您之前提到过类似的情况。要把刚才的内容并入上一次记录，还是新开一条?
> [并入上一次] [新开一条] [都不要]

- **并入上一次**: same append-only merge as common case.
- **新开一条**: standard confirm path. Record flagged with `dedup_skipped_by_patient=true` so the doctor sees the patient explicitly chose to fragment.
- **都不要**: cancel the draft (`cancellation_reason='patient_cancel'`). State returns to idle.

**Edge case 2 — target is already doctor-reviewed (`completed`, has AISuggestion decision, or status > `pending_review`):** the patient prompt is the same three buttons as Edge case 1, but the consequences differ. Codex round 4: "treat reviewed records as immutable unless the doctor accepts the supplement merge."

- **并入上一次**: do **not** auto-mutate the reviewed record. Instead, create a `RecordSupplementDB` row attached to the target record, status `pending_doctor_review`. The supplement carries the new field entries (same provenance shape as common-case merges) and surfaces in the doctor's review queue as a new work item: "患者补充了上次就诊记录" with [接受补充] / [创建新记录] / [忽略] actions on the doctor side. Until the doctor acts, the original reviewed record is unchanged. The patient sees a passive chip ("已发送给医生确认") — they have done their part.
- **新开一条**: same as Edge case 1 — flag and create new.
- **都不要**: cancel.

This keeps reviewed records as clinical work product. The patient cannot silently rewrite history a doctor has already consumed; the doctor's queue is the authority on what becomes part of the clinical record.

### 5c. intake_segment_id — bound the dedup scope

Every chat-derived record carries an `intake_segment_id`. A segment is one continuous run of chat where intake state was active or recently active (defined as: gaps ≤ 30 minutes between intake-relevant turns). Two records sharing an `intake_segment_id` are by definition from the same conversational arc and dedup is **mandatory** between them — not patient-prompted, automatic merge with a passive chip ("已并入本次问诊记录").

Cross-segment dedup follows §5b (auto-merge for not-yet-reviewed targets, prompt for reviewed/diverged). Same-segment dedup is system-managed. This is the line: the same arc of conversation should never produce two records; same complaint across two arcs (morning then evening) is a §5b decision.

**Required guard** (Codex round 3): segment auto-merge **must never silently touch a doctor-reviewed record**. If `intake_segment_id` matching surfaces a target whose status is `completed` or has an `AISuggestion` decision, the auto-merge is suppressed and the §5b prompt fires instead. Same-segment auto-merge is only "silent" when it cannot affect work the doctor already touched. Segment-boundary logic must also be visible in logs (segment id, segment start ts, the gap that closed it) — a misclassified boundary that merges what the patient experienced as separate episodes is exactly the failure mode that erodes trust fastest.

---

## Doctor-side changes

The review queue gains a provenance filter, a column, and a confidence indicator:

- **Filter chips** above the queue: `全部 | 问诊完成 | 自动整理` — defaults to 全部. "自动整理" maps to `seed_source='chat_detected'`.
- **Row badge** on chat-derived records: small "对话整理" tag. `extraction_confidence` shown as a small ring (0/7 to 7/7 visual) — not a percentage, not a colored severity dot. The denominator is right there so doctors learn what the number means.
- **Red-flag bubble** if `red_flag=true` from the per-turn urgent pass — same surface as today's existing urgent escalation, anchored to the record.
- **Retracted-reply indicator**: any chat message marked `retracted=true` (from §4) is shown struck through in the doctor's chat-history view of the patient, with a small "已撤回 (危险信号触发)" annotation. Doctors see exactly what the patient saw and what the system pulled back.

Records keep their existing edit-and-confirm flow. No change to how doctors compose AI suggestions — that's downstream of `pending_review`.

---

## Migration plan — parallel flows, no big bang

**Phase 0: backend safety floor.** `seed_source` column populated on existing rows. New columns added (Alembic migration): `extraction_confidence`, `patient_confirmed_at`, `cancellation_reason`, `red_flag`, `intake_segment_id`, `dedup_skipped_by_patient`. New `retracted` column on chat messages. `patient_safe` field on `DoctorKnowledgeItem`. Per-turn red-flag classifier pulled out of `triage_handlers.handle_urgent` into a standalone always-on pass. **Ship this first, even before any UX change** — it's the floor regardless of whether merge ships.

**Phase 0.5: doctor KB curation onboarding.** New `KbCurationOnboardingDone` doctor-level flag. Until set, no `patient_safe=true` flag is honored on any of that doctor's KB items, even if individually marked. The KB editor surfaces a one-shot review pass: doctor walks through every existing KB item, decides patient-safe or not, then sets the onboarding-done flag. This is the round-2 fix to "per-item opt-in is not enough." We force the deliberate first-pass curation before patient-facing answers go live for that doctor.

**Phase 1: dual-mode chat backend.** ChatTab POST endpoint gains state-machine logic. Whitelist intents start replying autonomously (only for doctors who completed Phase 0.5). Draft-first record creation goes live but `intake` state has a feature flag (`PATIENT_CHAT_INTAKE_ENABLED`, doctor-scoped) — defaults off for everyone except 3 pilot doctors. Explicit `InterviewPage` continues to work unchanged.

**Phase 2: pilot.** Feature-flag intake on for ~5 doctors (~50 patients) who have completed Phase 0.5. Two weeks. Measure:
- false-positive record rate (`chat_detected` records doctor cancels in review)
- false-negative escalation rate (red-flag turns the system missed, caught by doctor)
- whitelist mis-fire rate (autonomous replies the doctor would have answered differently)
- patient correction rate (gate `继续聊` taps + post-confirm `撤销` taps)
- explicit-interview usage (does it drop, hold, or rise among pilot doctors)
- entry-branch split (`entered_by_primary_threshold` vs `entered_by_lexicon_boost`) and FP rate per branch
- **dedup band defensibility** (Codex round 4 ask): auto-merge precision above 0.7 (doctor-reversal rate after silent merge), prompt-trigger rate inside [0.5, 0.7], patient choice distribution in-band (并入 / 新开 / 都不要), false-negative duplicate rate below 0.5 (records the doctor later flags as obvious duplicates of an earlier one)
- **supplement acceptance** (Edge case 2): for reviewed-record supplements, doctor accept rate vs create-new vs ignore. Low accept rate signals the patient prompt should bias toward 新开一条 instead.

Hard rollback if any of: red-flag miss > 0 in pilot, FP record rate > 15%, whitelist mis-fire causes a documented patient harm event, or dedup prompt confusion rate (patients tap 都不要 then immediately re-describe symptoms) > 25%.

**Phase 3: default-on.** If pilot metrics clear, flip default. `InterviewPage` stays in the patient app as a small secondary CTA ("结构化问诊 →") for one quarter as a control arm + fallback. Kill-it-when criterion: `chat_detected` records' doctor-cancel rate ≤ explicit-interview cancel rate, AND explicit-interview usage drops below 10% of intake events for 4 consecutive weeks.

---

## Safety floor — must-ship gates

Per Codex rounds 1 and 2, none of these are negotiable:

- [ ] Always-on per-turn red-flag classifier, independent of state.
- [ ] Whitelist-only autonomous replies. No blacklist anywhere in the codebase.
- [ ] `patient_safe=true` required on KB items used in patient-facing replies, AND doctor `KbCurationOnboardingDone=true` required (Phase 0.5).
- [ ] `seed_source` provenance flag on every chat-derived record.
- [ ] Draft-first writes only. No promotion to `pending_review` without `patient_confirmed_at`.
- [ ] Threshold confirm gate (§3b) at every record promotion.
- [ ] 5-minute post-confirm undo + RecordsTab swipe-delete as longer-tail correction.
- [ ] Idle decay (24h) auto-cancels stale `interview_active` rows with `cancellation_reason='idle_decay'`.
- [ ] Dedup detection combines chief_complaint similarity AND episode-boundary signals (§5a); same complaint after a doctor decision or status advance is **not** a duplicate.
- [ ] Dedup merges are **append-only with provenance** (§5b common case) — no silent field overwrites, doctor view shows each entry's timestamp and segment.
- [ ] Auto-merge applies only when target is `interview_active` or undecided `pending_review` AND similarity ≥ 0.7 AND episode signals clear. [0.5, 0.7] band prompts the patient.
- [ ] Reviewed-record merges (§5b Edge case 2) create a `RecordSupplementDB` row pending doctor accept; **never auto-mutate clinical work product**.
- [ ] Same-segment auto-merge (§5c) without prompting, but never against a doctor-reviewed record (falls back to §5b Edge case 2 supplement flow).
- [ ] Entry-branch observability counters (`entered_by_primary_threshold` vs `entered_by_lexicon_boost`) wired into pilot dashboards. Without this, intake threshold tuning is guesswork.
- [ ] Red-flag retraction (§4) when `urgent` fires after a whitelist reply in the same segment.
- [ ] Doctor-side provenance badge + filter + extraction_confidence indicator shipped same release as auto-record creation.
- [ ] Hard rollback procedure: feature flag off → ChatTab returns to triage-only behavior, in-flight `interview_active` rows soft-cancelled with `cancellation_reason='system_rollback'` (excluded from user-behavior analytics by definition).

---

## Open questions for Codex round 3

v0 closed: Q3 (extraction_confidence — now deterministic), Q6 (medication_timing_faq — out for v0). v1 reframes the remaining set:

**Q1.** `intake_cancel` and `qa_resume` micro-classifiers — keep separate from main triage (latency cost: extra LLM call per applicable turn) or fold into main classifier output (prompt cost: more complex JSON schema, more failure surfaces)? My instinct is fold into main classifier as additional optional fields in the JSON schema.

**Q2.** Threshold confirm gate copy — proposed: "您刚才提到的情况，要为您整理成一条就诊记录给医生看吗? [整理给医生] [继续聊]". The verb 整理 is gentle but might read as too informal for a clinical action. Alternatives: 保存为 / 提交给 / 记录给. Pick one for v0 or test in pilot?

**Q3 (was Q5).** `InterviewPage` long-term — Phase 3 keeps it for one quarter as control. Is the kill criterion sound (cancel rate parity + < 10% usage for 4 weeks), or do you want stronger evidence before deletion? E.g., patient-survey signal that they don't miss it, or doctor-survey signal that record quality is equivalent.

**Q4 (was Q4).** Threshold confirm gate copy variants — same as Q2 but specifically for patient-facing trust. Three frames: action-explicit ("整理成就诊记录") vs benefit-explicit ("整理给医生看") vs minimal ("保存"). 40+ Chinese WeChat audience reads 记录 with weight. Worth pilot A/B?

**Q5.** Dedup similarity threshold (§5a) — 0.7 picked from intuition. Too high → false-negative duplicates (queue spam returns). Too low → false-positive merges (different episodes get conflated). Pilot tuning or pre-ship benchmark needed?

**Q6.** When a doctor has not completed Phase 0.5 KB curation but the patient asks an `app_howto` or `appointment_logistics` question (which use static templates, not KB items) — should those still be blocked? Strictly, those don't depend on KB items. Loosely, blocking until full curation may slow Phase 1 rollout. Lean toward: static-template intents always available; KB-derived (`procedure_prep_generic`) blocked until curation done.

**Q7.** Doctor-side `extraction_confidence` display — ring visual (0/7 to 7/7) was chosen for honesty. Alternative: show the actual filled fields as a tag list ("已填: 主诉, 现病史, 过敏史"). The tag list is even more honest but takes more queue real estate. Compromise: ring on the row, expanded tag list in detail view?

---

## What this spec deliberately does not specify

- File-by-file implementation map. That belongs in the plan, after Codex round 3 ratifies the architecture.
- Test plan. Same.
- The exact static templates for whitelist intents. Drafting copy is a separate, smaller spec.
- Multi-patient or multi-doctor chat semantics. Out of scope for v0.
- The `KbCurationOnboardingDone` flow's UI. v0 plan needs to spec this; v1 architecture spec just declares the requirement.

---

## Round-3 ask for Codex

Three questions framed bluntly:

1. **Did the v1 entry rule (trust classifier ≥ 0.65, lexicon as boost only) actually solve the v0 lexical-overfit problem, or did I introduce a new flapping risk by lowering the gate?** Specifically: is the 0.50/0.65 + lexicon-boost formula defensible, or do you want a single threshold with no lexicon involvement at all?

2. **Is the draft-first + explicit confirm gate + dedup prompt sequence one too many friction points for a 40+ patient who just wanted to describe a symptom?** Or is this the right amount of "the system is being careful" friction? If it's too much, where would you cut: skip dedup prompt (auto-merge always), skip confirm gate (revert to passive chip), or accept multiple gates as the cost of safety?

3. **Of the 7 v1 open questions, which one would you actually block ship on?** I want a single ship-blocker, not two — v1 tightened enough that more than one feels like bikeshedding. If you don't have a ship-blocker, say so.
