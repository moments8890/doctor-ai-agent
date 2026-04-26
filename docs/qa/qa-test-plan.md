# QA Test Plan — Doctor AI Agent

Comprehensive test scenarios organized by pipeline. Each section lists the
happy-path flows, edge cases, and what to verify.

**Last reference run:** 2026-04-08 (hero-path run — see `hero-path-qa-plan.md`)
**Known open bugs:** BUG-01 (date display), BUG-02 (greeting suffix), BUG-03 (intake send, real-device only), BUG-05 (edit button order), BUG-06 (NL search), BUG-07 (logout back nav)
**Pre-flight requirement:** Backend must start with `NO_PROXY=* no_proxy=*` prefix or all LLM calls fail silently (BUG-04 — not yet permanently fixed in code)

---

## 1. Knowledge Creation Pipeline

Tests the full lifecycle of doctor knowledge: create, import, edit, delete.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 1.1 | Add knowledge manually | 我的AI → 我的知识库 → add text entry | Item appears in list, title/summary auto-generated |
| 1.2 | Upload PDF → extract → save | Knowledge page → upload PDF → review extracted text → save | Extracted text is meaningful, item saved with source=file |
| 1.3 | Upload image → OCR → save | Knowledge page → upload image → review OCR result → save | Text extracted from image, saved as knowledge item |
| 1.4 | Fetch URL → extract → save | Knowledge page → paste URL → extract → save | URL content fetched, key facts extracted, source_url stored |
| 1.5 | Edit existing knowledge | Click knowledge item → edit text → save | Updated text persists, title/summary updated |
| 1.6 | Delete knowledge item | Click delete on item → confirm | Item removed from list and no longer cited in future suggestions |
| 1.7 | Category assignment | Add item with specific category (diagnosis, treatment, etc.) | Category saved and displayed correctly |
| 1.8 | Reference count | Create knowledge → use in diagnosis → check count | reference_count increments when cited in AI suggestions |

**Edge cases:**
- Content length limit: 3000 characters max (enforced server-side)
- File upload size limit: 10MB max for knowledge uploads
- Very large PDF (50+ pages)
- Non-Chinese language document
- Corrupted/password-protected PDF
- Empty text submission
- Duplicate content
- Special characters in title

---

## 2. Diagnosis Pipeline

Tests AI diagnosis generation, suggestion review, and record finalization.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 2.1 | Trigger diagnosis | Chat creates record → click 诊断 button | 202 accepted, async polling starts, suggestions appear |
| 2.2 | Confirm suggestion | Review page → click confirm on a suggestion | Decision = confirmed, timestamp recorded |
| 2.3 | Remove/unconfirm suggestion | Review page → expand suggestion (▾) → tap 移除 | Item returns to dimmed/unconfirmed state; **not deleted** from list; 确认 option reappears |
| 2.4 | Edit suggestion | Review page → edit text → save | edited_text stored, original preserved, decision = edited |
| 2.5 | Add custom suggestion | Review page → add manual suggestion | New suggestion with is_custom=true appears in list |
| 2.6 | Finalize review (partial decisions) | Decide some suggestions → finalize | Record status → completed even without all decisions (no gate) |
| 2.7 | Finalize side effects | Finalize review | Tasks auto-generated from treatment plan, draft message created |
| 2.8 | KB citation display | Trigger diagnosis with knowledge items | [KB-N] references resolved to knowledge titles in UI |
| 2.9 | Urgency levels | Diagnosis with urgent findings | 紧急 badge displayed, sorted to top |

**Edge cases:**
- Diagnosis on record with minimal data (only chief complaint)
- Diagnosis failure / LLM timeout → status = diagnosis_failed
- Re-diagnose same record after initial diagnosis
- Record with no structured fields (legacy unstructured content)
- Concurrent diagnosis requests on same record (duplicate suggestion risk from fire-and-forget)

---

## 3. Doctor Intake / Record Creation

