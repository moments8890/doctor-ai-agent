/**
 * FIELD_LABELS — canonical Chinese labels for intake fields.
 *
 * Shared between doctor IntakePage (复合 14-field 模板) and patient ChatTab
 * (病史 6 项). Imports from one place so the patient submit popup matches
 * the doctor complete popup pixel-for-pixel.
 */

export const FIELD_LABELS = {
  department: "科室",
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
  family_history: "家族史",
  physical_exam: "体格检查",
  specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查",
  diagnosis: "初步诊断",
  treatment_plan: "治疗方案",
  orders_followup: "医嘱随访",
};

// Subset of fields the patient is asked about in self-intake. Mirrors
// _PATIENT_FIELDS in src/domain/intake/templates/medical_general.py:339.
// The submit dialog uses this as the denominator (not the doctor's full
// 14-field set) so progress reads "7/7" not "7/14".
export const PATIENT_INTAKE_FIELDS = [
  "chief_complaint",
  "present_illness",
  "past_history",
  "allergy_history",
  "family_history",
  "personal_history",
  "marital_reproductive",
];
