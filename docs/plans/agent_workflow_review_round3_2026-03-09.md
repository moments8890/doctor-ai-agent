# Doctor AI Agent — Round 3 Review (Post Round 2 Fixes)

**Date:** 2026-03-09
**Scope:** Full agent pipeline re-review after Round 2 fixes
**Reviewers:** 5 domain reviews: WeChat Pipeline (R1), LLM Dispatch (R2), Resilience (R3), DB Layer (R4), Fast Router (R5)

---

## 1. Executive Summary

Round 2 fixes addressed all previously-known issues. This review surfaced new findings — several critical bugs that were either introduced by the fixes or were previously hidden. The most urgent are a **P0 argument-order crash** in `handle_pending_create`, a **P0 MySQL migration crash** in migration 0017, and **P0 silent degradation** when the cloud LLM fallback times out.

**Domain scores:**

| Domain | Score | Reviewer |
|---|---|---|
| WeChat Pipeline & SLA | 6.5/10 | R1 |
| LLM Dispatch & Prompts | 6.0/10 | R2 |
| Resilience & Error Handling | 5.5/10 | R3 |
| DB Layer & Migrations | 7.5/10 | R4 |
| Fast Router & Clinical Coverage | 6.0/10 | R5 |

---

## 2. P0 Issues — Fix Before Next Deploy

### P0-A: `handle_pending_create` passes arguments in wrong order
**Files:** `services/wechat/wechat_domain.py:630`
**Reviews:** R1 (BUG-1), R5 (BUG-01)

```python
# CURRENT (broken)
return await handle_add_record(doctor_id, fake_intent, text)

# Signature: handle_add_record(text: str, doctor_id: str, intent_result: IntentResult, ...)
# FIX
return await handle_add_record(text, doctor_id, fake_intent)
```

Triggered whenever a doctor sends clinical content while in `pending_create` state. At runtime, `doctor_id` (a string) is treated as `text`, `fake_intent` (an `IntentResult`) is treated as `doctor_id`, causing `get_session(fake_intent)` to raise `AttributeError`. The entire `pending_create` → clinical-note auto-complete path is broken in production.

---

### P0-B: Migration 0017 crashes on MySQL (sqlite_master query)
**File:** `alembic/versions/0017_pending_records_compound_index.py:25–30`
**Review:** R4

`_index_exists()` queries `sqlite_master`, which does not exist in MySQL. The migration crashes at deploy time on the production server. Migration 0016 correctly uses `inspect(conn).get_indexes(table)`. Fix:

```python
def _index_exists(conn, table: str, index_name: str) -> bool:
    from sqlalchemy import inspect as _inspect
    existing = {idx["name"] for idx in _inspect(conn).get_indexes(table)}
    return index_name in existing
```

---

### P0-C: `_follow_up_hint` operator precedence — task created with `content="True"`
**File:** `services/wechat/wechat_domain.py:316`
**Reviews:** R1 (BUG-6), R5 (BUG-02)

```python
# CURRENT (broken)
("随访" in record.content or "复诊" in record.content and record.content or None)
# Python parses as: ("随访" in content) or (("复诊" in content) and content) or None
# → When only "随访" matches: evaluates to boolean True → task created with content="True"

# FIX
(("随访" in record.content or "复诊" in record.content) and record.content) or None
```

Every record mentioning "随访" (but not "复诊") creates a follow-up task with `content="True"` — a corrupted task title silently propagated in production.

---

### P0-D: Cloud fallback `asyncio.TimeoutError` silently degrades to regex
**File:** `services/ai/agent.py:1059`, `services/ai/structuring.py:245`
**Review:** R3 (BUG-1, BUG-2)

In `agent.py`: `asyncio.TimeoutError` from `asyncio.wait_for(3.0s)` is a subclass of `Exception` (Python 3.11+) and is caught by `except Exception` at line 1059, silently triggering regex fallback. Cloud infrastructure failure is invisible in metrics and the doctor gets a degraded response with no circuit breaker increment on the cloud path.

In `structuring.py`: there is **no** `except` around the `asyncio.wait_for(...)` call. `TimeoutError` propagates raw through `wechat_domain.py`'s generic `except Exception` and silently discards the medical record.

**Fix:** Catch `asyncio.TimeoutError` explicitly in both files and re-raise (or handle it as a distinct failure mode distinct from LLM errors):

