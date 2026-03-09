# Database Schema Review — Doctor AI Agent (MVP)

**Date:** 2026-03-09
**Reviewed by:** 5 independent analysis agents (completeness, cascades, integrity, performance, security)
**Audience:** Senior Engineer / CTO
**Scope:** Full SQLAlchemy model layer (`db/models.py`) as of commit `2071fad`

---

## Executive Summary

Five independent reviews of the schema revealed a consistent pattern: the core transactional tables are sound, but a cluster of dead-weight tables, several critical cascade misconfigurations, and missing compliance instrumentation create meaningful risk before and after launch.

Key findings:

- **Audit trail is erasable by design.** `audit_log.doctor_id` is configured `ondelete=CASCADE`, meaning a single `DELETE FROM doctors` permanently destroys the entire compliance record for that doctor. This is the highest-severity finding in the review.
- **READ operations are never logged.** Patient list, detail, and record views produce zero `audit_log` entries. This violates the principle of access accountability required by GDPR/HIPAA-equivalent frameworks and will be a blocker for any formal compliance audit.
- **~8 tables are dead weight** (specialty clinical context tables, `DoctorNotifyPreference`, `ChatArchive`, `DoctorKnowledgeItem`) accounting for roughly 940 lines of model code with zero active callers in routers, services, or CRUD. They increase cognitive load and migration surface with no MVP benefit.
- **No retention policy on any append-only table.** `chat_archive` and `audit_log` grow without bound; `pending_records` retains PII indefinitely after expiry; `MedicalRecordVersion` stores full plaintext history forever.
- **Seven high-traffic query paths lack covering indexes**, including the expiry scheduler's hot path on `pending_records(status, expires_at)` and the UI name-search on `patients(name)`.
- **All enum-like string columns lack CHECK constraints.** Any string value is accepted at the DB layer for 18+ columns whose valid domain is a closed set of 2–6 values. Application-layer bugs or direct SQL writes can silently corrupt state.
- **Cross-doctor data access is enforced only at the application layer.** No composite FK or row-level security prevents a `medical_record.patient_id` from belonging to a patient owned by a different doctor.
- **`NeuroCaseDB` is a parallel structure to `MedicalRecordDB`** with overlapping semantics. Dual-write paths will diverge; consolidation via a `record_type` discriminator is the right long-term shape.

---

## 1. Schema Completeness for MVP

### 1.1 Dead Weight — Tables with Zero Active Usage

The following tables have no callers in any router, service module, or CRUD function. They were built speculatively or are stubs from deferred features. Removing them before launch reduces migration surface, test maintenance, and onboarding confusion.

| Table | Reason Unused | Recommended Action |
|---|---|---|
| `StrokeClinicalContext` | Specialty table, no read/write endpoint | Remove before launch |
| `EpilepsyClinicalContext` | Specialty table, no read/write endpoint | Remove before launch |
| `ParkinsonClinicalContext` | Specialty table, no read/write endpoint | Remove before launch |
| `DementiaClinicalContext` | Specialty table, no read/write endpoint | Remove before launch |
| `HeadacheClinicalContext` | Specialty table, no read/write endpoint | Remove before launch |
| `DoctorNotifyPreference` | No endpoint in MVP routers | Remove before launch |
| `ChatArchive` | `intent_label` always NULL; no user-facing feature; PII risk (see §5) | Remove or replace with TTL-bounded log |
| `DoctorKnowledgeItem` | No doctor-initiated write endpoint exists | Remove before launch |

**Estimated removal:** ~8 tables, ~940 lines of model + migration code.

### 1.2 Over-Engineered for MVP

| Table | Issue | Recommendation |
|---|---|---|
| `SpecialtyScore` | `validation_status`, `confidence_score`, and `source` add review-workflow complexity with no UI to surface them | Strip to essential fields; re-add when validation UI ships |
| `NeuroCaseDB` | Parallel to `MedicalRecordDB` with overlapping semantics; creates dual-write confusion | Consolidate via `record_type` discriminator on `MedicalRecordDB`; deprecate `neuro_cases` |

### 1.3 Healthy / Essential Tables

The following tables are load-bearing for MVP and should not be disturbed:

