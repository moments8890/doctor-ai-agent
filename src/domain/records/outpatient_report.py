"""
卫医政发〔2010〕11号 门诊病历标准格式报告生成。

功能：
1. extract_outpatient_fields(records, patient, doctor_id) → dict[str, str]
   从存储的 结构化数据中合并标准字段。

2. generate_outpatient_report_pdf(fields, patient_name, patient_info, clinic_name, doctor_name) → bytes
   按表单样式渲染 PDF（标题行 + 患者信息行 + 各字段分节）。

字段列表（卫医政发〔2010〕11号 + 国卫办医政发〔2024〕16号）：
  就诊类型 / 科别 /
  主诉 / 现病史 / 既往史 / 过敏史 / 个人史 / 家族史 /
  体格检查 / 辅助检查 / 初步诊断（含ICD编码）/ 治疗方案 / 医嘱及随访
"""
from __future__ import annotations

from typing import Any, Optional

from domain.records.schema import OUTPATIENT_FIELD_META, FIELD_KEYS, OutpatientRecord, PatientInfo
from utils.log import log


class ExtractionError(RuntimeError):
    """Raised when no structured data could be extracted from records."""

# ---------------------------------------------------------------------------
# Standard field definitions (imported from shared schema)
# ---------------------------------------------------------------------------

OUTPATIENT_FIELDS = OUTPATIENT_FIELD_META

# Fields rendered in the PDF header row rather than as full sections
_HEADER_ONLY_FIELDS = {"department"}

_FIELD_KEYS = FIELD_KEYS

# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _merge_structured_fields(records: list) -> Optional[dict[str, str]]:
    """Merge stored structured data from multiple records; return None if any record lacks it."""
    # Cumulative fields: merge across all records
    _CUMULATIVE = {"past_history", "allergy_history", "family_history", "marital_reproductive", "personal_history"}

    parsed: list[dict] = []
    for rec in records:
        if not rec.has_structured_data():
            return None  # at least one record has no structured data → fall back to LLM
        parsed.append(rec.structured_dict())

    # Start with empty fields, apply in chronological order (oldest first)
    result: dict[str, str] = {k: "" for k in _FIELD_KEYS}
    cumulative: dict[str, list[str]] = {k: [] for k in _CUMULATIVE}

    for struct in parsed:
        for key in _FIELD_KEYS:
            val = str(struct.get(key, "") or "").strip()
            if not val:
                continue
            if key in _CUMULATIVE:
                if val not in cumulative[key]:  # deduplicate
                    cumulative[key].append(val)
            else:
                result[key] = val  # override: latest wins

    for key in _CUMULATIVE:
        if cumulative[key]:
            result[key] = "；".join(cumulative[key])

    return result


async def extract_outpatient_fields(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict[str, str]:
    """提取门诊标准字段：从已存储的 结构化数据中合并。"""
    merged = _merge_structured_fields(records)
    if merged is not None:
        log(f"[outpatient-report] using stored structured data ({len(records)} records)")
        return merged
    raise ExtractionError("No structured data found in records")


async def export_as_json(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict:
    """Extract fields and return as OutpatientRecord dict."""
    fields = await extract_outpatient_fields(records, patient, doctor_id)
    patient_info = PatientInfo()
    if patient:
        patient_info.name = getattr(patient, "name", None)
        patient_info.gender = getattr(patient, "gender", None)
        yob = getattr(patient, "year_of_birth", None)
        if yob:
            from datetime import date
            patient_info.age = date.today().year - int(yob)
    record = OutpatientRecord(patient=patient_info, **fields)
    return record.model_dump()


