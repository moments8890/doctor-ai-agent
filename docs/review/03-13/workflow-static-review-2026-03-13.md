# Workflow Static Review - 2026-03-13

Date: 2026-03-13

Scope: Consolidated static code review of the current doctor workflow, channel routers, stateful prechecks, intent workflow, persistence boundaries, read models, auth surfaces, background jobs, provider integrations, and prompt/configuration paths.

Method: Repository-only review. No runtime validation, no integration replay, and no tests were run.

## Executive Summary

The core 5-layer workflow is directionally correct, but the system still has too many edge-specific branches where channel adapters, legacy paths, persistence helpers, and admin/config surfaces override or bypass the intended source of truth.

The main recurring risk themes are:

- write safety that depends on reply-string heuristics or partially broken confirm/save boundaries
- stale or spoofable context influencing patient binding and downstream writes
- auth and admin surfaces that trust caller-controlled identity or expose sensitive/expensive operations too broadly
- read/export/admin models that drift from the write-side source of truth
- legacy WeChat and fast-router behavior that still sits beside, not fully inside, the new workflow

## Verified Correction

One earlier concern was rechecked and is not a runtime bug: shared dispatch does handle `export_records`, `export_outpatient_report`, and `import_history`. The stale artifact is the comment/docstring in `services/domain/intent_handlers/_dispatch.py`, not the executable path.

## 1. Channel Workflow Boundaries

Key files: `routers/records.py`, `routers/voice.py`, `routers/wechat.py`, `services/intent_workflow/gate.py`, `services/intent_workflow/precheck.py`, `services/domain/intent_handlers/_add_record.py`

- Medium: the `no_patient_name` gate is not authoritative. Web, voice, and WeChat continue for that failure reason, and `handle_add_record()` can still auto-bind a single patient and create a draft.
- Medium: the voice path drops the stale-draft abandonment branch from `run_stateful_prechecks()`. Users do not see the abandonment notice, and the rerouted turn also misses knowledge loading that normally happens after precheck completion.

## 2. Legacy WeChat Sync Path

Key files: `routers/wechat.py`, `routers/wechat_flows.py`, `services/intent_workflow/precheck.py`, `services/domain/intent_handlers/_create_patient.py`

- High: the legacy sync create-patient path can create a literal patient named `__pending__` because it bypasses the precheck sentinel handling and treats the placeholder as a real name.
- Medium: sync pending-record rerouting uses less context than the normal WeChat workflow, so identical follow-up text can classify differently depending on which path handled it.
- Medium: stateful WeChat turns handled synchronously are not persisted into conversation history, so later fallback resolution and compression do not see those replies.

## 3. Classify -> Extract -> Bind

Key files: `services/intent_workflow/models.py`, `services/intent_workflow/entities.py`, `services/intent_workflow/binder.py`, `services/intent_workflow/gate.py`, `services/domain/intent_handlers/_create_patient.py`, `services/domain/intent_handlers/_simple_intents.py`, `services/ai/turn_context.py`

- High: `create_patient` can silently inherit a previous patient name from history or session instead of asking for one.
- High: `delete_patient` and `update_patient` can also inherit stale patient context, and the gate does not stop those operations once a name is present.
- Medium: the advertised turn-context snapshot contract is only partial. Classification uses the snapshotted turn context, but later extraction and binding still read live session state and caller/history fallbacks.

## 4. Planner/Gate -> Shared Dispatch

Key files: `services/intent_workflow/planner.py`, `services/domain/intent_handlers/_dispatch.py`, `services/domain/intent_handlers/_create_patient.py`, `services/domain/intent_handlers/_add_record.py`, `services/notify/tasks.py`

- High: compound `create_patient + add_record` can continue into record creation even when patient creation never actually succeeded, because dispatch treats non-warning replies as success.
- High: add-record reminder compounds can create a task even when the record branch failed or blocked, including under an unassociated patient label.
- Medium: reminder tasks created from `add_record` compounds are not patient-linked, unlike the create-patient reminder path, so the same planner behavior yields different downstream task semantics.

## 5. Pending Confirm / Persistence Boundary

Key files: `services/domain/intent_handlers/_confirm_pending.py`, `db/crud/pending.py`, `db/crud/records.py`, `db/crud/specialty.py`, `routers/ui/admin_table_rows.py`, `db/models/pending.py`