`Doctor`, `Patient`, `MedicalRecordDB`, `DoctorSessionState`, `DoctorConversationTurn`, `PendingRecord`, `PendingMessage`, `DoctorTask`, `AuditLog`, `SystemPrompt` + `SystemPromptVersion`, `RuntimeCursor` / `RuntimeConfig` / `RuntimeToken`, `SchedulerLease`, `InviteCode`, `PatientLabel`, `MedicalRecordExport`, `MedicalRecordVersion`, `DoctorContext`, `NeuroCVDContext`.

### 1.4 Nothing Critically Missing for MVP

Current MVP scaffolding for rate limiting (in-memory), auth (header-based), and invite codes is sufficient for launch. No blocking gaps were identified in core transactional coverage.

---

## 2. Cross-Table Cascade Behavior

### 2.1 DELETE Doctor — Cascade Map

| Child Table | Configured Behavior | Assessment |
|---|---|---|
| `patients` | CASCADE | Correct — patients belong to a doctor |
| `medical_records` | CASCADE (via patients) | Correct |
| `doctor_tasks` | CASCADE | Correct |
| `specialty_contexts` (all 5) | CASCADE | Correct (moot if tables are removed) |
| `audit_log` | **CASCADE** | **CRITICAL — destroys compliance trail** |
| `chat_archive` | CASCADE | Contradicts "never truncated" design intent |
| `doctor_context` | No FK — **orphaned rows survive** | Add FK with CASCADE |
| `doctor_session_states` | No FK — **orphaned rows survive** | Add FK with CASCADE |
| `doctor_notify_preferences` | No FK — **orphaned rows survive** | Add FK with CASCADE (or remove table) |
| `invite_codes` | No FK — dead codes persist indefinitely | Add FK with SET NULL or CASCADE |

### 2.2 DELETE Patient — Cascade Map

| Child Table | Configured Behavior | Assessment |
|---|---|---|
| `medical_records` | CASCADE | Correct |
| `neuro_cases` | CASCADE | Correct |
| `doctor_tasks` | CASCADE | Correct |
| `pending_records` | CASCADE | Correct |
| Specialty context tables (6) | SET NULL on `patient_id`; `record_id` is CASCADE-deleted | Clinically orphaned rows: `patient_id=NULL`, referenced record gone. If tables are retained, add CASCADE on `patient_id` |
| `specialty_scores` | SET NULL on both `patient_id` AND `record_id` | Scores float without any anchor context — misleading data |

### 2.3 DELETE MedicalRecord — Cascade Map

| Child Table | Configured Behavior | Assessment |
|---|---|---|
| `medical_record_versions` | CASCADE | Correct |
| `medical_record_exports` | CASCADE | Correct |
| `specialty_scores` | CASCADE | Correct |
| Specialty context tables | CASCADE | Correct |
| `doctor_tasks` | SET NULL on `record_id` | Task survives with a stale title referencing a deleted record — acceptable if task UI handles NULL `record_id` gracefully |
| `audit_log` | Unaffected | Correct |

### 2.4 Critical Cascade Fix Required

The single highest-priority cascade change in the entire schema:

```
audit_log.doctor_id  →  ondelete="RESTRICT"
```

A doctor account should never be hard-deleted while audit records exist. Either (a) enforce `RESTRICT` and implement a soft-delete/anonymization path for doctors, or (b) set `doctor_id` to `SET NULL` on delete and add a `doctor_display_name` denormalization column so the audit trail remains readable after account removal. Option (b) is preferred for compliance.

---

## 3. Data Integrity Gaps

### 3.1 Enum-Like String Columns Without CHECK Constraints

Eighteen columns accept arbitrary strings at the database layer. The valid domain is a small closed set in every case. Any application bug or direct SQL write can silently corrupt status-machine state.

