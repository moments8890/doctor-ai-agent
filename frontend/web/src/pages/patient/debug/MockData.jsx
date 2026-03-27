/**
 * Static mock data for patient UI development.
 * Import this instead of calling APIs when building UI without a backend.
 */

export const MOCK_PATIENT = {
  patient_name: "陈伟强",
  gender: "male",
  year_of_birth: 1984,
  phone: "138****5678",
  doctor_id: "mock_doctor",
  doctor_name: "张医生",
  doctor_specialty: "神经外科",
};

export const MOCK_RECORDS = [
  {
    id: 101, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "头痛3天伴恶心呕吐",
    created_at: "2026-03-26 10:30:00",
    structured: {
      chief_complaint: "头痛3天伴恶心呕吐",
      present_illness: "3天前无明显诱因出现持续性胀痛，以额颞部为主，伴恶心呕吐2次，非喷射性，呕吐物为胃内容物，无咖啡色液体。自测血压165/100mmHg，服用氨氯地平后头痛略有缓解。",
      past_history: "高血压10年，口服氨氯地平5mg qd，血压控制尚可；2型糖尿病5年，口服二甲双胍500mg bid",
      allergy_history: "磺胺类药物过敏（皮疹）",
      family_history: "母亲高血压病史20年，父亲2型糖尿病",
      personal_history: "不吸烟，不饮酒，睡眠欠佳",
      physical_exam: "BP 165/100mmHg，HR 82次/分，神清，颈软，双瞳等大等圆，对光反射灵敏",
      specialist_exam: "四肢肌力V级，肌张力正常，病理征未引出，指鼻试验稳准",
      auxiliary_exam: "头颅CT未见明显出血灶，血常规正常，肝肾功能正常",
      diagnosis: "高血压性头痛",
      treatment_plan: "降压治疗，调整氨氯地平至5mg bid，加用缬沙坦80mg qd",
      orders_followup: "2周后门诊复诊，监测血压变化，如头痛加重或出现视物模糊立即就诊",
      department: "神经外科",
      marital_reproductive: "已婚，育有一子",
    },
    diagnosis_status: "confirmed",
    medications: [{ name: "氨氯地平", dosage: "5mg", frequency: "每日一次" }],
    followup_plan: "2周后复诊",
    lifestyle: "低盐饮食，规律作息",
    tags: ["高血压", "头痛"],
  },
  {
    id: 102, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "interview_summary", status: "pending_review",
    content: "头晕反复发作1月",
    created_at: "2026-03-26 08:15:00",
    structured: {
      chief_complaint: "头晕反复发作1月",
      present_illness: "1月前开始反复出现头晕，每次持续数分钟至半小时不等，以晨起及体位变化时明显，无视物旋转，无耳鸣听力下降",
      past_history: "高血压10年，2型糖尿病5年",
      allergy_history: "磺胺类药物过敏",
    },
    tags: ["头晕", "待审核"],
  },
  {
    id: 103, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "血压控制不佳2周",
    created_at: "2026-03-22 14:20:00",
    structured: {
      chief_complaint: "血压控制不佳2周",
      present_illness: "2周前开始血压波动明显，家庭自测收缩压150-170mmHg，舒张压95-105mmHg，伴间断性头胀不适",
      past_history: "高血压10年，2型糖尿病5年",
      diagnosis: "高血压病3级（高危）",
      treatment_plan: "调整降压方案：氨氯地平5mg+缬沙坦80mg",
    },
    tags: ["高血压", "药物调整"],
  },
  {
    id: 104, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "糖尿病复查",
    created_at: "2026-03-18 09:00:00",
    structured: {
      chief_complaint: "糖尿病复查",
      present_illness: "规律服用二甲双胍500mg bid，近期无明显口干多饮多尿，偶有餐后腹胀",
      past_history: "2型糖尿病5年，高血压10年",
      auxiliary_exam: "空腹血糖8.2mmol/L（偏高），HbA1c 7.1%（控制欠佳），肝功能正常，肾功能正常，尿微量白蛋白正常",
      diagnosis: "2型糖尿病",
      treatment_plan: "二甲双胍加量至1000mg bid，加用阿卡波糖50mg tid",
    },
    tags: ["糖尿病", "血糖控制"],
  },
  {
    id: 105, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "import", status: "completed",
    content: "外院转入MRI报告",
    created_at: "2026-03-15 11:30:00",
    structured: {
      auxiliary_exam: "头颅MRI（2026-03-14 外院）：双侧基底节区少许腔隙性缺血灶，脑白质轻度脱髓鞘改变，未见占位性病变，中线结构居中，脑室系统未见明显扩大",
    },
    tags: ["MRI", "外院报告"],
  },
  {
    id: 106, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "失眠2周",
    created_at: "2026-01-20 15:45:00",
    structured: {
      chief_complaint: "失眠2周",
      present_illness: "2周前开始出现入睡困难，每晚需1-2小时方能入睡，睡后易醒，每晚总睡眠时间约4-5小时，白天精神差，注意力难以集中，伴有心烦焦虑感",
      past_history: "高血压10年，2型糖尿病5年",
      diagnosis: "焦虑相关性失眠",
      treatment_plan: "右佐匹克隆1mg qn，短期使用不超过2周；认知行为疗法指导",
    },
    tags: ["失眠", "焦虑"],
  },
];

