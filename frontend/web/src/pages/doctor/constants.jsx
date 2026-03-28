/**
 * 医生工作台常量：任务类型、病历类型、导航项等静态配置。
 */
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import AssignmentTurnedInOutlinedIcon from "@mui/icons-material/AssignmentTurnedInOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

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
  { key: "review", label: "门诊", icon: <LocalHospitalOutlinedIcon fontSize="medium" />, badgeKey: "review" },
  { key: "followup", label: "任务", icon: <AssignmentTurnedInOutlinedIcon fontSize="medium" />, badgeKey: "followup" },
];

export const DESKTOP_NAV = [
  { key: "my-ai", label: "我的AI", icon: <AutoAwesomeOutlinedIcon fontSize="medium" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="medium" /> },
  { key: "review", label: "门诊", icon: <LocalHospitalOutlinedIcon fontSize="medium" />, badgeKey: "review" },
  { key: "followup", label: "任务", icon: <AssignmentTurnedInOutlinedIcon fontSize="medium" />, badgeKey: "followup" },
  { key: "settings", label: "设置", icon: <SettingsOutlinedIcon fontSize="medium" /> },
];

export const AVATAR_COLORS = [
  "#07C160", "#5b9bd5", "#e8833a", "#9b59b6", "#FA5151",
  "#16a085", "#d35400", "#8e44ad", "#2980b9", "#c0392b",
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
  pending: "#1890ff",
  completed: "#07C160",
  confirmed: "#999",
  failed: "#FA5151",
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
  { key: Action.QUERY_PATIENT, label: "查询患者",  autoSend: false, allowEmpty: true },
  { key: Action.DIAGNOSIS,     label: "诊断建议",  autoSend: false, disabled: true },
];

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