| Table | Column | Valid Values |
|---|---|---|
| `doctor_tasks` | `status` | `pending`, `completed`, `cancelled` |
| `doctor_tasks` | `task_type` | `follow_up`, `emergency`, `appointment` |
| `pending_records` | `status` | `awaiting`, `confirmed`, `abandoned`, `expired` |
| `pending_messages` | `status` | `pending`, `done` |
| `medical_records` | `record_type` | `visit`, `dictation`, `import`, `interview_summary` |
| `medical_records` | `encounter_type` | `first_visit`, `follow_up`, `unknown` |
| `audit_log` | `action` | `READ`, `WRITE`, `DELETE`, `LOGIN` |
| `audit_log` | `resource_type` | `patient`, `record`, `task` |
| `doctor_conversation_turns` | `role` | `user`, `assistant`, `system` |
| `chat_archive` | `role` | `user`, `assistant` |
| `neuro_cvd_context` | `surgery_status` | `planned`, `done`, `cancelled`, `conservative` |
| `neuro_cvd_context` | `diagnosis_subtype` | `ICH`, `SAH`, `ischemic`, `AVM`, `aneurysm`, `other` |
| `specialty_scores` | `validation_status` | `pending`, `confirmed`, `rejected` |
| `specialty_scores` | `source` | `chat`, `import`, `manual`, `voice` |
| `neuro_cvd_context` | `source` | `chat`, `import`, `manual`, `voice` |
| `medical_record_exports` | `export_format` | `pdf`, `markdown`, `docx` |
| `doctor_notify_preferences` | `notify_mode` | `auto`, `manual` |
| `doctor_notify_preferences` | `schedule_type` | `immediate`, `interval`, `cron` |

**Remediation:** Add SQLAlchemy `CheckConstraint` (rendered as SQL `CHECK` in DDL) for all columns above. For SQLite compatibility use string-literal `CHECK` expressions; for MySQL use `ENUM` type or `CHECK` (MySQL 8.0+).

### 3.2 Numeric Columns Without Range Constraints

| Table | Column | Required Range |
|---|---|---|
| `specialty_scores` | `confidence_score` | `0.0 ≤ x ≤ 1.0` |
| `dementia_clinical_context` | `mmse_score` | `0 ≤ x ≤ 30` |
| `dementia_clinical_context` | `moca_score` | `0 ≤ x ≤ 30` |
| `dementia_clinical_context` | `cdr_stage` | `{0, 0.5, 1, 2, 3}` |
| `parkinson_clinical_context` | `hoehn_yahr_stage` | `1.0 ≤ x ≤ 5.0` |
| `patients` | `year_of_birth` | `1900 ≤ x ≤ current_year` |
| `doctor_notify_preferences` | `interval_minutes` | `x > 0` |
| `neuro_cases` | `nihss` | `0 ≤ x ≤ 42` |

### 3.3 JSON Columns Without Schema Validation

The following columns accept arbitrary JSON blobs with no structural validation at any layer:

`patients.category_tags`, `medical_records.tags`, `pending_records.draft_json`, `neuro_cases.raw_json`, `neuro_cases.extraction_log_json`, `specialty_scores.details_json`, `neuro_cvd_context.raw_json`.

For MVP, application-layer Pydantic validation on ingress paths is acceptable. For production hardening, introduce a JSON Schema registry or typed columns for the most frequently read fields (e.g., `category_tags`, `tags`).

### 3.4 Cross-Table Consistency — App-Layer Only

Two consistency invariants are enforced only in application code with no DB-level guarantee:

1. **Cross-doctor data access:** A `medical_records.patient_id` can reference a patient belonging to a different `doctor_id`. No composite FK or DB constraint prevents this; the guard exists only in router-layer query filters.
2. **One pending record per doctor:** The MEMORY.md invariant ("one pending record per doctor at a time") has no `UNIQUE` constraint or serialization guarantee at the DB level. A race condition between two concurrent WeChat messages from the same doctor can create two simultaneous `pending_records` rows with `status='awaiting'`.

---

## 4. Performance & Scalability

### 4.1 Missing Indexes on Hot Query Paths

All indexes below were identified by tracing actual query patterns in CRUD and scheduler code. None are speculative.

