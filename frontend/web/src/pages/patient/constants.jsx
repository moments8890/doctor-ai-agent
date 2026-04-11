/**
 * Shared constants for patient portal pages.
 * Extracted from the monolithic PatientPage.jsx.
 */

import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import { COLOR } from "../../theme";

// ---------------------------------------------------------------------------
// localStorage keys
// ---------------------------------------------------------------------------

export const STORAGE_KEY = "patient_portal_token";
export const STORAGE_NAME_KEY = "patient_portal_name";
export const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
export const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
export const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
export const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";

// ---------------------------------------------------------------------------
// Record display helpers
// ---------------------------------------------------------------------------

export const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊",
};

export const FIELD_LABELS = {
  department: "科别", chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "初步诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

export const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

export const DIAGNOSIS_STATUS_LABELS = {
  pending: "诊断中", completed: "待审核", confirmed: "已确认", failed: "诊断失败",
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export const NAV_TABS = [
  { key: "chat", label: "主页", icon: <ChatOutlinedIcon />, title: "AI 健康助手" },
  { key: "records", label: "病历", icon: <DescriptionOutlinedIcon />, title: "病历" },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon />, title: "任务" },
  { key: "profile", label: "我的", icon: <PersonOutlineIcon />, title: "我的" },
];

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

// Layout matches DoctorPage — MobileFrame in App.jsx handles the phone container
export const PAGE_LAYOUT = {
  display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt,
  position: "relative", overflow: "hidden",
};

// ---------------------------------------------------------------------------
// Filter configs
// ---------------------------------------------------------------------------

export const PATIENT_RECORD_TABS = [
  { key: "", label: "全部" },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

export const PATIENT_TASK_FILTERS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待完成" },
  { key: "done", label: "已完成" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }); }
  catch { return iso; }
}