Tests the doctor-side structured intake flow — the primary data-entry path
for creating medical records.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 3.1 | Start new intake | 新建病历 → select patient or create new | Intake chat starts, first question from AI |
| 3.2 | Multi-turn data entry | Answer AI questions about symptoms, history, etc. | AI asks relevant follow-ups, builds structured record |
| 3.3 | Voice input during intake | Tap mic → speak → AI processes | Audio transcribed, treated as intake answer |
| 3.4 | Image/file import mid-intake | Upload image or file during intake | Content extracted and incorporated into record fields |
| 3.5 | Carry-forward from previous records | Start intake for returning patient | Previous record data pre-populated / referenced |
| 3.6 | Edit fields mid-intake | Correct a field during intake | Field updated, AI adjusts subsequent questions |
| 3.7 | Confirm and save | Review structured fields → confirm | Record created with status = pending_review |
| 3.8 | Cancel mid-intake | Abandon intake before confirm | Partial data handled gracefully (not saved as record) |

**Edge cases:**
- Intake with no prior patient records (cold start)
- Very long free-text answers
- Switching patients mid-intake
- Network interruption during multi-turn conversation
- File upload size limit: 20MB max for chat/intake uploads

---

## 4. New Patient Pipeline

Tests patient creation from various entry points.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 4.1 | Create from chat | Chat "新建患者 张三 男 45岁" | Patient created, appears in patient list |
| 4.2 | Create from onboarding | Onboarding wizard → demo patient step | Patient created with QR code, portal URL generated |
| 4.3 | Generate QR code | Patient detail → generate pre-intake code | QR code displayed, scannable, has expiry |
| 4.4 | Patient appears in list | Create patient → go to 患者 tab | Patient in alphabetical group, shows gender/age |
| 4.5 | Patient detail view | Click patient → view detail | Timeline, records, messages displayed correctly |

**Edge cases:**
- Duplicate patient name
- Missing required fields (name)
- Special characters / very long names
- Create patient with only partial info
- Patient with no records (empty timeline)

---

## 5. Patient Intake Pipeline (Patient-Facing)

Tests the patient-facing pre-visit intake flow.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 5.1 | Start intake via QR | Patient scans QR → lands on intake page | Intake starts, first question displayed |
| 5.2 | Answer questions | Patient types answers → AI asks follow-ups | Clarifying questions are relevant, conversation flows |
| 5.3 | Submit intake | Patient confirms all answers → submit | Structured record created for doctor, status = pending_review |
| 5.4 | Doctor sees result | Doctor opens patient → view intake record | Structured fields populated (chief complaint, history, etc.) |

**Edge cases:**
- Patient abandons mid-intake (partial data saved?)
- Very long patient answers (>2000 chars)
- Intake session timeout / token expiry
- Patient re-starts intake after submission
- Multiple patients using same QR code simultaneously

---

## 6. Patient Portal & AI Triage (Safety-Critical)

Tests the patient portal chat with AI triage classification. This is
safety-critical: misclassification could suppress urgent clinical content.

### 6a. Triage Classification

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 6a.1 | Informational message | Patient asks general question (e.g. "什么时候复诊") | AI answers directly, no escalation to doctor |
| 6a.2 | Symptom report | Patient reports new symptom | Escalated to doctor with structured summary, draft created |
| 6a.3 | Side effect report | Patient reports medication side effect | Escalated to doctor, triage = side_effect |
| 6a.4 | Urgent message | Patient reports chest pain / emergency symptoms | Immediate safety guidance shown + doctor notification sent |
| 6a.5 | General question (ambiguous) | Patient sends unclear message | Safe default: escalated to doctor (not auto-handled) |

### 6b. Patient Portal Features

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 6b.1 | Patient login | Scan QR / enter access code | Session established, portal loads |
| 6b.2 | Patient registration | Self-register via phone | Account created, linked to doctor |
| 6b.3 | View own records | Patient → records tab | Read-only view of shared records |
| 6b.4 | View follow-up tasks | Patient → tasks tab | Assigned tasks with due dates shown |
| 6b.5 | Complete a task | Mark task as done | Status updated, reflected on doctor side |
| 6b.6 | Chat with doctor | Send message via `POST /api/patient/chat` with `{"text":"..."}` (NOT `/api/patient/message` — that endpoint saves but does NOT generate AI draft) | Message appears in doctor's 审核 → 待回复 queue with "AI已起草" label within ~15s |
| 6b.7 | Mark message as read | Open received message | Read status updated |
| 6b.8 | File upload | Upload image/PDF in chat | File processed, attached to message |