| Missing Index | Table | Query Pattern | Impact |
|---|---|---|---|
| `(status, expires_at)` | `pending_records` | Expiry scheduler: `WHERE status='awaiting' AND expires_at < now()` runs every 5 min | Full table scan every 5 min |
| `(doctor_id, updated_at, id)` | `doctor_knowledge_items` | `list_doctor_knowledge_items()` ORDER BY | Full scan per call |
| `(record_id, doctor_id, changed_at)` | `medical_record_versions` | `get_record_versions()` | Full scan per call |
| `name` (or `name COLLATE NOCASE`) | `patients` | UI `.ilike()` name search | Full table scan on every search |
| `created_at` | `medical_records` | UI date-range filters without doctor prefix | Range scan degrades at scale |
| `(record_id, exported_at)` | `medical_record_exports` | Audit/tamper detection queries | Full scan per record |
| `(doctor_id, score_type, extracted_at)` | `specialty_scores` | Score history queries | Full scan per doctor |

### 4.2 Unbounded Table Growth — No Retention Policy

| Table | Growth Rate (5K doctors, moderate use) | Risk |
|---|---|---|
| `chat_archive` | ~9M rows/year at 5 msgs/day/doctor | Unbounded PII storage; query latency degrades |
| `audit_log` | Up to 91M rows/year at scale | Storage and query cost at scale |
| `pending_records` | Low volume, but PII retained after `status='expired'` | PII lingers indefinitely; no hard-delete |
| `medical_record_versions` | One row per edit event, full content copy | Storage grows linearly with edit activity |

**Recommended retention policies:**

- `chat_archive`: Hard-delete rows older than 90 days (or remove table entirely — see §1).
- `audit_log`: Partition by month; archive to cold storage after 12 months. Do not delete.
- `pending_records`: Hard-delete rows with `status IN ('confirmed','abandoned','expired')` older than 30 days via the existing APScheduler job.
- `medical_record_versions`: Keep last N versions per record (e.g., 20); archive older versions to a separate cold table.

### 4.3 Audit Log Write Contention

The current pattern fires one async `INSERT` per audit action, each with its own `commit()`. Under concurrent WeChat message bursts this creates per-action write contention on SQLite (serialized writes) and unnecessary round-trips on MySQL.

**Recommendation:** Buffer audit writes in a bounded async queue (drain every 5 seconds or 100 entries, whichever comes first). This is consistent with the existing async write queue in `observability.py`.

### 4.4 Admin Endpoint Pagination

The admin table endpoint permits `limit=5000` on append-only tables. At the growth rates in §4.2 this will return multi-MB JSON payloads.

**Recommendation:** Cap `limit` at 500; enforce cursor-based pagination (keyset on `id` or `created_at`) rather than offset pagination, which degrades as `OFFSET` grows.

### 4.5 Unbounded In-Memory Cache

`_DOCTOR_CACHE` in `routers/wechat.py` is a module-level `dict` with no eviction policy. In a long-running process with a large number of unique `open_id` values this will grow without bound.

**Recommendation:** Replace with an LRU cache (`functools.lru_cache` or `cachetools.TTLCache`) capped at a reasonable size (e.g., 2000 entries, 1-hour TTL).

---

## 5. Security & Compliance

### 5.1 Critical

**Audit trail erasable on doctor delete.**
`audit_log.doctor_id` is `ondelete=CASCADE`. A single `DELETE FROM doctors WHERE id=X` silently destroys every compliance record for that doctor. Change to `ondelete=RESTRICT` with a mandatory anonymization workflow, or to `SET NULL` with a `doctor_display_name` denormalization column (see §2.4).

**READ operations produce no audit log entries.**
Patient list, patient detail, and medical record view endpoints do not call `audit()`. Any regulatory audit of the system will find no evidence of who accessed which patient record and when. Add `audit(doctor_id, "READ", "patient", patient_id)` and `audit(doctor_id, "READ", "record", record_id)` to all view paths.

### 5.2 High

**PII in conversation logs with no TTL.**
Patient names, clinical content, and draft records appear in plaintext in `chat_archive` and `doctor_conversation_turns`. There is no pseudonymization, no TTL, and no purge mechanism. At minimum, add a retention TTL (90 days recommended) enforced by the APScheduler job; consider pseudonymizing patient identifiers at write time.