- High: pending-record confirmation is broken at the service boundary because `_persist_pending_record()` passes `commit=False` into `confirm_pending_record()`, which does not accept that parameter. The generic failure wrapper can also mask partial persistence when auto follow-up creation commits underneath.
- Medium: inline CVD context restore from the pending draft is broken for the same reason: `save_cvd_context(..., commit=False)` does not match the CRUD signature, and the exception is swallowed.
- Medium: one confirmed record can create duplicate follow-up tasks when `AUTO_FOLLOWUP_TASKS_ENABLED=true` because both the save path and confirm-time side effects can enqueue them.
- Medium: `PendingRecord.raw_input` is schema drift. Confirm-time logic and admin views read it, but the model and baseline schema do not define it, and draft creation never stores it.

## 6. Pending Messages and Session Persistence

Key files: `routers/wechat.py`, `db/crud/pending.py`, `services/session.py`, `db/models/pending.py`, `main.py`

- High: `PendingMessage` recovery is effectively disabled for many failures because rows are marked `done` in `finally` before outbound delivery is confirmed.
- High: queued conversation turns can be permanently lost on DB write failure because `_flush_pending_turns()` clears the in-memory batch before the write and does not re-queue it on error.
- Medium: session-state persistence can miss the latest mutation because only one persist task may exist at a time, with no dirty-bit or follow-up flush.
- Medium: startup stale-message recovery is not claim-based, so multi-instance startup can replay the same pending message more than once.

## 7. Knowledge and Memory Context

Key files: `services/ai/turn_context.py`, `services/intent_workflow/classifier.py`, `services/intent_workflow/workflow.py`, `services/ai/agent.py`, `services/knowledge/doctor_knowledge.py`, `routers/records.py`, `routers/voice.py`, `routers/wechat.py`

- High: compressed long-term memory is only actually injected on WeChat. Web and voice load it but do not feed it into routing.
- Medium: `DoctorTurnContext.advisory.knowledge_snippet` is dead state. Routers populate it, but the workflow and classifier ignore it in favor of a separate `knowledge_context` parameter.
- Medium: `knowledge_used` provenance is non-functional. The field is exposed and logged, but no caller updates it, so observability reports no knowledge usage even when snippets were injected.
- Medium: the knowledge retriever guarantees at least one item even on query misses, so unrelated knowledge can still be injected into prompts and bias routing.

## 8. Cross-Channel Session/History Model

Key files: `routers/records.py`, `routers/voice.py`, `services/domain/adapters/web_adapter.py`, `services/domain/name_utils.py`, `services/intent_workflow/entities.py`, `services/domain/intent_handlers/_add_record.py`, `services/intent_workflow/precheck.py`, `services/session.py`, `routers/wechat.py`

- High: web and voice trust caller-supplied history as authoritative routing context, so a client can steer patient attribution with fabricated prior turns.
- High: that same untrusted history is persisted into blocked-write continuation state and replayed on a later turn, extending the impact beyond the original request.
- Medium: the server already has an authoritative recent-history model, but only WeChat uses it end to end. Web and voice still depend on caller-supplied history and do not push turns back.

## 9. Legacy Routing Beside the New Workflow

Key files: `routers/wechat_flows.py`, `utils/text_parsing.py`, `services/domain/intent_handlers/_add_record.py`, `services/ai/intent.py`, `services/ai/router.py`, `services/domain/chat_handlers.py`

- High: WeChat still has a live legacy rerouter after the 5-layer workflow for `Intent.unknown`, and it can turn an unknown result into a write path by synthesizing `add_record`.
- Medium: WeChat also keeps an ad hoc `name_lookup` intent family outside the formal intent model, so an `unknown` result can still mutate patient/session state.
- Medium: the repo still carries an orphaned pre-workflow routing stack in `services/ai/router.py` and `services/domain/chat_handlers.py` whose behavior has already drifted from the shared handlers. Reusing it would reintroduce old logic.

## 10. Specialty and Auxiliary Side Effects

Key files: `services/domain/intent_handlers/_add_record.py`, `services/ai/structuring.py`, `services/patient/score_extraction.py`, `services/domain/intent_handlers/_simple_intents.py`, `services/notify/tasks.py`, `services/domain/intent_handlers/_confirm_pending.py`, `services/notify/task_rules.py`

