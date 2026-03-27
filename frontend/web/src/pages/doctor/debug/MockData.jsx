/**
 * Static mock data for doctor UI development.
 * Import this instead of calling APIs when building UI without a backend.
 */

export const MOCK_DOCTOR = {
  doctorId: "mock_doctor",
  doctorName: "张医生",
  specialty: "神经外科",
  accessToken: "mock-token",
};

export const MOCK_PATIENTS = [
  { id: 1, name: "陈伟强", gender: "male", year_of_birth: 1984, phone: "138****5678", created_at: "2026-03-20", record_count: 3 },
  { id: 2, name: "李复诊", gender: "female", year_of_birth: 1970, phone: "139****1234", created_at: "2026-03-15", record_count: 1 },
  { id: 3, name: "王明", gender: "male", year_of_birth: 1955, phone: "136****9012", created_at: "2026-03-10", record_count: 5 },
  { id: 4, name: "张小红", gender: "female", year_of_birth: 1990, phone: "137****3456", created_at: "2026-03-25", record_count: 0 },
  { id: 5, name: "刘建国", gender: "male", year_of_birth: 1968, phone: "135****7890", created_at: "2026-03-22", record_count: 2 },
];

export const MOCK_RECORDS = [
  {
    id: 101, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "头痛3天伴恶心呕吐，血压165/100",
    created_at: "2026-03-26 10:30:00",
    structured: {
      chief_complaint: "头痛3天伴恶心呕吐",
      present_illness: "3天前无明显诱因出现持续性胀痛，以额颞部为主，伴恶心呕吐2次",
      past_history: "高血压10年，糖尿病5年",
      allergy_history: "磺胺类药物过敏",
      family_history: "母亲高血压",
      personal_history: "不吸烟，不饮酒",
      physical_exam: "BP 165/100mmHg，神清，颈软",
      auxiliary_exam: "CT未见出血",
      diagnosis: "高血压性头痛",
      treatment_plan: "降压治疗，观察",
    },
    tags: ["高血压", "头痛"],
  },
  {
    id: 102, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "interview_summary", status: "pending_review",
    content: "预问诊记录",
    created_at: "2026-03-26 08:15:00",
    structured: {
      chief_complaint: "头晕反复发作1月",
      present_illness: "1月前开始反复出现头晕，每次持续数分钟",
      past_history: "2型糖尿病8年",
      allergy_history: "无",
    },
    tags: ["头晕", "糖尿病"],
  },
  {
    id: 103, patient_id: 2, patient_name: "李复诊", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "复诊记录",
    created_at: "2026-03-25 05:32:00",
    structured: {
      chief_complaint: "头晕反复发作1月",
      past_history: "2型糖尿病8年，口服二甲双胍500mg bid",
      allergy_history: "磺胺类药物过敏",
      personal_history: "不吸烟，不饮酒",
      family_history: "母亲糖尿病",
    },
    tags: [],
  },
  // Records for patient 3 (王明)
  {
    id: 104, patient_id: 3, patient_name: "王明", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed", content: "高血压复诊",
    created_at: "2026-03-22 14:20:00",
    structured: {
      chief_complaint: "血压控制不佳2周",
      present_illness: "2周前开始血压波动，收缩压150-170mmHg",
      past_history: "高血压15年，冠心病5年",
      diagnosis: "高血压病3级（高危）",
      treatment_plan: "调整降压方案：氨氯地平5mg+缬沙坦80mg",
    },
    tags: ["高血压", "冠心病"],
  },
  {
    id: 105, patient_id: 3, patient_name: "王明", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed", content: "冠心病随访",
    created_at: "2026-03-15 09:30:00",
    structured: {
      chief_complaint: "胸闷活动后加重1周",
      present_illness: "1周前开始活动后出现胸闷",
      past_history: "冠心病5年，PCI术后2年",
      auxiliary_exam: "心电图：窦律，ST-T改变",
      diagnosis: "冠心病 PCI术后",
      treatment_plan: "继续双抗+他汀",
    },
    tags: ["冠心病", "PCI"],
  },
  // Records for patient 5 (刘建国)
  {
    id: 106, patient_id: 5, patient_name: "刘建国", doctor_id: "mock_doctor",
    record_type: "interview_summary", status: "pending_review", content: "预问诊记录",
    created_at: "2026-03-26 07:45:00",
    structured: {
      chief_complaint: "右侧肢体麻木3天",
      present_illness: "3天前无诱因出现右侧肢体麻木",
      past_history: "高血压8年，2型糖尿病3年",
      allergy_history: "无",
    },
    tags: ["肢体麻木", "高血压"],
  },
];