export const MOCK_TASKS = [
  {
    id: 1, patient_id: 1, task_type: "follow_up", title: "神经外科复诊",
    content: "携带近期血压记录",
    status: "pending", due_at: "2026-03-29", record_id: 101,
    created_at: "2026-03-26",
  },
  {
    id: 2, patient_id: 1, task_type: "medication", title: "降压药服药提醒",
    content: "氨氯地平5mg，每日一次",
    status: "notified", due_at: "2026-03-25",
    created_at: "2026-03-24",
  },
  {
    id: 3, patient_id: 1, task_type: "checkup", title: "复查头颅MRI",
    content: "空腹，预约放射科",
    status: "pending", due_at: "2026-04-02",
    created_at: "2026-03-26",
  },
  {
    id: 4, patient_id: 1, task_type: "checkup", title: "空腹血糖检测",
    content: "空腹采血，检测血糖及HbA1c",
    status: "completed", due_at: "2026-03-24",
    completed_at: "2026-03-24", created_at: "2026-03-20",
  },
  {
    id: 5, patient_id: 1, task_type: "follow_up", title: "血压监测记录",
    content: "每日早晚各测一次血压并记录",
    status: "completed", due_at: "2026-03-21",
    completed_at: "2026-03-21", created_at: "2026-03-18",
  },
];

export const MOCK_CHAT_MESSAGES = [
  {
    id: 1, role: "assistant",
    content: "您好，陈先生！我是您的健康助手。有什么可以帮您的吗？您可以随时向我描述症状或咨询健康问题。",
    created_at: "2026-03-26T09:00:00",
  },
  {
    id: 2, role: "user",
    content: "最近头痛又开始了，已经持续3天了",
    created_at: "2026-03-26T09:00:35",
  },
  {
    id: 3, role: "assistant",
    content: "了解，头痛持续3天了。请问疼痛主要在什么位置？是整个头痛还是某个部位比较明显？",
    created_at: "2026-03-26T09:00:42",
  },
  {
    id: 4, role: "user",
    content: "主要是两侧太阳穴，胀痛",
    created_at: "2026-03-26T09:01:15",
  },
  {
    id: 5, role: "assistant",
    content: "双侧太阳穴胀痛，好的。请问疼痛程度如何？0到10分的话您觉得大概几分？有没有伴随恶心呕吐的感觉？",
    created_at: "2026-03-26T09:01:22",
  },
  {
    id: 6, role: "user",
    content: "大概6分吧，有点恶心，没有呕吐",
    created_at: "2026-03-26T09:02:00",
  },
  {
    id: 7, role: "assistant",
    content: "中度疼痛伴恶心，考虑到您的高血压病史，请问最近血压测过吗？降压药有按时服用吗？",
    created_at: "2026-03-26T09:02:08",
  },
  {
    id: 8, role: "user",
    content: "昨天量了一次，150/95，药一直在吃",
    created_at: "2026-03-26T09:02:45",
  },
  {
    id: 9, role: "assistant",
    content: "根据您的描述，双侧太阳穴胀痛3天，伴恶心，血压150/95mmHg偏高，结合您的高血压病史，头痛很可能与血压控制不佳有关。\n\n建议您：\n1. 继续规律服用降压药，不要自行停药或减量\n2. 每天早晚各测一次血压并做好记录\n3. 近几天低盐饮食，避免熬夜和情绪波动\n4. 如果头痛加重、出现视物模糊或肢体无力，请立即就医\n\n建议您尽快预约张医生的门诊复诊，可能需要调整降压方案。",
    created_at: "2026-03-26T09:02:55",
    triage_category: "diagnosis_confirmation",
  },
  {
    id: 10, role: "user",
    content: "好的谢谢",
    created_at: "2026-03-26T09:03:20",
  },
  {
    id: 11, role: "assistant",
    content: "不客气！记得按时测血压，有任何不适随时告诉我。祝您早日康复！",
    created_at: "2026-03-26T09:03:26",
  },
  {
    id: 12, role: "doctor",
    content: "陈先生您好，我看了您最近的血压情况，建议这周六上午来门诊复查一下，我帮您调整一下降压方案。来的时候带上最近的血压记录。",
    created_at: "2026-03-26T10:15:00",
    doctor_name: "张医生",
  },
  {
    id: 13, role: "user",
    content: "好的张医生，周六上午我过来，血压记录我每天都有记的",
    created_at: "2026-03-26T10:16:30",
  },
  {
    id: 14, role: "assistant",
    content: "已收到您的回复，张医生那边会看到的。周六复诊前记得继续每天记录血压哦。",
    created_at: "2026-03-26T10:16:38",
  },
];

export const MOCK_INTERVIEW_STATE = {
  session_id: "mock-interview-001",
  status: "interviewing",
  collected: {
    chief_complaint: "头痛反复发作",
    present_illness: "近1月来反复头痛，以双侧太阳穴为主，每次持续2-3小时",
  },
  progress: { filled: 2, total: 7 },
  reply: "收到，主诉和现病史已记录。请问您有什么既往病史吗？比如高血压、糖尿病？",
  suggestions: ["有高血压", "有糖尿病", "没有慢性病", "不太清楚"],
  conversation: [
    { role: "assistant", content: "您好！我是预问诊助手，帮您提前记录病情信息，方便医生更快了解您的情况。请问您今天主要想看什么问题？" },
    { role: "user", content: "我头痛反复发作，想来看看" },
    { role: "assistant", content: "好的，头痛反复发作。请问大概持续多长时间了？每次发作持续多久？主要在头部什么位置？" },
    { role: "user", content: "差不多一个月了，每次两三个小时，主要是两边太阳穴" },
    { role: "assistant", content: "收到，主诉和现病史已记录。请问您有什么既往病史吗？比如高血压、糖尿病？" },
  ],
};
