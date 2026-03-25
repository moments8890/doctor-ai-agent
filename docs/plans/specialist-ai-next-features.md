# Specialist AI Agent — Next Feature Priorities

## Objective
Translate the feasibility report into an implementation-ready feature backlog focused on specialist-doctor workflow value.

## P0 (Build Next)

1. Doctor approval workflow for AI outputs
- AI suggestion → doctor confirm/edit → final write-back.
- Mandatory approval gate for high-impact outputs (record writes, task creation, medication flags).
- **Blocks all other P0 items** — AI output must be gated before expanding scope.

2. Risk-driven triage engine
- Classify incoming signals into low/medium/high risk.
- Route to auto-reply, doctor-review draft, or urgent doctor alert.

3. Multimodal structured ingestion hardening
- Stabilize speech/text/message ingestion and schema extraction (voice and WeChat pipelines exist but need reliability work before clinical use).
- Ensure robust extraction for diagnosis, meds, labs, vitals, plans, and adverse events.

4. Audit trail
- Log every AI output, doctor edit, approval, and rejection with actor + timestamp.
- Required for clinical compliance before any multi-user or production deployment.

5. Timeline-centered patient workspace
- Longitudinal view of visits, labs, meds, alerts, tasks, and communication history.
- Highlight missed follow-ups and unresolved high-risk items.

6. Follow-up orchestration
- Rule-based recheck reminders and overdue escalation.
- Priority support for chronic disease, post-op, and emergency follow-up paths.

## P1 (Expand)

7. Multi-doctor access control
- Role-based access: attending, resident, nurse, admin.
- Patient data ownership and per-doctor view isolation.
- Required before scaling beyond a single-doctor setup.

8. Communication load reduction layer
- Extends existing intent routing with tiered handling: low-risk auto-reply, medium-risk AI draft for approval, high-risk direct escalation to doctor queue.
- Distinct from current routing: adds the approval step and escalation path.

9. Clinical decision-support triggers
- Trigger concise guideline/research prompts at key disease milestones.
- Include source/version tags for traceability.

10. Medication safety and adverse-event module
- Detect refill requests, dose changes, suspected adverse reactions, and contraindication cues.
- Auto-create review tasks for doctor confirmation.

## P2 (Scale and Moat)

11. Doctor feedback-to-model loop
- Capture doctor edits/rejections from day one (audit trail in P0 provides the data foundation).
- Use collected signal to improve routing, extraction, and draft quality continuously.

12. Research-ready structured data layer
- Cohort/query/export for outcomes and longitudinal analysis.
- De-identification and auditability for compliant secondary use.

## Suggested Success Metrics
- Time saved per clinician per day.
- Follow-up completion rate and overdue reduction.
- High-risk signal response time.
- Auto-handled low-risk message ratio.
- Doctor edit rate on AI drafts (should decrease over time).
- Audit log coverage: 100% of AI-generated outputs traceable to a doctor action.