export const MOCK_TASKS = [
  { id: 201, doctor_id: "mock_doctor", patient_id: 1, patient_name: "陈伟强", task_type: "follow_up", title: "陈伟强 门诊随访", content: "头痛控制情况复查", status: "pending", due_at: "2026-04-01", created_at: "2026-03-26" },
  { id: 202, doctor_id: "mock_doctor", patient_id: 2, patient_name: "李复诊", task_type: "checkup", title: "李复诊 血糖复查", content: "空腹血糖 + HbA1c", status: "pending", due_at: "2026-03-28", created_at: "2026-03-25" },
  { id: 203, doctor_id: "mock_doctor", patient_id: 3, patient_name: "王明", task_type: "medication", title: "王明 用药调整", content: "降压药剂量调整后观察", status: "done", due_at: "2026-03-24", created_at: "2026-03-20" },
  { id: 204, doctor_id: "mock_doctor", patient_id: 5, patient_name: "刘建国", task_type: "review", title: "审阅刘建国预问诊记录", content: "患者已完成预问诊", status: "pending", due_at: "2026-03-26", created_at: "2026-03-26" },
  { id: 205, doctor_id: "mock_doctor", patient_id: 1, patient_name: "陈伟强", task_type: "lab_review", title: "陈伟强 血常规结果", content: "查看最新血常规报告", status: "pending", due_at: "2026-03-27", created_at: "2026-03-25" },
  { id: 206, doctor_id: "mock_doctor", patient_id: 3, patient_name: "王明", task_type: "imaging", title: "王明 头颅MRA预约", content: "已预约3月28日MRA检查", status: "done", due_at: "2026-03-28", created_at: "2026-03-22" },
];

export const MOCK_SUGGESTIONS = [
  { id: 301, record_id: 102, section: "differential", content: "高血压性头晕", detail: "长期高血压合并糖尿病，头晕可能为血压控制不佳所致。高血压性头晕通常表现为持续性或波动性头晕，与血压变化相关，需通过24小时动态血压监测确认。", confidence: "高", decision: null, is_custom: false },
  { id: 302, record_id: 102, section: "differential", content: "椎基底动脉供血不足", detail: "反复发作头晕，结合年龄和高血压病史，需排除后循环缺血。可通过头颅MRA评估椎基底动脉血流情况。", confidence: "中", decision: null, is_custom: false },
  { id: 303, record_id: 102, section: "differential", content: "良性阵发性位置性眩晕", detail: "反复发作性头晕需鉴别BPPV。典型表现为体位变化时短暂眩晕，需Dix-Hallpike试验排除。", confidence: "低", decision: null, is_custom: false },
  { id: 304, record_id: 102, section: "workup", content: "头颅MRA", detail: "评估椎基底动脉血流情况，排除后循环狭窄或闭塞。这是一种无创的血管成像检查，通常30分钟可完成。", urgency: "紧急", decision: null, is_custom: false },
  { id: 305, record_id: 102, section: "workup", content: "血压24h动态监测", detail: "评估全天血压波动规律与头晕发作的时间关系，帮助调整降压方案。", urgency: "常规", decision: null, is_custom: false },
  { id: 306, record_id: 102, section: "workup", content: "血糖监测", detail: "排除低血糖性头晕，特别是服用降糖药物期间。", urgency: "常规", decision: null, is_custom: false },
  { id: 307, record_id: 102, section: "treatment", content: "钙通道阻滞剂", detail: "优化降压方案，选择长效钙通道阻滞剂平稳降压，减少血压波动引起的头晕。", intervention: "药物", decision: null, is_custom: false },
  { id: 308, record_id: 102, section: "treatment", content: "前庭康复训练", detail: "如确诊BPPV，可进行Epley手法复位治疗，配合前庭康复训练改善平衡功能。", intervention: "观察", decision: null, is_custom: false },
];

export const MOCK_BRIEFING = {
  today_patients: 3,
  pending_tasks: 4,
  completed_tasks: 2,
  pending_reviews: 2,
  overdue_tasks: 2,
};

export const MOCK_CHAT_MESSAGES = [
  { role: "assistant", content: "医生好！👋\n直接说或输入患者信息，AI 会自动整理病历，您确认后保存。也可以🎤语音录入，或点击下方快捷指令。", ts: "2026-03-26T10:00:00" },
  { role: "user", content: "今日摘要", ts: "2026-03-26T10:00:05" },
  { role: "assistant", content: "📋 今日摘要\n\n📊 待处理任务：2 ✅ 今日已完成：1 🧑 今日接诊患者：3\n\n今日有2项待办任务需要处理。", ts: "2026-03-26T10:00:08" },
  { role: "user", content: "查看陈伟强的病历", ts: "2026-03-26T10:01:00" },
  { role: "assistant", content: "陈伟强，男，42岁\n\n最近门诊记录（2026-03-26）：\n主诉：头痛3天伴恶心呕吐\n诊断：高血压性头痛\n治疗：降压治疗，观察", ts: "2026-03-26T10:01:05" },
  { role: "user", content: "给陈伟强建个病历，主诉头痛3天", ts: "2026-03-26T10:02:00" },
  { role: "assistant", content: "好的，已为陈伟强创建病历草稿：\n\n主诉：头痛3天\n\n请继续补充现病史、既往史等信息，或点击确认保存。", ts: "2026-03-26T10:02:05", has_record: true },
];