**Edge cases:**
- Expired access code / token
- Legacy patient without access code (deprecated login by name)
- PBKDF2 hash verification timing-attack resistance
- Access code rotation (old JWT invalidated)
- Rate limit: 5/min on patient session, 10/min on patient chat
- Patient upload size limits

---

## 7. Draft & Reply Pipeline

Tests AI draft generation, editing, sending, and the teaching loop.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 7.1 | Auto-generated draft | Patient sends message via `POST /api/patient/chat` → wait ~15s → check **审核 → 待回复** tab | Draft card appears with patient name, "AI已起草" label, triage category |
| 7.2 | View draft content | Click draft card → expand | Shows patient message, AI reply, knowledge citations |
| 7.3 | Edit draft | Click edit → modify text → save | Status changes to "edited", edited text persisted |
| 7.4 | Send with confirmation | Tap 确认发送 › → confirmation sheet slides up | Sheet titled "确认发送回复"; shows patient's original message + reply text; "AI辅助生成，经医生审核" attribution; 取消 LEFT / 发送 RIGHT |
| 7.5 | Send draft | Tap 发送 in confirmation sheet | Message delivered to patient; chat view shows green sent bubble with attribution; item moves to 已完成 |
| 7.6 | Confirm draft chat URL | After sending, note current URL | Doctor chat view is at `/doctor/patients/<id>?view=chat` |
| 7.7 | Save as rule (teaching) | Edit draft significantly → "save as rule" prompt | DoctorEdit logged, new knowledge item created from edit |
| 7.8 | Decline teaching prompt | Edit draft → decline "save as rule" | No knowledge item created, edit still saved |
| 7.9 | Draft from patient message | Patient sends message → AI auto-drafts reply | Draft appears in pending list with source message context |
| 7.10 | Undrafted escalated messages | Patient message escalated but no draft generated | Appears as type="undrafted" in draft list, actionable |

**Edge cases:**
- Send without editing (direct send)
- Multiple pending drafts for same patient
- Draft for deleted patient
- Very long draft text
- Teaching prompt threshold (should_prompt_teaching check)
- Draft status = "stale" — when/how does this trigger?
- Draft expiration behavior

---

## 8. Task / Follow-up Pipeline

Tests task creation, status management, and notifications.

Status enum: `pending` → `notified` → `completed` | `cancelled`
(No `in_progress` status exists.)

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 8.1 | Auto-generated tasks | Finalize record with treatment plan | Tasks created from orders/follow-up items |
| 8.2 | Create manual task | 任务 tab → create new → fill fields | Task appears in pending list |
| 8.3 | Complete task | Click task → mark completed | Status = completed, timestamp recorded |
| 8.4 | Cancel task | Click task → cancel | Status = cancelled, removed from active list |
| 8.5 | Task with due date | Create task with future due date | Due date displayed, overdue styling when past |
| 8.6 | Task badges | Tasks exist → check patient card badges | Badge count matches pending tasks |
| 8.7 | Filter by status | Switch between pending/completed/cancelled tabs | Correct tasks shown per filter |
| 8.8 | Task detail view | Click task → view detail | Notes, linked record, postpone option visible |
| 8.9 | Task target | Create doctor-target vs patient-target task | Correct target shown, patient tasks visible in patient portal |

**Edge cases:**
- Task without assigned patient
- Task with past due date at creation
- Overdue task display
- 50+ tasks in list (pagination/scroll)
- Task target: doctor vs patient behavior differences
- Allowed status transitions: only `completed` and `cancelled` via PATCH

---

## 9. Chat / AI Conversation Pipeline

> **Note (2026-04-08):** The doctor workbench no longer has an embedded chat input on the main 我的AI tab. The workbench uses a dashboard model with quick action cards (新建病历, 患者预问诊码) and an AI activity feed. Chat interaction happens via the doctor-side intake flow (§3), not a standalone chat composer. Tests 9.1–9.4 apply to those entry points; 9.8–9.9 apply to the 我的AI activity feed.