```python
# agent.py: inside the cloud fallback block
try:
    _cloud_timeout = float(os.environ.get("AGENT_CLOUD_FALLBACK_TIMEOUT", "3.0"))
    completion = await asyncio.wait_for(
        call_with_retry_and_fallback(..., circuit_key_suffix=doctor_id or ""),
        timeout=_cloud_timeout,
    )
except asyncio.TimeoutError:
    log(f"[Agent] cloud fallback timed out after {_cloud_timeout}s")
    raise  # let outer except Exception handle it with correct attribution
```

---

### P0-E: `_summarise` JSON validation is decorative — garbage stored as context
**File:** `services/ai/memory.py:97–108`
**Review:** R2 (P0-1)

Both the `try` and `except` branches of the JSON validation block unconditionally fall through to `return raw`. If the LLM returns a plain sentence or malformed JSON, it is stored unchanged in `doctor_contexts`. On the next session, `load_context_message` injects the garbage directly into the system prompt. Fix: raise (or return a sentinel) when compression output is unparseable so `maybe_compress` can skip the clear-and-persist step.

---

## 3. P1 Issues

### P1-A: Primary Ollama path missing `circuit_key_suffix=doctor_id`
**Files:** `services/ai/agent.py:1020`, `services/ai/memory.py:87`, `services/ai/structuring.py:215`
**Reviews:** R3 (BUG-3), R2 (P1-1)

`circuit_key_suffix=doctor_id` is only applied to the cloud fallback call. The primary path shares one circuit breaker across all doctors. One doctor's repeated Ollama failures (e.g., sending huge inputs the model rejects) opens the circuit and denies routing for all other doctors for the 60s cooldown. Same problem in `memory.py` and `structuring.py`.

---

### P1-B: Startup recovery has no retry cap — poison messages loop forever
**File:** `routers/wechat.py:1332`
**Review:** R3 (BUG-4)

`recover_stale_pending_messages` re-enqueues all pending messages on every restart with no attempt counter or dead-letter state. A message that crashes `_handle_intent_bg` repeatedly is re-enqueued on every deploy. Fix: add an `attempt_count` column to `PendingMessage`; mark as `"dead"` after N failures.

---

### P1-C: Voice messages never persisted to `PendingMessage` — durable guarantee absent
**File:** `routers/wechat.py:895–897`
**Review:** R3 (BUG-5)

`_handle_voice_bg` is called without a `msg_id`. The `finally` block at line 1151 guards with `if msg_id:` and always skips. Voice messages receive no durable-inbox protection: if the server dies during transcription the message is lost with no recovery path.

---

### P1-D: `confirm_pending_record` / `abandon_pending_record` accept `doctor_id=None`
**File:** `db/crud/pending.py:61–86`
**Review:** R4

Both functions silently skip the `doctor_id` filter when `None` is passed, allowing cross-doctor record access. `doctor_id` should be a required non-optional parameter.

---

### P1-E: Patient name regex rejects legitimate patients
**File:** `services/ai/agent.py:67, 104, 193, ...` (all 9 `patient_name` fields)
**Review:** R2 (P1-2)

`^[\\u4e00-\\u9fff]{2,5}$` rejects:
- Single-character nicknames (minimum 2 chars blocks "王" etc.)
- Non-CJK names (foreign patients, ethnic minorities using Latin/other script)
- Rare CJK characters outside the base block (Extension A/B)
- The `delete_patient` tool has no pattern constraint at all — inconsistent with the 9 other tools

---

### P1-F: `add_cvd_record` never offered when specialty is unset
**File:** `services/ai/agent.py:995–1003`
**Review:** R5 (BUG-04)

The CVD tool is gated behind specialty matching. A neurosurgeon who hasn't configured specialty in the DB never receives structured CVD extraction — their ICH/SAH notes are routed through `add_medical_record` losing GCS/Hunt-Hess/Fisher scores silently.

---

### P1-G: `export_outpatient_report` intent has no LLM tool
**File:** `services/ai/agent.py` (`_TOOLS`, `_INTENT_MAP`)
**Review:** R5 (BUG-05)

The intent exists in the enum and fast_router, but no corresponding LLM tool is defined. LLM-fallback paths for export-related queries have no structured tool to call.

---

### P1-H: `handle_add_record` fast-path now adds a DB round-trip on every hit
**File:** `services/wechat/wechat_domain.py:134–148`
**Reviews:** R1, R5 (BUG-06)