**`pending_records` and `pending_messages` retain PII after expiry.**
Rows are marked `expired`/`done` but never hard-deleted. Draft clinical content (including patient names and symptom text in `draft_json`) persists indefinitely. Add hard-delete to the existing `_expire_stale_pending_records` scheduler job for rows older than 30 days.

**`InviteCode.code` is stored plaintext with no expiry or use limits.**
The code namespace is enumerable. There is no `expires_at`, no `max_uses`, and no rate limiting on the login endpoint.

**Missing audit entries for key state transitions.**
The following actions are not logged:
- `pending_record` state change: `awaiting → confirmed`, `awaiting → abandoned`
- `MedicalRecordExport` creation (no `action="EXPORT"` entry)
- Patient label create/delete/assign

### 5.3 Medium

**Doctor isolation is app-layer only.**
No DB row-level security or composite FK prevents cross-doctor data leakage. A bug in any router query filter exposes all patients to any authenticated doctor. For a medical records system, this is a meaningful architectural risk even before formal compliance requirements apply.

**Plaintext identity fields.**
`Doctor.wechat_user_id` and `Doctor.mini_openid` are stored plaintext. These are low-entropy identifiers that could be used to correlate with external WeChat user data. Consider HMAC-hashing at rest if the application never needs to reverse-look up by raw value (it typically does not — lookups are always by the hashed value).

**`MedicalRecordVersion.old_content` stores full plaintext history indefinitely.**
Every edit to a medical record appends a full plaintext copy. There is no version cap and no encryption. This is the highest-volume PII accumulator in the schema after `chat_archive`.

**No soft-delete grace period.**
Hard-delete on patient and record with no `deleted_at` + grace-period makes accidental deletion by a doctor unrecoverable without a DB-level backup restore.

### 5.4 Low

- `Patient.name` has no `CHECK(TRIM(name) != '')` — empty string names are valid.
- `chat_archive` is queryable via the admin UI with no additional authorization tier beyond the admin session.
- Label operations (create, delete, assign) are not audited.

---

## 6. Consolidated Action Plan

Items are ordered within each priority tier by estimated impact.

### Priority Definitions

| Priority | Meaning |
|---|---|
| **P0** | Must fix before MVP launch — data loss, compliance blocker, or silent data corruption |
| **P1** | Fix in first two sprints post-launch — performance or security risk under real load |
| **P2** | Fix within 60 days — code hygiene, operational readiness, secondary integrity |
| **P3** | Backlog — nice-to-have, addressable when related features ship |

### P0 — Pre-Launch Blockers

| # | Item | Affected Tables | Effort |
|---|---|---|---|
| P0-1 | Change `audit_log.doctor_id` from `CASCADE` to `RESTRICT` (or `SET NULL` + denormalize `doctor_display_name`) | `audit_log` | S |
| P0-2 | Add `audit()` calls to all READ paths (patient list, patient detail, record view) | `audit_log`, routers | M |
| P0-3 | Add `UNIQUE` partial index on `pending_records(doctor_id)` WHERE `status='awaiting'` to enforce one-pending-per-doctor invariant at DB level | `pending_records` | S |
| P0-4 | Add composite index on `pending_records(status, expires_at)` — scheduler hot path | `pending_records` | S |
| P0-5 | Add CHECK constraints on the 5 most critical status-machine columns: `pending_records.status`, `pending_messages.status`, `medical_records.record_type`, `doctor_tasks.status`, `audit_log.action` | Multiple | M |
| P0-6 | Remove or add TTL to `ChatArchive` table — plaintext PII with no retention bound | `chat_archive` | S |
| P0-7 | Add `audit()` calls for `pending_record` state transitions (confirm, abandon) and `MedicalRecordExport` creation | `audit_log`, services | S |

### P1 — First Two Sprints Post-Launch

