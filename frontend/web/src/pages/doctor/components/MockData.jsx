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
];

export const MOCK_TASKS = [
  { id: 201, doctor_id: "mock_doctor", patient_id: 1, patient_name: "陈伟强", task_type: "follow_up", title: "陈伟强 门诊随访", content: "头痛控制情况复查", status: "pending", due_at: "2026-04-01", created_at: "2026-03-26" },
  { id: 202, doctor_id: "mock_doctor", patient_id: 2, patient_name: "李复诊", task_type: "checkup", title: "李复诊 血糖复查", content: "空腹血糖 + HbA1c", status: "pending", due_at: "2026-03-28", created_at: "2026-03-25" },
  { id: 203, doctor_id: "mock_doctor", patient_id: 3, patient_name: "王明", task_type: "medication", title: "王明 用药调整", content: "降压药剂量调整后观察", status: "done", due_at: "2026-03-24", created_at: "2026-03-20" },
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
  pending_tasks: 2,
  completed_tasks: 1,
};

export const MOCK_CHAT_MESSAGES = [
  { role: "assistant", content: "医生好！👋\n直接说或输入患者信息，AI 会自动整理病历，您确认后保存。也可以🎤语音录入，或点击下方快捷指令。", ts: "2026-03-26T10:00:00" },
  { role: "user", content: "今日摘要", ts: "2026-03-26T10:00:05" },
  { role: "assistant", content: "📋 今日摘要\n\n📊 待处理任务：2 ✅ 今日已完成：1 🧑 今日接诊患者：3\n\n今日有2项待办任务需要处理。", ts: "2026-03-26T10:00:08" },
  { role: "user", content: "查看陈伟强的病历", ts: "2026-03-26T10:01:00" },
  { role: "assistant", content: "陈伟强，男，42岁\n\n最近门诊记录（2026-03-26）：\n主诉：头痛3天伴恶心呕吐\n诊断：高血压性头痛\n治疗：降压治疗，观察", ts: "2026-03-26T10:01:05" },
];

export const MOCK_INTERVIEW_FIELDS = {
  chief_complaint: "头痛3天伴恶心呕吐",
  present_illness: "3天前无明显诱因出现持续性胀痛",
  past_history: "高血压10年，糖尿病5年",
  allergy_history: "磺胺类药物过敏",
  family_history: "母亲高血压",
  personal_history: "不吸烟，不饮酒",
};