- High: the post-structuring score pass can overwrite or erase scores that the main structuring model already extracted, and its supported score set is narrower.
- Medium: standalone `schedule_follow_up` writes `record_id=0` into a nullable foreign key, which is a phantom record reference rather than a safe null.
- Medium: confirm-time auto-task timing is globally reapplied to every detected task type, so one time phrase in the note can shift unrelated tasks away from their defaults.
- Medium: fallback CVD extraction is case-sensitive, so lower-case English neurovascular notes can silently miss background extraction.

## 11. Readback, Query, Export, and Report Generation

Key files: `services/export/outpatient_report.py`, `db/models/records.py`, `services/domain/intent_handlers/_query_records.py`, `services/patient/prior_visit.py`, `services/export/pdf_export.py`, `db/crud/scores.py`, `services/wechat/wechat_export.py`

- High: outpatient-report generation throws away stored structured data and re-derives the report from concatenated free text only, so the read path can contradict persisted write-side data.
- High: persisted specialty scores are effectively invisible in the doctor-facing readback surfaces reviewed here. Query, summary, PDF export, and outpatient-report generation mostly ignore them.
- Medium: the same records PDF renderer is populated inconsistently by channel, so exports differ materially depending on whether the request came from web or WeChat.
- Medium: WeChat's text fallback after PDF export failure shows the oldest 10 records rather than the most recent 10.

## 12. Admin/UI Read Models

Key files: `routers/ui/__init__.py`, `routers/ui/admin_table_rows.py`, `routers/ui/admin_handlers.py`, `services/session.py`, `services/intent_workflow/precheck.py`, `db/models/pending.py`, `db/models/doctor.py`

- High: sensitive admin reads are only partially audited. Raw patient/record views are available without a corresponding audit trail, and pending tables exposing draft/raw content are excluded from the sensitive-audit allowlist.
- Medium: filtered admin counts are not trustworthy for several operational tables because some count helpers ignore the same filters that the row views apply.
- Medium: the workbench header ignores blocked-write continuation state, so it can tell the user the wrong next step while the workflow is actually waiting for a patient-name reply.
- Medium: admin operational tables hide fields the runtime uses for recovery, such as `PendingMessage.attempt_count` and persisted `blocked_write_json`.

## 13. /api/manage/* Read Models

Key files: `routers/ui/record_handlers.py`, `routers/miniprogram.py`, `db/crud/records.py`, `db/crud/patient.py`, `db/repositories/patients.py`, `services/patient/patient_categorization.py`, `routers/ui/__init__.py`

- High: record-management views filter after a pre-limited fetch, so older matching records disappear and the reported total is only the size of the truncated slice.
- High: grouped patient lists and legacy offset pagination still have a hidden 200-patient ceiling because they use `get_all_patients()` with the repository default limit.
- Medium: patient category/grouped views are stale by design because time-based categories are persisted at write time and not refreshed on reads.
- Medium: natural-language patient search silently truncates to 20 rows and reports that cap as the total count.

## 14. Patient Portal and Mini-Program Surfaces

Key files: `routers/patient_portal.py`, `utils/runtime_config.py`, `main.py`, `db/crud/patient.py`, `routers/miniprogram.py`, `routers/records.py`, `db/crud/doctor.py`, `services/auth/rate_limit.py`

- High: the patient-portal JWT secret can silently fall back to a hardcoded dev value when deployment config uses the project's normal runtime-config path but does not set `APP_ENV=production`.
- High: legacy patients can still log in with name only if `access_code` is null, and there is no exposed product path to migrate them off that mode.
- Medium: rotating a patient access code does not revoke existing patient sessions because portal JWTs are not tied to the current code hash or a token version.
- Medium: mini-program chat duplicates conversation-turn persistence on the normal workflow path, which can distort later history use.
- Medium: patient-portal messaging is unthrottled and directly fans out doctor notifications, so any valid patient token can spam the notification path.

## 15. Authentication and Identity Linking

Key files: `routers/auth.py`, `services/auth/request_auth.py`, `routers/ui/_utils.py`, `routers/records.py`, `db/models/doctor.py`, `routers/ui/invite_handlers.py`

- High: `/api/auth/web/login` is an unauthenticated token mint for any `doctor_id`, and downstream routers treat those tokens as authoritative for doctor-scoped access.
- High: the invite-code model advertises expiry and usage limits, but the login and admin flows do not enforce or even surface those fields meaningfully.
- Medium: `DELETE /api/auth/mini-link` does not actually sever mini-app identity for standalone `wxmini_*` doctors because later lookup can still re-find the same row by `wechat_user_id`.
- Medium: mini mock-code login is a real auth bypass toggle with no built-in production hard-stop beyond the environment flag itself.

