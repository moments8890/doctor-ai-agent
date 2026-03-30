/**
 * 医生工作台常量：任务类型、病历类型、导航项、图标配置等静态配置。
 */
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import AssignmentTurnedInOutlinedIcon from "@mui/icons-material/AssignmentTurnedInOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import ContentPasteOutlinedIcon from "@mui/icons-material/ContentPasteOutlined";
import CameraAltOutlinedIcon from "@mui/icons-material/CameraAltOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import { COLOR } from "../../theme";

export const TASK_TYPE_LABEL = {
  follow_up:   "随访",
  medication:  "用药",
  checkup:     "检查",
  general:     "通用",
  review:      "审阅记录",
  lab_review:  "检验结果",
  imaging:     "影像检查",
};

export const TASK_STATUS_LABEL = {
  pending: "待处理",
  done: "已完成",
  cancelled: "已取消",
  snoozed: "已推迟",
};

export const ENCOUNTER_LABEL = {
  inpatient: "住院",
  outpatient: "门诊",
  first_visit: "初诊",
  follow_up_visit: "复诊",
  unknown: "未知",
};

export const RECORD_FIELDS = [
  { key: "record_type", label: "类型" },
];

export const RECORD_STRUCTURED_FIELDS = [
  { key: "chief_complaint", label: "主诉" },
  { key: "present_illness", label: "现病史" },
  { key: "past_history", label: "既往史" },
  { key: "allergy_history", label: "过敏史" },
  { key: "personal_history", label: "个人史" },
  { key: "marital_reproductive", label: "婚育史" },
  { key: "family_history", label: "家族史" },
  { key: "physical_exam", label: "体格检查" },
  { key: "specialist_exam", label: "专科检查" },
  { key: "auxiliary_exam", label: "辅助检查" },
  { key: "diagnosis", label: "初步诊断" },
  { key: "treatment_plan", label: "治疗方案" },
  { key: "orders_followup", label: "医嘱及随访" },
];

export const RECORD_TYPE_COLOR = {
  visit: "default",
  referral: "info",
  surgery: "error",
  lab: "success",
  imaging: "warning",
  dictation: "secondary",
  import: "default",
  interview_summary: "info",
};

export const RECORD_TYPE_LABEL = {
  visit: "门诊",
  referral: "转诊",
  surgery: "手术",
  lab: "检验",
  imaging: "影像",
  dictation: "语音录入",
  import: "导入",
  interview_summary: "问诊总结",
};

export const NAV = [
  { key: "my-ai", label: "我的AI", icon: <AutoAwesomeOutlinedIcon fontSize="medium" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="medium" /> },
  { key: "review", label: "审核", icon: <FactCheckOutlinedIcon fontSize="medium" />, badgeKey: "review" },
  { key: "tasks", label: "任务", icon: <AssignmentTurnedInOutlinedIcon fontSize="medium" />, badgeKey: "tasks" },
];

export const DESKTOP_NAV = [
  { key: "my-ai", label: "我的AI", icon: <AutoAwesomeOutlinedIcon fontSize="medium" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="medium" /> },
  { key: "review", label: "审核", icon: <FactCheckOutlinedIcon fontSize="medium" />, badgeKey: "review" },
  { key: "tasks", label: "任务", icon: <AssignmentTurnedInOutlinedIcon fontSize="medium" />, badgeKey: "tasks" },
  { key: "settings", label: "设置", icon: <SettingsOutlinedIcon fontSize="medium" /> },
];


export const LABEL_PRESET_COLORS = [
  "#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6",
];

export const RECORD_TYPE_FILTER_OPTS = [
  { value: "", label: "全部" },
  { value: "visit", label: "门诊" },
  { value: "dictation", label: "语音录入" },
  { value: "import", label: "导入" },
  { value: "lab", label: "检验" },
  { value: "imaging", label: "影像" },
  { value: "surgery", label: "手术" },
  { value: "referral", label: "转诊" },
  { value: "interview_summary", label: "问诊总结" },
];

