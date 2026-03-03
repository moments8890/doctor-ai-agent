# Specialist AI Agent — Next Feature Priorities

## Objective
Translate the feasibility report into an implementation-ready feature backlog focused on specialist-doctor workflow value.

## P0 (Build Next)
1. Risk-driven triage engine
- Classify incoming signals into low/medium/high risk.
- Route to auto-reply, doctor-review draft, or urgent doctor alert.

2. Timeline-centered patient workspace
- Longitudinal view of visits, labs, meds, alerts, tasks, and communication history.
- Highlight missed follow-ups and unresolved high-risk items.

3. Follow-up orchestration
- Rule-based recheck reminders and overdue escalation.
- Priority support for chronic disease, post-op, and emergency follow-up paths.

4. Doctor approval workflow for AI outputs
- AI suggestion -> doctor confirm/edit -> final write-back.
- Mandatory approval gate for high-impact outputs.

## P1 (Expand)
5. Multimodal structured ingestion hardening
- Stabilize speech/text/message ingestion and schema extraction.
- Ensure robust extraction for diagnosis, meds, labs, vitals, plans, and adverse events.

6. Communication load reduction layer
- Low-risk: automated response.
- Medium-risk: AI draft for doctor approval.
- High-risk: direct escalation to doctor queue.

7. Clinical decision-support triggers
- Trigger concise guideline/research prompts at key disease milestones.
- Include source/version tags for traceability.

8. Medication safety and adverse-event module
- Detect refill requests, dose changes, suspected adverse reactions, and contraindication cues.
- Auto-create review tasks for doctor confirmation.

## P2 (Scale and Moat)
9. Doctor feedback-to-model loop
- Capture doctor edits/rejections.
- Continuously improve routing, extraction, and draft quality.

10. Research-ready structured data layer
- Cohort/query/export for outcomes and longitudinal analysis.
- De-identification and auditability for compliant secondary use.

## Suggested Success Metrics
- Time saved per clinician per day.
- Follow-up completion rate and overdue reduction.
- High-risk signal response time.
- Auto-handled low-risk message ratio.
- Doctor edit rate on AI drafts (should decrease over time).