## 16. Non-Chat REST Surfaces

Key files: `routers/tasks.py`, `db/crud/tasks.py`, `db/repositories/tasks.py`, `db/models/tasks.py`, `main.py`, `routers/records.py`, `services/notify/tasks.py`

- High: task creation accepts arbitrary `patient_id` without verifying that the patient belongs to the authenticated doctor, enabling cross-linked task creation if a foreign patient ID is known.
- High: mounted media helper endpoints for OCR, transcription, and file extraction expose expensive AI work with no auth and no rate limiting, and some read the full upload into memory first.
- Medium: the dev notifier endpoint is unauthenticated and can trigger global due-task processing when enabled.
- Medium: `/api/tasks` paginates after loading the full task set into memory, so each paginated request becomes a full fetch.

## 17. Background Jobs and Fire-and-Forget Workers

Key files: `main.py`, `services/domain/intent_handlers/_confirm_pending.py`, `db/crud/pending.py`, `services/notify/tasks.py`, `db/crud/tasks.py`, `services/observability/audit.py`, `routers/export.py`, `services/wechat/wechat_export.py`

- High: the stale-draft autosave scheduler can save the same expired pending record repeatedly because confirm-time state transition logic does not actually claim stale rows before saving.
- High: task notification delivery is send-first and mark-later, so a DB failure after a successful external send causes duplicate reminders on the next scheduler cycle.
- Medium: the audit background worker permanently drops events on transient DB write failure because it never re-queues failed batches.
- Medium: several export flows enqueue a successful `EXPORT` audit before generation, upload, or delivery has actually succeeded.

## 18. LLM/Provider Boundary

Key files: `main.py`, `services/ai/llm_client.py`, `services/ai/agent.py`, `services/ai/structuring.py`, `services/ai/vision.py`, `services/ai/neuro_structuring.py`, `services/ai/transcription.py`, `services/knowledge/pdf_extract_llm.py`, `utils/runtime_config.py`, `utils/log.py`

- High: the startup Ollama failover path is mostly non-functional for live callers because provider config and long-lived clients are already cached against the original endpoint.
- High: OCR, ASR, and PDF extraction log clinical text previews to disk by default, which is PHI leakage into operational logs.
- Medium: hot-applying runtime config does not hot-reload the LLM clients, so endpoint/model/timeout changes can remain ineffective until restart.
- Medium: the PDF vision extractor does not honor the local fallback path when the provider raises, so `extract-file` can return 500 instead of using the available local extractor.
- Medium: the degraded ASR path drops the medical/consultation prompt entirely when it falls back away from local `faster-whisper`.

## 19. Prompt and Configuration Layer

Key files: `utils/prompt_loader.py`, `db/init_db.py`, `db/crud/system.py`, `routers/ui/__init__.py`, `routers/ui/admin_config.py`, `services/intent_workflow/classifier.py`, `services/ai/fast_router/_router.py`, `services/ai/memory.py`, `services/export/outpatient_report.py`

- High: startup prompt seeding overwrites admin-edited prompts on every boot for at least `structuring` and `structuring.neuro_cvd`, and the overwrite bypasses prompt version history.
- Medium: prompt lookup silently falls back to hardcoded defaults after transient DB read failure and then caches that fallback for 60 seconds.
- Medium: admin-edited template prompts are not validated against required format placeholders, so a bad prompt edit can break runtime memory compression or outpatient-report generation.
- Medium: fast-router admin and observability surfaces are out of sync with the live routing path. Metrics re-run fast routing without session state, and exposed admin keyword buckets do not fully match the rules that production routing actually uses.

## 20. Remaining Prompt Consumers and AI Utility Layer

Key files: `services/wechat/wechat_import.py`, `routers/neuro.py`, `services/ai/neuro_structuring.py`, `services/domain/intent_handlers/_simple_intents.py`, `services/domain/intent_handlers/_confirm_pending.py`, `db/crud/records.py`, `services/wechat/patient_pipeline.py`, `services/patient/score_extraction.py`, `services/ai/memory.py`

- High: `import_history` is still a prompt-driven bulk write path outside draft-first confirmation and can persist multiple records directly, including unassociated records.
- High: `/api/neuro/from-text` bypasses the 5-layer workflow entirely and also discards part of its own prompt output (`cvd_ctx`) before persistence.
- High: saved-record correction can report success even when no correction was extracted or applied, because the fallback extractor can yield an empty update set and the handler still returns a success message.
- Medium: auxiliary prompt consumers such as patient-facing chat and specialty score extraction do not share the main provider/fallback stack, so runtime behavior diverges by feature.
- Medium: memory compression can silently drop older unsummarized context after transient failures once the rolling buffer exceeds its fallback cap.