export const TASK_STATUS_OPTS = [
  { value: "pending", label: "待处理" },
  { value: "snoozed", label: "已推迟" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
];

export const REVIEW_STATUS_LABEL = {
  pending_review: "待审核",
  reviewed: "已审核",
};

export const DIAGNOSIS_STATUS_LABEL = {
  pending: "诊断中",
  completed: "诊断完成",
  confirmed: "已确认",
  failed: "诊断失败",
};

export const DIAGNOSIS_STATUS_COLOR = {
  pending: COLOR.accent,
  completed: COLOR.primary,
  confirmed: COLOR.text4,
  failed: COLOR.danger,
};

export const STRUCTURED_FIELD_LABELS = {
  department: "科别",
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
  orders_followup: "医嘱及随访",
};

export const Action = {
  DAILY_SUMMARY:    "daily_summary",
  CREATE_RECORD:    "create_record",
  START_PATIENT_ONBOARDING: "start_patient_onboarding",
  QUERY_PATIENT:    "query_patient",
  QUERY_RECORDS:    "query_records",
  UPDATE_RECORD:    "update_record",
  CREATE_TASK:      "create_task",
  EXPORT_PDF:       "export_pdf",
  SEARCH_KNOWLEDGE: "search_knowledge",
  DIAGNOSIS:        "diagnosis",
  GENERAL:          "general",
};

export const QUICK_COMMANDS = [
  { key: Action.DAILY_SUMMARY, label: "今日摘要",  autoSend: true },
  { key: Action.CREATE_RECORD, label: "新增病历",  autoSend: false },
  { key: Action.START_PATIENT_ONBOARDING, label: "发预问诊", autoSend: false },
  { key: Action.QUERY_PATIENT, label: "查询患者",  autoSend: false, allowEmpty: true },
  { key: Action.DIAGNOSIS,     label: "诊断建议",  autoSend: false, disabled: true },
];

export const ONBOARDING_EXAMPLES = {
  diagnosisPatientNames: ["陈伟强", "李复诊"],
  replyPatientNames: ["陈伟强", "李复诊", "王明"],
  ruleTitles: ["术后头痛危险信号", "TIA复查路径"],
};

const ONBOARDING_STORAGE_PREFIX = "doctor_onboarding_state:v1";

export const ONBOARDING_STEP = {
  knowledge: "knowledge",
  diagnosis: "diagnosis",
  reply: "reply",
  patientPreview: "patient_preview",
  reviewTask: "review_task",
  followupTask: "followup_task",
};

const DEFAULT_ONBOARDING_STATE = {
  steps: {},
  lastSavedRuleTitle: "",
  lastSavedRuleId: null,
  lastSavedRuleAt: "",
  lastPreviewPatientId: null,
  lastPreviewPatientName: "",
  lastPreviewToken: "",
  lastReviewRecordId: null,
  lastReviewTaskId: null,
  lastFollowUpTaskIds: [],
};

function onboardingStorageKey(doctorId) {
  return `${ONBOARDING_STORAGE_PREFIX}:${doctorId || "anon"}`;
}

export function getOnboardingState(doctorId) {
  if (!doctorId) return { ...DEFAULT_ONBOARDING_STATE };
  try {
    const raw = localStorage.getItem(onboardingStorageKey(doctorId));
    if (!raw) return { ...DEFAULT_ONBOARDING_STATE };
    return { ...DEFAULT_ONBOARDING_STATE, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_ONBOARDING_STATE };
  }
}

export function setOnboardingState(doctorId, patch) {
  if (!doctorId) return { ...DEFAULT_ONBOARDING_STATE };
  const prev = getOnboardingState(doctorId);
  const next = {
    ...prev,
    ...(typeof patch === "function" ? patch(prev) : patch),
  };
  localStorage.setItem(onboardingStorageKey(doctorId), JSON.stringify(next));
  return next;
}

export function markOnboardingStep(doctorId, step, meta = {}) {
  const timestamp = new Date().toISOString();
  return setOnboardingState(doctorId, (prev) => ({
    ...prev,
    ...meta,
    steps: {
      ...(prev.steps || {}),
      [step]: timestamp,
    },
  }));
}

export function isOnboardingStepDone(state, step) {
  return Boolean(state?.steps?.[step]);
}

export function getLastSavedRuleTitle(doctorId) {
  return getOnboardingState(doctorId).lastSavedRuleTitle || "";
}

export function clearOnboardingState(doctorId) {
  if (!doctorId) return;
  localStorage.removeItem(onboardingStorageKey(doctorId));
}

export const SPECIALTY_OPTIONS = [
  "神经外科", "神经内科", "心内科", "内科", "外科",
  "骨科", "妇产科", "儿科", "眼科", "耳鼻喉科",
  "口腔科", "皮肤科", "精神科", "肿瘤科", "急诊科",
  "重症医学科", "康复科", "中医科", "全科医学科",
];

export const RECORD_TAB_GROUPS = [
  { key: "", label: "全部", types: null },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import", "surgery", "referral"] },
  { key: "lab_imaging", label: "检验/影像", types: ["lab", "imaging"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

export const TASK_FILTER_CHIPS = [
  { key: "all", label: "全部" },
  { key: "review", label: "待审核" },
  { key: "task", label: "待办" },
  { key: "done", label: "已完成" },
];

// ── Icon badge configs (used with <IconBadge config={...} />) ──────────────
// All avatar-style icons share the same visual treatment: icon in colored box.
// Palette: 4 colors — COLOR.primary (green), COLOR.accent (blue), COLOR.recordDoc (slate), COLOR.danger (red)

export const ICON_BADGES = {
  // Quick actions (MyAI page)
  qr_code:      { icon: QrCode2OutlinedIcon, bg: COLOR.primary },
  review:       { icon: CheckCircleOutlineIcon, bg: COLOR.accent },
  followup:     { icon: ChatOutlinedIcon, bg: COLOR.accent },
  new_record:   { icon: ContentPasteOutlinedIcon, bg: COLOR.primary },

  // Knowledge sources
  kb_doctor:    { icon: EditNoteOutlinedIcon, bg: COLOR.primary },
  kb_ai:        { icon: SmartToyOutlinedIcon, bg: COLOR.text4 },
  kb_upload:    { icon: DescriptionOutlinedIcon, bg: COLOR.primary },
  kb_url:       { icon: LinkOutlinedIcon, bg: COLOR.accent },
  kb_add:       { icon: AddCircleOutlineIcon, bg: COLOR.primary },

  // Knowledge add page
  upload:       { icon: UploadFileOutlinedIcon, bg: COLOR.primary },
  camera:       { icon: CameraAltOutlinedIcon, bg: COLOR.primary },
  url:          { icon: LinkOutlinedIcon, bg: COLOR.accent },

  // Chat avatars
  ai:           { icon: SmartToyOutlinedIcon, bg: COLOR.primary },
  doctor:       { icon: LocalHospitalOutlinedIcon, bg: COLOR.accent },
  patient:      { icon: PersonOutlineIcon, bg: COLOR.accent },
  notification: { icon: NotificationsNoneOutlinedIcon, bg: COLOR.borderLight, color: COLOR.text4 },

  // Record types
  rec_visit:     { icon: LocalHospitalOutlinedIcon, bg: COLOR.primary },
  rec_dictation: { icon: MicNoneOutlinedIcon, bg: COLOR.recordDoc },
  rec_import:    { icon: FileUploadOutlinedIcon, bg: COLOR.recordDoc },
  rec_lab:       { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  rec_imaging:   { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
  rec_surgery:   { icon: LocalHospitalOutlinedIcon, bg: COLOR.danger },
  rec_interview: { icon: ChatOutlinedIcon, bg: COLOR.primary },

  // Task types
  task_follow_up:  { icon: EventRepeatOutlinedIcon, bg: COLOR.primary },
  task_medication: { icon: MedicationOutlinedIcon, bg: COLOR.accent },
  task_checkup:    { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  task_general:    { icon: AssignmentOutlinedIcon, bg: COLOR.recordDoc },
  task_imaging:    { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
};

// Record type → IconBadge config lookup (shared with patient app)
export { RECORD_TYPE_BADGE } from "../../shared/badgeConfigs";
