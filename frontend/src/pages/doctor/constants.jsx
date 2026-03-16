/**
 * 医生工作台常量：任务类型、病历类型、导航项等静态配置。
 */
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";

export const TASK_TYPE_LABEL = {
  follow_up:   "随访",
  medication:  "用药管理",
  lab_review:  "检验复查",
  referral:    "转诊",
  imaging:     "影像检查",
  appointment: "预约就诊",
  general:     "通用任务",
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
  { key: "content", label: "临床笔记" },
  { key: "record_type", label: "类型" },
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
  { key: "chat", label: "AI 助手", icon: <ChatOutlinedIcon fontSize="medium" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="medium" /> },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon fontSize="medium" /> },
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

export const QUICK_COMMANDS = [
  { label: "新建患者", iconKey: "personAdd", insert: "新建患者：" },
  { label: "查询患者", iconKey: "search", insert: "查询患者：" },
  { label: "患者列表", iconKey: "people", insert: "患者列表" },
  { label: "补充记录", iconKey: "noteAdd", insert: "补充记录：" },
  { label: "修正上条", iconKey: "edit", insert: "刚才写错了，应该是" },
  { label: "导出PDF", iconKey: "download", insert: "导出病历PDF：" },
  { label: "今日任务", iconKey: "assignment", insert: "今日任务" },
  { label: "今日摘要", iconKey: "assessment", insert: "今日工作摘要" },
];

export const SPECIALTY_OPTIONS = [
  "神经外科", "神经内科", "心内科", "内科", "外科",
  "骨科", "妇产科", "儿科", "眼科", "耳鼻喉科",
  "口腔科", "皮肤科", "精神科", "肿瘤科", "急诊科",
  "重症医学科", "康复科", "中医科", "全科医学科",
];