The Round 2 fix added a `get_patient_for_doctor()` call inside the fast-path to guard against multi-device renames. This fires on **every** `add_record` call where the patient name matches the session (the majority case). The "fast path" now does the same number of DB queries as the normal path, with extra overhead from the two separate `AsyncSessionLocal` scopes. Consider trusting the session cache and only invalidating on explicit rename events.

---

### P1-I: `CancelledError` bypasses `mark_pending_message_done`
**File:** `routers/wechat.py:1082–1093`
**Review:** R1 (BUG-2)

`asyncio.CancelledError` (a `BaseException`) propagates past both `except` handlers and bypasses the `msg_id` marking block. On deploy restart, the unfinished message is re-queued and the doctor receives a duplicate reply. Fix: wrap the `msg_id` marking in a `finally` at the outermost function level.

---

## 4. P2 Issues

| ID | File | Description |
|---|---|---|
| P2-A | `structuring.py:195–196` | `prior_visit_summary` injected into user-role message; `[:500]` label is insufficient structural isolation against directive injection from stored records |
| P2-B | `agent.py:967–969` | `doctor_name` injected into system prompt without stripping embedded newlines (`\n` within name can inject directives) |
| P2-C | `memory.py:146–148` | Hard-cap at `MAX_TURNS*3` (30 msgs) but compression triggers at `MAX_TURNS*2` (20 msgs) — 50% unchecked growth after first failure |
| P2-D | `memory.py:87–93` | `maybe_compress` runs inside session lock and can trigger a full LLM round-trip (2–5s), consuming the majority of the 4.5s outer budget before intent routing begins |
| P2-E | All `DateTime` columns | `DateTime` without `timezone=True`; on MySQL all reads return naive datetimes requiring `.replace(tzinfo=utc)` workarounds everywhere — fragile, any new comparison site will raise `TypeError` in Python 3.12+ |
| P2-F | `agent.py` all tool defs | `gender` field lacks `enum: ["男","女"]` — any string passes schema validation |
| P2-G | `wechat_domain.py:530` | Interview escape word set too narrow — `"停止"`,`"不要了"`,`"终止"`,`"算了"`,`"stop"` not recognized; off-topic doctor messages recorded as interview answers |
| P2-H | `encounter_detection.py:32` | `"复查"` alone forces `follow_up` even for new patients with no prior records — wastes an async DB call on `_get_prior()` |
| P2-I | `db/models/pending.py:29` | `ix_pending_records_doctor_status` is a strict prefix of `ix_pending_records_doctor_status_expires` — 2-col index now redundant, wastes write amplification |
| P2-J | `wechat.py:259` | `datetime.utcnow()` deprecated since Python 3.12; creates naive datetime in `runtime_cursors.updated_at` |

---

## 5. P3 Issues

| ID | File | Description |
|---|---|---|
| P3-A | `session.py:167–170` | Hydration failure stamps full 300s TTL — 5 min of empty-session serving after any DB blip |
| P3-B | `wechat.py:1287–1307` | Direct XML WeChat path handles stateful flows without per-doctor session lock |
| P3-C | `fast_router/_tier3.py` | Common clinical phrases (`"血压正常"`, `"出院"`, `"病情稳定"`, `"手术顺利"`) not in keyword set → unnecessary LLM calls |
| P3-D | `fast_router/_tier3.py:164` | `specialty` parameter in `_is_clinical_tier3` is reserved but unused |
| P3-E | `llm_resilience.py:31–44` | `_failure_threshold()` and `_cooldown_seconds()` read env vars on every hot-path call |
| P3-F | `wechat.py:1332` | Recovered messages lack `open_kfid`; customer profile enrichment skipped on recovery |
| P3-G | `retention.py:83` | Docstring says "redact" but does UPDATE not DELETE; future auditors may misinterpret |
| P3-H | `fast_router/_router.py:460` | `fast_route_label` calls `fast_route` without session context — metrics undercount session-chain hits |
| P3-I | `db/crud/patient.py:148,187,214,251,273` | `import asyncio` repeated inline at 5 call sites instead of module-level |

---

## 6. Consolidated Priority Matrix

| Priority | Count | Must fix before… |
|---|---|---|
| P0 | 5 | Any production deploy |
| P1 | 9 | Next sprint |
| P2 | 10 | Sprint after next |
| P3 | 9 | Backlog |

**Estimated effort for P0 fixes:** ~4 hours total
- P0-A (arg order): 5 min
- P0-B (migration MySQL): 30 min
- P0-C (operator precedence): 5 min
- P0-D (TimeoutError propagation): 1 hour
- P0-E (_summarise validation): 1 hour