Tests the core AI chat interaction.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 9.1 | Basic text chat | Type message → send | AI responds with relevant content |
| 9.2 | Image upload + OCR | Attach image → send | AI extracts text, includes in response |
| 9.3 | PDF upload | Attach PDF → send | Extracted content returned, usable in conversation |
| 9.4 | Voice input | Tap mic → record → send | Audio transcribed, treated as text message |
| 9.5 | Action hints | Use quick action buttons | Correct action_hint sent, AI responds accordingly |
| 9.6 | Structured record in response | Chat about patient → AI creates record | Record card displayed inline with structured fields |
| 9.7 | Navigate to patient from chat | AI mentions patient → click link | Navigates to patient detail page |
| 9.8 | AI activity feed | Check 我的AI tab activity section | Shows "按你的方法处理了 N 位患者", recent AI actions |
| 9.9 | AI-flagged patients | Check flagged patients list | Patients needing attention (due tasks, unread escalations, unreviewed suggestions) |

**Edge cases:**
- Very long message (8000 char limit)
- Rapid successive messages
- Rate limiting: 100/min for doctor UI operations (429 response)
- Empty message send attempt
- Chat history > 100 turns
- LLM timeout / failure → graceful fallback message
- Unsupported file format upload
- Audio transcription: 50MB max file size

---

## 10. Patient Management

Tests the patient list, search, and detail views.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 10.1 | View patient list | 患者 tab | Alphabetical grouping, gender/age/chief complaint shown |
| 10.2 | Text search | Type patient name in search bar | Filtered results match query |
| 10.3 | Natural language search | Search "女性中年患者" | AI extracts criteria, returns matching patients |
| 10.4 | Filter by category | Select needs_action / follow_up filter | Correct patients per category |
| 10.5 | Patient detail | Click patient → view detail | Timeline, bio, records, messages all present |
| 10.6 | Patient timeline | Scroll through timeline | Events in chronological order, correct types |
| 10.7 | Delete patient | Admin → delete → confirm | Patient and all related data cascade deleted |

**Edge cases:**
- Empty patient list (empty state shown)
- 100+ patients (scroll performance)
- NL search with no matches
- Patient with no records
- Search with special characters

---

## 11. Review Queue (审核 tab)

Tests the centralized suggestion review interface.
API returns three sections: `summary`, `pending`, `completed`.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 11.1 | View queue | 审核 tab | Three sub-tabs: **待审核 / 待回复 / 已完成**; summary badge counts correct |
| 11.2 | Navigate to record | Tap patient card in 待审核 | Navigates to `/doctor/review/<id>`; "诊断审核" header; three suggestion sections: 鉴别诊断 / 检查建议 / 治疗方向 |
| 11.3 | Summary counts | Review queue header | Pending/confirmed/modified counts all accurate |
| 11.4 | Completed tab | Tap 已完成 | Shows decided records with decision type and timestamps |
| 11.5 | Urgency badge | Urgent record | Red "紧急" badge visible on card; sorted to top of 待审核 list |
| 11.6 | Badge updates | Decide suggestion → return to queue | Badge count decrements |

**Edge cases:**
- Empty queue (empty state)
- 50+ pending items (scroll/pagination)
- Stale queue (suggestions decided in another tab)

---

## 12. Record Edit, Delete & Versioning

Tests append-only record editing and deletion.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 12.1 | Edit existing record | Open record → edit fields → save | New row created with version_of pointing to original |
| 12.2 | View version history | Open edited record → check versions | Original and edited versions both visible |
| 12.3 | Delete record | Delete record → confirm | Record removed, cascade deletes suggestions and tasks |

**Edge cases:**
- Edit record with existing suggestions (do suggestions carry over?)
- Multiple edits (version chain)
- Delete versioned record (cascade to all versions?)

---

## 13. Medical Record Import

Tests importing records from external files (separate from knowledge upload).

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 13.1 | Import from image | Upload medical record image | OCR extracts text, creates intake session |
| 13.2 | Import from PDF | Upload medical record PDF | Text extracted, structured fields parsed |
| 13.3 | Import from text | Paste medical record text | text_to_intake creates structured record |