| # | Item | Affected Tables | Effort |
|---|---|---|---|
| P1-1 | Remove 8 dead tables and their Alembic migrations (5 specialty contexts, `DoctorNotifyPreference`, `DoctorKnowledgeItem`, `ChatArchive`) | Multiple | M |
| P1-2 | Hard-delete expired/done rows from `pending_records` and `pending_messages` in the APScheduler job (30-day retention) | `pending_records`, `pending_messages` | S |
| P1-3 | Add `expires_at`, `max_uses`, and `used_count` to `InviteCode`; add rate limiting to the login endpoint | `invite_codes` | M |
| P1-4 | Add missing indexes: `patients(name)`, `medical_records(created_at)`, `medical_record_versions(record_id, changed_at)`, `medical_record_exports(record_id, exported_at)`, `specialty_scores(doctor_id, score_type, extracted_at)` | Multiple | S |
| P1-5 | Fix orphaned-row FKs: add FK on `doctor_context.doctor_id`, `doctor_session_states.doctor_id`, `invite_codes.doctor_id` with appropriate `ondelete` | Multiple | S |
| P1-6 | Replace `_DOCTOR_CACHE` in `wechat.py` with a bounded LRU/TTL cache | `routers/wechat.py` | S |
| P1-7 | Cap admin endpoint `limit` at 500; enforce keyset pagination on append-only tables | Admin routers | S |

### P2 — Within 60 Days

| # | Item | Affected Tables | Effort |
|---|---|---|---|
| P2-1 | Buffer audit log writes in async queue (drain every 5s or 100 entries) — reduce write contention | `audit_log`, `services/audit.py` | M |
| P2-2 | Add CHECK constraints on remaining 13 enum-like string columns (see §3.1 table) | Multiple | M |
| P2-3 | Add numeric range CHECK constraints (confidence_score, mmse/moca/cdr, year_of_birth, nihss) | Multiple | S |
| P2-4 | Add retention policy job for `audit_log` (archive rows > 12 months to cold storage) and `medical_record_versions` (cap to last 20 per record) | `audit_log`, `medical_record_versions` | M |
| P2-5 | Add `deleted_at` soft-delete grace period to `patients` and `medical_records` (7-day window) | `patients`, `medical_records` | M |
| P2-6 | Add audit entries for label create/delete/assign operations | `audit_log`, label CRUD | S |
| P2-7 | Evaluate `NeuroCaseDB` vs `MedicalRecordDB` consolidation; produce a migration plan using `record_type` discriminator | `neuro_cases`, `medical_records` | L |
| P2-8 | Add `CHECK(TRIM(name) != '')` on `patients.name` | `patients` | S |

### P3 — Backlog

| # | Item | Affected Tables | Effort |
|---|---|---|---|
| P3-1 | HMAC-hash `Doctor.wechat_user_id` and `Doctor.mini_openid` at rest | `doctors` | M |
| P3-2 | Introduce JSON Schema validation for `draft_json`, `category_tags`, `tags` at Pydantic ingress layer | Multiple | M |
| P3-3 | Evaluate row-level security (application-layer composite FK guard or DB-level policy) for cross-doctor isolation | `medical_records`, `patients` | L |
| P3-4 | Strip `SpecialtyScore` to essential fields only; add validation UI before re-adding `validation_status`/`confidence_score` | `specialty_scores` | S |
| P3-5 | Pseudonymize patient identifiers in `doctor_conversation_turns` at write time (store patient_id reference, not name) | `doctor_conversation_turns` | L |
| P3-6 | Add additional authorization tier (separate admin role check) for `chat_archive` queries in admin UI | Admin routers | S |

---

## Appendix: Agent Coverage Summary

| Agent | Focus Area | Tables Reviewed | Critical Findings |
|---|---|---|---|
| Agent 1 | MVP Completeness | All 30+ tables | 8 dead tables, NeuroCaseDB duplication |
| Agent 2 | Cascade Interactions | All FK relationships | `audit_log` CASCADE, 4 orphaned FK paths |
| Agent 3 | Data Integrity | All column constraints | 18 unconstrained enums, 8 numeric ranges, cross-doctor gap |
| Agent 4 | Performance & Scalability | Query paths, index coverage | 7 missing indexes, 4 unbounded tables, cache leak |
| Agent 5 | Security & Compliance | Access logging, PII storage | No READ audit, erasable trail, indefinite PII retention |

---

*This report was generated from automated schema analysis. All findings reference model definitions as of `db/models.py` at commit `2071fad`. Remediation estimates (S/M/L) assume a single senior engineer with full codebase context: S ≤ 2h, M = 2–8h, L > 1 day.*