## 21. Benchmark, Debug, and Evaluation Harness

Key files: `scripts/benchmark_gate.sh`, `scripts/test.sh`, `scripts/run_chatlog_e2e.py`, `tests/integration/conftest.py`, `tests/integration/test_text_pipeline.py`, `tests/integration/test_data_integrity_e2e.py`, `tests/integration/test_realworld_doctor_agent_e2e.py`, `tests/integration/test_neuro_cases_table_e2e.py`, `db/models/medical_record.py`, `db/models/records.py`

- High: the benchmark gate can compare a stale `reports/candidate/hero.json`, and its "unit-test" step is now effectively a no-op.
- High: a large part of the integration/E2E suite is still pinned to the removed 8-field record schema and a deleted `neuro_cases` table, so those tests no longer represent the shipped product.
- High: the chatlog replay benchmark can turn an original failure into a reported pass by injecting a synthetic rescue turn that was never in the source conversation.
- Medium: one replay safety check (`expect_no_aggressive_treatment`) is effectively dead against the current record schema because it still inspects `treatment_plan`.
- Medium: the integration helper claims to mirror real clients but still exercises a dev-only auth shape by posting `doctor_id` in the request body without production-style bearer auth.

## 22. Fixture Generation and Rule-Mining Toolchain

Key files: `scripts/mine_routing_rules.py`, `scripts/validate_routing_rules.py`, `scripts/expand_clinical_keywords.py`, `scripts/mine_local_datasets.py`, `scripts/train_tier3_classifier.py`, `services/ai/fast_router/_router.py`, `services/ai/fast_router/_tier3.py`, `services/ai/fast_router/_mined_rules.py`, `tests/fixtures/scripts/patch_v2_assertions.py`

- High: the keyword-expansion utilities still hardcode the deleted monolithic `services/ai/fast_router.py` path and do not target the live `_keywords.py` artifact.
- High: `train_tier3_classifier.py` still trains and writes a model for a Tier-3 route that the codebase now explicitly marks as inactive in production.
- Medium: the mined-rule pipeline now produces artifacts outside the canonical fast-routing path, even though the loader and test plumbing still exist.
- Medium: rule mining and validation are text-only, while the live fast router is session-aware, so the reported precision/recall is not production-representative.
- Medium: the fixture toolchain includes in-place expectation-rewrite scripts that can retune benchmark cases offline rather than regenerating them from runtime behavior.

## 23. Seeding, Cleanup, and Local Data Utilities

Key files: `scripts/seed_db.py`, `scripts/seed_mock_data.py`, `scripts/cleanup_inttest_data.py`, `tests/integration/conftest.py`, `db/models/records.py`, `db/models/doctor.py`, `db/models/pending.py`, `db/models/tasks.py`, `routers/patient_portal.py`

- High: `seed_db.py` import logic and the bundled `seed_data.json` fixture are still on the removed record schema, so record import is broken on current databases.
- High: `cleanup_inttest_data.py` and the mirrored integration-suite cleanup still target stale tables and miss current persisted conversation/archive state, so cancelled test runs can leak debris across sessions.
- Medium: `seed_db.py --reset` is no longer a real clean-environment reset because it leaves doctor-scoped workflow state, pending rows, tasks, and chat history behind.
- Medium: `seed_mock_data.py` seeds patients without portal access codes, and the current patient portal still allows name-only login for such rows.

## Cross-Cutting Priorities

If this review is used to prioritize fixes, the first pass should focus on:

1. auth and access control gaps that allow broad doctor impersonation or unauthenticated compute use
2. pending-confirm and autosave bugs that can fail closed for the user while still partially persisting data
3. stale or spoofable context paths that can bind writes to the wrong patient
4. legacy WeChat and fallback branches that still bypass the intended workflow source of truth
5. read/export/admin drift where doctor-facing outputs no longer reflect the structured data already stored by the write path
6. benchmark and developer-tooling drift where fixtures, mining scripts, and reset/cleanup utilities no longer match the live schema and routing contract

## Review Status

This document reflects the final reviewed findings as of 2026-03-13, including the correction that shared dispatch already handles export/import intents at runtime.
