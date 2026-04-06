"""Agent package — prompt composer, LLM calls, and types.

The Plan-and-Act routing layer (handle_turn, router, dispatcher, handlers)
has been removed. Core flows use domain functions directly:
  - Doctor interview: domain.patients.interview_turn
  - Patient interview: domain.patients.interview_turn
  - Diagnosis: domain.diagnosis_pipeline
  - Follow-up reply: domain.patient_lifecycle.draft_reply
"""