**Edge cases:**
- Partially legible image
- Multi-page PDF with mixed content
- Text with non-standard field names

---

## 14. Daily Briefing

Tests the briefing endpoint that surfaces daily cards.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 14.1 | Overdue tasks card | Have overdue tasks → check briefing | Card shows overdue count with action buttons |
| 14.2 | Completed today card | Complete tasks → check briefing | Today's completed items listed |
| 14.3 | Today's patients card | Have patients with activity → check briefing | Relevant patients surfaced |
| 14.4 | Card actions | Click complete/postpone/view on briefing card | Action executes correctly |

**Edge cases:**
- No activity (empty briefing)
- Many overdue items
- Briefing across timezone boundaries

---

## 15. Auth & Access Control

Tests login, registration, session management, and data isolation.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 15.1 | Doctor login | UI: 昵称 (phone number) + 口令 (year of birth as integer) → 登录 | JWT issued; redirected to `/doctor`; 我的AI tab active. Note: UI labels say 昵称/口令 but API fields are `phone`/`year_of_birth` |
| 15.2 | Invite code registration | Tap "医生注册" on login page → enter 昵称 + 口令 + invite code (e.g. WELCOME) | Doctor account created; onboarding wizard starts |
| 15.3 | Dual-role phone login | Phone matches both doctor and patient | `needs_role_selection: true` returned, role picker shown |
| 15.4 | Data isolation (UI) | Login as doctor A → navigate to patients/records | Only own data visible |
| 15.5 | Data isolation (API) | `GET /api/manage/drafts?doctor_id=<doctor_B_id>` with doctor A's JWT | 403 or 404 returned — not doctor B's data |
| 15.6 | Session expiry | Wait for token expiry / manually expire | Redirect to login with appropriate message |
| 15.7 | QR login | Generate QR → scan → login | Token absorbed from URL, session established |
| 15.8 | WeChat token handoff | Open app with ?token=...&doctor_id=...&name=... in URL | Token absorbed, session established from URL params |

**Edge cases:**
- Wrong credentials (phone or year)
- Expired invite code
- Multi-use invite code (creates fresh doctor per login)
- Concurrent sessions from two devices
- Dev mode synthetic tokens (dev-token, mock-token)

---

## 16. Admin Panel

Tests admin-only management features.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 16.1 | Admin login | Admin credentials → login | Admin dashboard loads |
| 16.2 | System overview | Admin → overview | Total doctors, patients, records, daily metrics |
| 16.3 | Doctor list | Admin → doctors | All doctors with activity stats |
| 16.4 | Doctor detail | Click doctor → view detail | Patient list, timeline, activity for that doctor |
| 16.5 | Create invite code | Admin → invite codes → create | Code generated with expiry and max uses |
| 16.6 | Revoke invite code | Delete existing invite code | Code no longer usable for registration |
| 16.7 | Data cleanup preview | Admin → cleanup → preview | Shows what would be deleted, counts |
| 16.8 | Data cleanup execute | Admin → cleanup → execute with confirmation | Test/demo data removed, production data preserved |
| 16.9 | Raw data viewer | Admin → raw data | Database records viewable for debugging |
| 16.10 | System config | Admin → config → update | Config applied to running system |

**Edge cases:**
- Non-admin user accessing admin endpoints (auth check)
- Cleanup accidentally hitting production data
- Config change breaking running system
- Admin token (X-Admin-Token header) validation

---

## 17. Onboarding Wizard

Tests the guided setup experience for new doctors.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 17.1 | Full walkthrough | Step through all onboarding steps | Profile set, knowledge intro shown, demo data created |
| 17.2 | Demo patient | Onboarding creates demo patient + QR | Patient visible in list, QR scannable |
| 17.3 | Skip onboarding | Click skip | Redirected to main app, onboarded flag set |
| 17.4 | Example data | Onboarding creates example diagnosis/draft/tasks | Demo records marked with seed_source tag |

**Edge cases:**
- Re-run onboarding (idempotent? duplicates?)
- Onboarding with pre-existing data
- Interrupt mid-onboarding

---

## 18. Settings & Profile