export const MOCK_INTERVIEW_FIELDS = {
  chief_complaint: "头痛3天伴恶心呕吐",
  present_illness: "3天前无明显诱因出现持续性胀痛",
  past_history: "高血压10年，糖尿病5年",
  allergy_history: "磺胺类药物过敏",
  family_history: "母亲高血压",
  personal_history: "不吸烟，不饮酒",
};

export const MOCK_OVERDUE = [
  { id: 201, patient_name: "陈伟强", title: "门诊随访", due: "03-24" },
  { id: 202, patient_name: "李复诊", title: "血糖复查", due: "03-25" },
];

export const MOCK_INTERVIEW_STATE = {
  session_id: "mock-session-001",
  status: "interviewing",
  progress: { filled: 6, total: 13, pct: 46 },
  collected: {
    chief_complaint: "头痛3天伴恶心呕吐",
    present_illness: "3天前无明显诱因出现持续性胀痛",
    past_history: "高血压10年，糖尿病5年",
    allergy_history: "磺胺类药物过敏",
    family_history: "母亲高血压",
    personal_history: "不吸烟，不饮酒",
  },
  missing: ["physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis", "treatment_plan", "orders_followup", "marital_reproductive"],
  conversation: [
    { role: "assistant", content: "请描述患者的主诉（主要症状和持续时间）。" },
    { role: "user", content: "陈伟强 男 42岁 头痛3天伴恶心呕吐" },
    { role: "assistant", content: "收到。高血压10年，糖尿病5年。还有其他既往病史吗？" },
    { role: "user", content: "磺胺类药物过敏，母亲高血压，不吸烟不饮酒" },
    { role: "assistant", content: "既往史和个人史已记录。请补充体格检查和辅助检查结果。" },
  ],
  suggestions: ["血压偏高", "建议头颅CT", "查肝肾功能"],
};

export const MOCK_CARRY_FORWARD = [
  { field: "past_history", label: "既往史", value: "高血压10年，口服氨氯地平5mg qd", source_date: "2026-03-20" },
  { field: "allergy_history", label: "过敏史", value: "磺胺类药物过敏", source_date: "2026-03-20" },
  { field: "family_history", label: "家族史", value: "母亲高血压", source_date: "2026-03-20" },
  { field: "personal_history", label: "个人史", value: "不吸烟，不饮酒", source_date: "2026-03-20" },
];

export const MOCK_PATIENT_MESSAGES = [
  { id: 501, patient_id: 1, patient_name: "陈伟强", content: "医生，我今天头又开始痛了，比昨天厉害", source: "patient", triage_category: "escalation", created_at: "2026-03-26T08:30:00" },
  { id: 502, patient_id: 1, patient_name: "陈伟强", content: "降压药是饭前吃还是饭后吃？", source: "patient", triage_category: "informational", created_at: "2026-03-26T09:15:00" },
  { id: 503, patient_id: 2, patient_name: "李复诊", content: "血糖测了空腹7.2，餐后11.5", source: "patient", triage_category: "informational", created_at: "2026-03-25T20:00:00" },
];

export const MOCK_KNOWLEDGE_ITEMS = [
  { id: 1, category: "red_flag", text: "蛛网膜下腔出血（SAH）：突发剧烈头痛（雷击样），伴恶心呕吐、颈强直、意识障碍。Fisher分级指导治疗。Hunt-Hess分级评估预后。", source: "agent_auto", created_at: "2026-03-20", reference_count: 5 },
  { id: 2, category: "red_flag", text: "急性脑梗死：突发偏瘫、失语、视野缺损。NIHSS评分＞4分考虑溶栓或取栓。4.5h窗口期rtPA，24h窗口期机械取栓。", source: "doctor", created_at: "2026-03-18", reference_count: 3 },
  { id: 3, category: "interview_guide", text: "高血压患者首诊：必须询问头痛、头晕、视物模糊、胸闷。必须测量双上肢血压。询问家族史、用药依从性。", source: "doctor", created_at: "2026-03-15", reference_count: 8 },
  { id: 4, category: "diagnosis_rule", text: "高血压分级：1级（140-159/90-99）2级（160-179/100-109）3级（≥180/≥110）。危险分层：低危/中危/高危/很高危。", source: "agent_auto", created_at: "2026-03-10", reference_count: 12 },
  { id: 5, category: "treatment_protocol", text: "脑动脉瘤术后管理：尼莫地平60mg/d预防血管痉挛14天。术后3天CT排除再出血。7天DSA评估效果。每日TCD监测。", source: "doctor", created_at: "2026-03-22", reference_count: 2 },
];

export const MOCK_FIELD_LABELS = {
  chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

export const MOCK_SETTINGS_TEMPLATES = [
  { name: "门诊病历模板", desc: "默认模板，包含主诉、现病史、既往史等字段", badge: "默认" },
  { name: "神经外科专科模板", desc: "包含GCS评分、瞳孔检查、神经系统查体等专科字段" },
  { name: "术后随访模板", desc: "术后恢复情况、伤口愈合、并发症筛查" },
];
