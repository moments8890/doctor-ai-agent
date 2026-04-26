"""Scenario test runner — in-process, fixture-driven, traces every step.

Executes YAML scenario fixtures by calling agent functions directly
(intake_start, intake_turn, intake_confirm, diagnosis) without
an HTTP server.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Ensure src/ is importable
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ROUTING_LLM", "groq")

# Load runtime config and set env vars for LLM clients
try:
    from utils.app_config import load_config_from_json
    _, _values = load_config_from_json()
    for key in ["GROQ_API_KEY", "DEEPSEEK_API_KEY", "ROUTING_LLM", "STRUCTURING_LLM",
                 "OLLAMA_BASE_URL", "OLLAMA_API_KEY"]:
        val = _values.get(key, "")
        if val and not os.environ.get(key):
            os.environ[key] = val
except Exception:
    pass


def load_fixture(path: str) -> Dict[str, Any]:
    """Load a YAML scenario fixture."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class ScenarioWorld:
    """Isolated test namespace with unique doctor/patient IDs."""

    def __init__(self, fixture: Dict[str, Any]):
        self.fixture = fixture
        self.doctor_id = f"scenario_{fixture['id']}_{uuid.uuid4().hex[:6]}"
        self.step_results: Dict[str, Any] = {}
        self.patients: Dict[str, int] = {}  # ref → patient_id
        self.trace: List[Dict[str, Any]] = []

    async def setup(self) -> None:
        """Seed doctor, patients, knowledge items via ORM."""
        from db.engine import AsyncSessionLocal
        from db.crud.doctor import _ensure_doctor_exists
        from db.crud.patient import create_patient
        from db.crud.doctor import add_doctor_knowledge_item
        from domain.knowledge.doctor_knowledge import invalidate_knowledge_cache

        setup = self.fixture.get("setup", {})

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, self.doctor_id)

        # Create patients
        for p in setup.get("patients", []):
            async with AsyncSessionLocal() as db:
                patient, _code = await create_patient(
                    db, self.doctor_id, p["name"],
                    gender=p.get("gender"), age=p.get("age"),
                )
                self.patients[p.get("ref", p["name"])] = patient.id

        # Seed knowledge items
        for kb in setup.get("knowledge_items", []):
            async with AsyncSessionLocal() as db:
                from domain.knowledge.knowledge_crud import _encode_knowledge_payload
                payload = _encode_knowledge_payload(kb["text"], source="test", confidence=1.0)
                from db.models.doctor import DoctorKnowledgeItem
                item = DoctorKnowledgeItem(
                    doctor_id=self.doctor_id,
                    content=payload,
                    category=kb.get("category", "custom"),
                )
                db.add(item)
                await db.commit()

        invalidate_knowledge_cache(self.doctor_id)

    async def teardown(self) -> None:
        """Clean up all test data."""
        from db.engine import AsyncSessionLocal
        from sqlalchemy import text

        tables = [
            "patient_auth", "intake_sessions", "medical_records",
            "doctor_tasks", "doctor_knowledge_items", "doctor_chat_log",
            "patients", "doctors",
        ]
        async with AsyncSessionLocal() as db:
            for table in tables:
                try:
                    await db.execute(text(f"DELETE FROM {table} WHERE doctor_id = :did"), {"did": self.doctor_id})
                except Exception:
                    pass
            await db.commit()

    async def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one step and return the result."""
        call = step["call"]
        input_data = self._resolve_vars(step.get("input", {}))
        step_id = step["id"]

        if call == "doctor_intake.start":
            result = await self._call_intake_start(input_data)
        elif call == "doctor_intake.turn":
            result = await self._call_intake_turn(input_data)
        elif call == "doctor_intake.confirm":
            result = await self._call_intake_confirm(input_data)
        elif call == "diagnosis.run":
            result = await self._call_diagnosis(input_data)
        elif call == "draft_reply":
            result = await self._call_draft_reply(input_data)
        else:
            raise ValueError(f"Unknown step call: {call}")

        self.step_results[step_id] = result
        self.trace.append({"step_id": step_id, "call": call, "result": result})
        return result

    def _resolve_vars(self, data: Any) -> Any:
        """Resolve ${...} variable references in input data."""
        if isinstance(data, str):
            if data == "${doctor_id}":
                return self.doctor_id
            if data.startswith("${steps."):
                # e.g. ${steps.turn_1.data.session_id}
                parts = data[2:-1].split(".")  # steps, turn_1, data, session_id
                val = self.step_results
                for p in parts[1:]:  # skip "steps"
                    if isinstance(val, dict):
                        val = val.get(p)
                    else:
                        val = getattr(val, p, None)
                return val
            if data.startswith("${patients."):
                ref = data[len("${patients."):-1]
                return self.patients.get(ref)
            return data
        if isinstance(data, dict):
            return {k: self._resolve_vars(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._resolve_vars(v) for v in data]
        return data

    async def _call_intake_start(self, input_data: Dict) -> Dict:
        from domain.patients.intake_session import create_session
        session = await create_session(
            doctor_id=self.doctor_id,
            patient_id=input_data.get("patient_id"),
            mode=input_data.get("mode", "doctor"),
            initial_fields=input_data.get("initial_fields"),
        )
        return {"session_id": session.id, "status": session.status}

    async def _call_intake_turn(self, input_data: Dict) -> Dict:
        from domain.patients.intake_turn import intake_turn
        response = await intake_turn(input_data["session_id"], input_data["text"])
        return {
            "reply": response.reply,
            "collected": response.collected,
            "progress": response.progress,
            "status": response.status,
            "missing": getattr(response, "missing", []),
        }

    async def _call_intake_confirm(self, input_data: Dict) -> Dict:
        from channels.web.doctor_intake import intake_confirm_endpoint
        from unittest.mock import AsyncMock

        # Call the confirm endpoint function directly (skip HTTP)
        # We need to simulate the Form params
        from domain.patients.intake_session import load_session, save_session
        from db.models.intake_session import IntakeStatus
        from db.engine import AsyncSessionLocal
        from db.models.records import MedicalRecordDB, RecordStatus
        from db.crud.doctor import _ensure_doctor_exists

        session = await load_session(input_data["session_id"])
        if session is None:
            return {"error": "session not found"}

        from channels.web.doctor_intake import _build_clinical_text, _compute_progress
        collected = session.collected or {}
        clinical_text = _build_clinical_text(collected)

        has_diagnosis = bool(collected.get("diagnosis", "").strip())
        has_treatment = bool(collected.get("treatment_plan", "").strip())
        has_followup = bool(collected.get("orders_followup", "").strip())
        status = RecordStatus.completed if (has_diagnosis and has_treatment and has_followup) else RecordStatus.pending_review

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, self.doctor_id)
            record = MedicalRecordDB(
                doctor_id=self.doctor_id,
                patient_id=session.patient_id,
                record_type="intake_summary",
                status=status.value,
                content=clinical_text,
                chief_complaint=collected.get("chief_complaint"),
                present_illness=collected.get("present_illness"),
                past_history=collected.get("past_history"),
                allergy_history=collected.get("allergy_history"),
                personal_history=collected.get("personal_history"),
                family_history=collected.get("family_history"),
                physical_exam=collected.get("physical_exam"),
                diagnosis=collected.get("diagnosis"),
                treatment_plan=collected.get("treatment_plan"),
                orders_followup=collected.get("orders_followup"),
            )
            db.add(record)
            await db.commit()
            record_id = record.id

        session.status = IntakeStatus.confirmed
        await save_session(session)

        return {
            "status": status.value,
            "record_id": record_id,
        }

    async def _call_diagnosis(self, input_data: Dict) -> Dict:
        import json as _json
        from domain.diagnosis import run_diagnosis
        result = await run_diagnosis(
            doctor_id=self.doctor_id,
            record_id=input_data["record_id"],
        )
        # Convenience fields for assertions
        result["_json"] = _json.dumps(result, ensure_ascii=False)
        result["_differentials_count"] = len(result.get("differentials", []))
        result["_workup_count"] = len(result.get("workup", []))
        # Top differential for quick assertions
        diffs = result.get("differentials", [])
        if diffs:
            result["_top_condition"] = diffs[0].get("condition", "")
            result["_top_detail"] = diffs[0].get("detail", "")
        # All details concatenated for hallucination/citation checks
        all_details = []
        for d in diffs:
            all_details.append(d.get("detail", ""))
        for w in result.get("workup", []):
            all_details.append(w.get("detail", ""))
        for t in result.get("treatment", []):
            all_details.append(t.get("detail", ""))
        result["_all_details"] = " ".join(all_details)
        return result

    async def _call_draft_reply(self, input_data: Dict) -> Dict:
        from domain.patient_lifecycle.draft_reply import generate_draft_reply
        result = await generate_draft_reply(
            doctor_id=self.doctor_id,
            patient_id=str(input_data.get("patient_id", "")),
            message_id=input_data.get("message_id", 0),
            patient_message_text=input_data["text"],
            patient_context=input_data.get("patient_context", ""),
        )
        if result is None:
            return {"status": "skipped", "text": "", "cited_knowledge_ids": [], "char_count": 0}
        return {
            "status": "generated",
            "text": result.text,
            "cited_knowledge_ids": result.cited_knowledge_ids,
            "char_count": len(result.text),
        }

    def get_nested(self, result: Dict, path: str) -> Any:
        """Get a nested value from a result dict using dot notation.

        Supports list indexing with numeric keys: 'differentials.0.condition'
        """
        val = result
        for key in path.split("."):
            if isinstance(val, list):
                try:
                    val = val[int(key)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(val, dict):
                val = val.get(key)
            elif hasattr(val, key):
                val = getattr(val, key)
            else:
                return None
        return val

    async def db_count(self, table: str) -> int:
        """Count rows for this doctor in a table."""
        from db.engine import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE doctor_id = :did"),
                {"did": self.doctor_id},
            )).fetchone()
            return row[0] if row else 0
