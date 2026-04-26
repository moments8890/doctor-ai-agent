"""Agent package — prompt composer, LLM calls, and types.

The Plan-and-Act routing layer (handle_turn, router, dispatcher, handlers)
has been removed. Core flows use domain functions directly:
  - Doctor intake: domain.patients.intake_turn
  - Patient intake: domain.patients.intake_turn
  - Diagnosis: domain.diagnosis_pipeline
  - Follow-up reply: domain.patient_lifecycle.draft_reply
"""