Tests doctor profile management.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 18.1 | Update name | Settings → profile → change name | Name persists, shown in header |
| 18.2 | Set specialty | Add/change specialty | Saved, may affect AI behavior |
| 18.3 | Set clinic name | Add/change clinic_name | Saved and displayed |
| 18.4 | Set bio | Add/change bio | Saved and displayed |
| 18.5 | Logout | Settings → logout | Session cleared, redirect to login |

**Edge cases:**
- Empty required name field
- Very long name / specialty / bio text
- Profile fields missing in older DB (graceful fallback)

---

## 19. Record Export Pipeline

Tests PDF/report generation and bulk export.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 19.1 | Single patient PDF | Patient detail → export PDF | PDF downloads, content matches record |
| 19.2 | Outpatient report | Export as outpatient report format | Professional formatting, all fields present |
| 19.3 | Bulk export ZIP | Select multiple → bulk export | ZIP downloads with individual PDFs |
| 19.4 | Export integrity | Check SHA256 hash in exported PDF | Hash verifiable |

**Edge cases:**
- Export record with missing fields
- Very long records (10+ pages)
- Export for patient with no records
- Special characters in patient name (filename safety)

---

## 20. Navigation & UI Polish

Tests transitions, badges, responsive layout, and component conventions.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 20.1 | Tab switching | Click each of the 4 bottom tabs (我的AI / 患者 / 审核 / 任务) | Fade transition (150ms), correct content |
| 20.2 | Subpage navigation | Enter subpage → back | Slide transition (300ms), back works |
| 20.3 | Badge counts | Create data → check tab badges | Counts update in real-time |
| 20.4 | Responsive layout | Resize viewport (mobile/tablet/desktop) | Layout adapts, no overflow |
| 20.5 | Dialog conventions | Trigger any confirm dialog | Cancel LEFT gray, primary RIGHT green |
| 20.6 | Danger dialog | Trigger delete confirmation | Same layout, primary button red |
| 20.7 | Loading states | Navigate to data-heavy page | Skeleton loaders shown (not spinners) |
| 20.8 | Empty states | View list with no items | EmptyState component shown (not plain text) |
| 20.9 | Browser back button | Navigate deep → press back | Returns to previous page correctly |
| 20.10 | Privacy page | Navigate to privacy policy | Content displays correctly |

---

## 21. Cross-cutting Concerns

Tests that apply across all features.

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 21.1 | Rate limiting (doctor) | Send rapid API requests | 429 at 100/min for UI, user-friendly message |
| 21.2 | Rate limiting (patient) | Rapid patient session/chat requests | 429 at 5/min session, 10/min chat |
| 21.3 | Network failure | Disconnect network → try action | Error state shown, no crash |
| 21.4 | Console errors | Navigate all pages | No JS exceptions in console |
| 21.5 | API errors | Trigger 404/422/500 | Graceful error display, not raw JSON |
| 21.6 | Concurrent tabs | Open app in two tabs as same doctor | No state corruption |
| 21.7 | LLM failure fallback | LLM returns error/timeout | Neutral error message, app doesn't crash |

---

## Priority Order

For systematic QA, test in this order (safety-critical and gating items first):

1. **Auth & Access** (15) — gates everything else
2. **Admin Panel** (16) — invite codes gate doctor registration
3. **Knowledge Creation** (1) — foundation for AI quality
4. **Doctor Intake / Record Creation** (3) — primary data entry path
5. **Diagnosis Pipeline** (2) — core product loop
6. **Patient Portal & AI Triage** (6) — safety-critical triage classification
7. **Draft & Reply** (7) — core communication loop
8. **Task / Follow-up** (8) — follow-up workflow
9. **Patient Management** (10) — daily workflow
10. **New Patient** (4) — onboarding flow
11. **Chat / AI** (9) — primary interaction surface
12. **Review Queue** (11) — management interface
13. **Record Edit & Versioning** (12) — data integrity
14. **Patient Intake** (5) — patient-facing
15. **Daily Briefing** (14) — dashboard utility
16. **Medical Record Import** (13) — utility
17. **Navigation & UI** (20) — polish
18. **Cross-cutting** (21) — resilience
19. **Onboarding** (17) — first-time experience
20. **Settings** (18) — low risk
21. **Export** (19) — utility feature
