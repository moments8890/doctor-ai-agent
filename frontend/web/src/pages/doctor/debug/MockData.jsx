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
  { id: 1, name: "陈伟强", gender: "male", year_of_birth: 1984, phone: "138****5678", created_at: "2026-03-20", record_count: 2 },
  { id: 2, name: "李复诊", gender: "female", year_of_birth: 1970, phone: "139****1234", created_at: "2026-03-25", record_count: 1 },
  { id: 3, name: "王明", gender: "male", year_of_birth: 1955, phone: "136****9012", created_at: "2026-03-15", record_count: 2 },
  { id: 4, name: "张小红", gender: "female", year_of_birth: 1990, phone: "137****3456", created_at: "2026-03-25", record_count: 1 },
  { id: 5, name: "刘建国", gender: "male", year_of_birth: 1968, phone: "135****7890", created_at: "2026-03-22", record_count: 1 },
];

export const MOCK_RECORDS = [
  // Patient 1: 陈伟强 — 脑膜瘤术后7天
  {
    id: 101, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "右额叶脑膜瘤开颅切除术后7天",
    created_at: "2026-03-20 09:00:00",
    structured: {
      chief_complaint: "头痛渐进性加重2月伴右眼视力下降1月",
      present_illness: "近2个月头痛逐渐加重，以右额部为主，伴右眼视力进行性下降。MRI示右额叶脑膜瘤4.2x3.8cm，中线轻度左移",
      past_history: "既往体健，无高血压糖尿病史",
      allergy_history: "无",
      family_history: "无特殊",
      personal_history: "不吸烟，偶尔饮酒",
      physical_exam: "神清，GCS 15分，右眼视力0.4，双侧瞳孔等大等圆",
      auxiliary_exam: "头颅MRI增强：右额叶脑膜瘤，均匀强化，硬脑膜尾征阳性",
      diagnosis: "右额叶脑膜瘤（WHO I级）",
      treatment_plan: "开颅脑膜瘤切除术（Simpson I级切除）",
    },
    tags: ["脑膜瘤", "开颅手术"],
  },
  {
    id: 102, patient_id: 1, patient_name: "陈伟强", doctor_id: "mock_doctor",
    record_type: "interview_summary", status: "pending_review",
    content: "术后第7天随访记录",
    created_at: "2026-03-27 08:15:00",
    structured: {
      chief_complaint: "术后头痛加剧伴恶心1天",
      present_illness: "脑膜瘤术后第7天，昨日开始头痛较前明显加剧，今晨伴恶心1次，无呕吐，无肢体活动障碍",
      past_history: "3月20日行右额叶脑膜瘤开颅切除术",
      allergy_history: "无",
    },
    tags: ["术后随访", "头痛加剧"],
  },
  // Patient 2: 李复诊 — TIA首发48小时
  {
    id: 103, patient_id: 2, patient_name: "李复诊", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "TIA首发就诊记录",
    created_at: "2026-03-25 14:30:00",
    structured: {
      chief_complaint: "右侧肢体无力20分钟自行缓解",
      present_illness: "2天前突发右侧上下肢无力，伴言语含糊，持续约20分钟后完全缓解。无头痛、无意识障碍",
      past_history: "高血压8年，口服氨氯地平5mg qd；2型糖尿病3年，二甲双胍500mg bid",
      allergy_history: "磺胺类药物过敏",
      physical_exam: "BP 152/96mmHg，神清，NIHSS 0分，四肢肌力V级",
      auxiliary_exam: "急诊头颅CT未见出血，心电图：窦律",
      diagnosis: "短暂性脑缺血发作（TIA）",
      treatment_plan: "ABCD2评分4分，收入院观察。启动阿司匹林100mg+氯吡格雷75mg双抗，阿托伐他汀20mg",
    },
    tags: ["TIA", "脑血管"],
  },
  // Patient 3: 王明 — 脑动脉瘤术后12天
  {
    id: 104, patient_id: 3, patient_name: "王明", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "前交通动脉瘤破裂急诊手术记录",
    created_at: "2026-03-15 03:20:00",
    structured: {
      chief_complaint: "突发剧烈头痛伴意识障碍2小时",
      present_illness: "2小时前突发剧烈头痛（雷击样），随即意识模糊，伴呕吐3次。急诊CT示蛛网膜下腔出血Fisher III级，CTA示前交通动脉瘤6mm",
      past_history: "高血压5年，不规则服药。否认糖尿病、冠心病",
      allergy_history: "无",
      physical_exam: "GCS 12分（E3V4M5），Hunt-Hess III级，颈强直阳性，Kernig征阳性",
      auxiliary_exam: "头颅CT：弥漫性蛛网膜下腔出血。CTA：前交通动脉瘤6x5mm",
      diagnosis: "前交通动脉瘤破裂伴蛛网膜下腔出血（Hunt-Hess III级，Fisher III级）",
      treatment_plan: "急诊开颅动脉瘤夹闭术+去骨瓣减压术",
    },
    tags: ["动脉瘤", "蛛网膜下腔出血", "急诊手术"],
  },
  {
    id: 105, patient_id: 3, patient_name: "王明", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "术后第12天查房记录",
    created_at: "2026-03-27 08:30:00",
    structured: {
      chief_complaint: "动脉瘤术后12天，轻微头痛",
      present_illness: "动脉瘤夹闭术后第12天，头痛较前缓解，偶有轻微胀痛，无恶心呕吐，意识清醒，肢体活动正常",
      past_history: "3月15日急诊行前交通动脉瘤夹闭术+去骨瓣减压术",
      physical_exam: "GCS 15分，双侧瞳孔等大等圆，四肢肌力V级，切口愈合良好",
      diagnosis: "前交通动脉瘤夹闭术后（恢复期）",
      treatment_plan: "继续尼莫地平预防血管痉挛，下周复查DSA评估夹闭效果",
    },
    tags: ["术后恢复", "动脉瘤夹闭"],
  },
  // Patient 4: 张小红 — 三叉神经痛
  {
    id: 107, patient_id: 4, patient_name: "张小红", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "三叉神经痛门诊记录",
    created_at: "2026-03-25 10:00:00",
    structured: {
      chief_complaint: "右侧面部阵发性电击样疼痛3月",
      present_illness: "3月前开始出现右侧面部阵发性剧烈疼痛，呈电击样、刀割样，每次持续数秒至1分钟，洗脸刷牙可诱发，频率渐增",
      past_history: "既往体健",
      allergy_history: "无",
      physical_exam: "右侧三叉神经V2支分布区触痛阳性，扳机点：右上唇旁",
      auxiliary_exam: "头颅MRI：右侧三叉神经根部可见血管压迫征象",
      diagnosis: "右侧三叉神经痛（V2支）",
      treatment_plan: "卡马西平100mg bid起始，逐渐加量至疼痛控制，2周后复查疗效。如药物控制不佳，考虑微血管减压术",
    },
    tags: ["三叉神经痛", "药物治疗"],
  },
  // Patient 5: 刘建国 — 腰椎管狭窄
  {
    id: 106, patient_id: 5, patient_name: "刘建国", doctor_id: "mock_doctor",
    record_type: "visit", status: "completed",
    content: "腰椎管狭窄门诊记录",
    created_at: "2026-03-22 09:00:00",
    structured: {
      chief_complaint: "腰痛伴双下肢间歇性跛行6月",
      present_illness: "6月前开始出现腰痛，行走约200米后双下肢酸痛无力，需蹲下休息数分钟方可继续行走，渐进性加重",
      past_history: "腰椎间盘突出症病史10年。高血压5年，规律服药",
      allergy_history: "无",
      physical_exam: "腰椎活动度受限，直腿抬高试验：左60°(+)右70°(+)，双下肢肌力IV级",
      auxiliary_exam: "腰椎MRI：L3/4、L4/5椎管狭窄，硬膜囊受压，黄韧带肥厚",
      diagnosis: "腰椎管狭窄症（L3/4、L4/5）",
      treatment_plan: "先保守治疗1月：甲钴胺0.5mg tid营养神经+塞来昔布200mg qd消炎镇痛+腰背肌功能锻炼。1月后评估，保守无效考虑手术",
    },
    tags: ["腰椎管狭窄", "保守治疗"],
  },
];

export const MOCK_TASKS = [
  { id: 201, doctor_id: "mock_doctor", patient_id: 1, patient_name: "陈伟强", task_type: "imaging", title: "陈伟强 术后复查CT", content: "脑膜瘤术后第7天，头痛加剧，急查头颅CT排除再出血", status: "pending", due_at: "2026-03-27", created_at: "2026-03-27" },
  { id: 202, doctor_id: "mock_doctor", patient_id: 2, patient_name: "李复诊", task_type: "checkup", title: "李复诊 颈动脉超声", content: "TIA首发48h内完成颈动脉超声+头颅MRA血管评估", status: "pending", due_at: "2026-03-28", created_at: "2026-03-25" },
  { id: 203, doctor_id: "mock_doctor", patient_id: 3, patient_name: "王明", task_type: "imaging", title: "王明 术后复查DSA", content: "动脉瘤夹闭术后复查DSA评估夹闭效果", status: "pending", due_at: "2026-04-03", created_at: "2026-03-27" },
  { id: 204, doctor_id: "mock_doctor", patient_id: 4, patient_name: "张小红", task_type: "follow_up", title: "张小红 用药效果复查", content: "卡马西平2周疗效评估，观察疼痛控制情况及副作用", status: "pending", due_at: "2026-04-03", created_at: "2026-03-25" },
  { id: 205, doctor_id: "mock_doctor", patient_id: 5, patient_name: "刘建国", task_type: "follow_up", title: "刘建国 保守治疗1月评估", content: "腰椎管狭窄保守治疗1个月后评估疗效，决定是否手术", status: "pending", due_at: "2026-04-10", created_at: "2026-03-22" },
];

export const MOCK_SUGGESTIONS = [
  // Patient 1: 陈伟强 — 术后头痛加剧鉴别诊断
  { id: 301, record_id: 102, section: "differential", content: "术后迟发性颅内血肿", detail: "脑膜瘤术后第7天头痛加剧伴恶心，需首先排除迟发性硬膜外/硬膜下血肿。[KB-7]术后3-10天为迟发性血肿高发期，头痛进行性加剧是最重要的预警信号。", confidence: "高", decision: null, is_custom: false },
  { id: 302, record_id: 102, section: "differential", content: "术后脑水肿", detail: "开颅术后脑水肿可在术后数天内加重，表现为头痛加剧伴恶心。需CT评估水肿范围及中线移位情况。", confidence: "中", decision: null, is_custom: false },
  { id: 303, record_id: 102, section: "differential", content: "颅内感染", detail: "开颅术后颅内感染可表现为头痛加剧伴发热。需关注体温变化、颈强直等脑膜刺激征。", confidence: "低", decision: null, is_custom: false },
  { id: 304, record_id: 102, section: "workup", content: "急查头颅CT平扫", detail: "首选检查，快速排除术后再出血和脑水肿加重。重点观察术区有无新发血肿、中线移位程度。", urgency: "紧急", decision: null, is_custom: false },
  { id: 305, record_id: 102, section: "workup", content: "血常规+CRP", detail: "评估有无感染迹象，白细胞升高伴CRP升高提示颅内感染可能。", urgency: "常规", decision: null, is_custom: false },
  { id: 306, record_id: 102, section: "treatment", content: "甘露醇脱水降颅压", detail: "如CT示脑水肿加重或中线移位，20%甘露醇250ml q8h快速静滴，密切监测电解质。", intervention: "药物", decision: null, is_custom: false },
  { id: 307, record_id: 102, section: "treatment", content: "急诊手术清除血肿", detail: "如CT证实血肿量大（>30ml）或中线移位>5mm，需急诊手术清除血肿。", intervention: "手术", decision: null, is_custom: false },
  // Patient 2: 李复诊 — TIA检查建议
  { id: 401, record_id: 103, section: "workup", content: "颈动脉超声", detail: "TIA首发48h内必须完成颈动脉超声评估，排除颈动脉狭窄或不稳定斑块。[KB-5]TIA复查路径要求48h内完成血管评估。", urgency: "紧急", decision: null, is_custom: false },
  { id: 402, record_id: 103, section: "workup", content: "头颅MRA", detail: "无创评估颅内血管情况，排除大血管狭窄或闭塞，与颈动脉超声联合完成全面血管评估。", urgency: "紧急", decision: null, is_custom: false },
  { id: 403, record_id: 103, section: "workup", content: "心脏超声", detail: "排除心源性栓塞，特别是左房附壁血栓、卵圆孔未闭等。7天内完成。", urgency: "常规", decision: null, is_custom: false },
  { id: 404, record_id: 103, section: "differential", content: "大动脉粥样硬化型TIA", detail: "56岁女性，高血压+糖尿病，大动脉粥样硬化为最可能病因。颈动脉超声+MRA可明确。", confidence: "高", decision: null, is_custom: false },
  { id: 405, record_id: 103, section: "differential", content: "心源性栓塞型TIA", detail: "需排除房颤等心律失常导致的心源性栓塞。建议24h动态心电图。", confidence: "中", decision: null, is_custom: false },
];

export const MOCK_BRIEFING = {
  today_patients: 5,
  pending_tasks: 5,
  completed_tasks: 3,
  pending_reviews: 2,
  overdue_tasks: 1,
};

export const MOCK_CHAT_MESSAGES = [
  { role: "assistant", content: "医生好！👋\n直接说或输入患者信息，AI 会自动整理病历，您确认后保存。也可以🎤语音录入，或点击下方快捷指令。", ts: "2026-03-27T08:00:00" },
  { role: "user", content: "今日摘要", ts: "2026-03-27T08:00:05" },
  { role: "assistant", content: "📋 今日摘要\n\n📊 待处理任务：5 ✅ 已完成审核：3 🧑 管理患者：5\n\n⚠ 陈伟强术后头痛加剧，需紧急复查CT。李复诊TIA首发，明天完成颈动脉超声。", ts: "2026-03-27T08:00:08" },
  { role: "user", content: "查看陈伟强的病历", ts: "2026-03-27T08:01:00" },
  { role: "assistant", content: "陈伟强，男，42岁\n\n最近记录（2026-03-27）：\n主诉：术后头痛加剧伴恶心1天\n诊断：右额叶脑膜瘤术后（第7天）\n⚠ AI建议：急查头颅CT排除迟发性血肿", ts: "2026-03-27T08:01:05" },
  { role: "user", content: "王明恢复情况怎么样", ts: "2026-03-27T08:02:00" },
  { role: "assistant", content: "王明，男，71岁\n\n前交通动脉瘤夹闭术后第12天：\n头痛较前缓解，偶有轻微胀痛，意识清醒，肢体活动正常\nGCS 15分，切口愈合良好\n\n计划：下周复查DSA评估夹闭效果", ts: "2026-03-27T08:02:05" },
];

export const MOCK_INTERVIEW_FIELDS = {
  chief_complaint: "术后头痛加剧伴恶心1天",
  present_illness: "脑膜瘤术后第7天，昨日开始头痛较前明显加剧，今晨伴恶心1次",
  past_history: "3月20日行右额叶脑膜瘤开颅切除术",
  allergy_history: "无",
  family_history: "无特殊",
  personal_history: "不吸烟，偶尔饮酒",
};

export const MOCK_OVERDUE = [
  { id: 201, patient_name: "陈伟强", title: "术后复查CT", due: "03-27" },
];

export const MOCK_INTERVIEW_STATE = {
  session_id: "mock-session-001",
  status: "interviewing",
  progress: { filled: 6, total: 13, pct: 46 },
  collected: {
    chief_complaint: "术后头痛加剧伴恶心1天",
    present_illness: "脑膜瘤术后第7天，昨日开始头痛较前明显加剧，今晨伴恶心1次",
    past_history: "3月20日行右额叶脑膜瘤开颅切除术",
    allergy_history: "无",
    family_history: "无特殊",
    personal_history: "不吸烟，偶尔饮酒",
  },
  missing: ["physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis", "treatment_plan", "orders_followup", "marital_reproductive"],
  conversation: [
    { role: "assistant", content: "请描述患者的主诉（主要症状和持续时间）。" },
    { role: "user", content: "陈伟强 男 42岁 脑膜瘤术后7天 头痛加剧伴恶心" },
    { role: "assistant", content: "收到。3月20日行右额叶脑膜瘤手术，术后恢复情况如何？" },
    { role: "user", content: "术后前5天恢复正常，昨天开始头痛加重，今早恶心了一次，无呕吐" },
    { role: "assistant", content: "术后头痛加剧需警惕。请补充体格检查（GCS、瞳孔、肌力）和辅助检查结果。" },
  ],
  suggestions: ["急查头颅CT", "监测GCS评分变化", "甘露醇脱水备用"],
};

export const MOCK_CARRY_FORWARD = [
  { field: "past_history", label: "既往史", value: "3月20日行右额叶脑膜瘤开颅切除术（Simpson I级）", source_date: "2026-03-20" },
  { field: "allergy_history", label: "过敏史", value: "无", source_date: "2026-03-20" },
  { field: "family_history", label: "家族史", value: "无特殊", source_date: "2026-03-20" },
  { field: "personal_history", label: "个人史", value: "不吸烟，偶尔饮酒", source_date: "2026-03-20" },
];

export const MOCK_PATIENT_MESSAGES = [
  { id: 501, patient_id: 1, patient_name: "陈伟强", content: "张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？", source: "patient", triage_category: "escalation", created_at: "2026-03-27T08:30:00" },
  { id: 502, patient_id: 2, patient_name: "李复诊", content: "张医生，我想问下我下次检查是什么时候？需要做什么准备吗？", source: "patient", triage_category: "informational", created_at: "2026-03-27T09:15:00" },
  { id: 503, patient_id: 5, patient_name: "刘建国", content: "医生您好，我腰椎的问题能不能做腰椎穿刺检查一下？", source: "patient", triage_category: "informational", created_at: "2026-03-27T10:00:00" },
];

export const MOCK_KNOWLEDGE_ITEMS = [
  { id: 7, title: "术后头痛危险信号", summary: "先排除再出血，再评估颅压", text: "开颅术后头痛加剧需警惕：①迟发性颅内血肿（术后3-10天多见）②脑水肿加重③颅内感染。危险信号：头痛进行性加剧、伴恶心呕吐、一侧瞳孔散大、意识水平下降。处理：立即头颅CT平扫，必要时急诊手术。", source: "doctor", created_at: "2026-03-23", reference_count: 7 },
  { id: 5, title: "TIA复查路径", summary: "48h内颈动脉超声+MRA", text: "短暂性脑缺血发作（TIA）复查路径：①48h内完成颈动脉超声+头颅MRA评估血管狭窄②ABCD2评分≥4分需住院观察③7天内完善心脏超声排除心源性栓塞④启动抗血小板+他汀治疗⑤控制血压血糖等危险因素。", source: "doctor", created_at: "2026-03-22", reference_count: 2 },
  { id: 8, title: "随访安抚话术", summary: "先共情再给时间节点", text: "术后随访沟通要点：①先表达理解和共情（'您的担心是正常的'）②给出明确的观察指标和时间节点③告知哪些情况需要紧急就医④提供下次复查的具体安排⑤鼓励患者记录症状变化。避免过度安抚或过度警示。", source: "doctor", created_at: "2026-03-21", reference_count: 4 },
  { id: 1, text: "蛛网膜下腔出血（SAH）：突发剧烈头痛（雷击样），伴恶心呕吐、颈强直、意识障碍。Fisher分级指导治疗。Hunt-Hess分级评估预后。", source: "agent_auto", created_at: "2026-03-20", reference_count: 5 },
  { id: 9, text: "颅内压增高三联征：头痛、呕吐、视乳头水肿。儿童可见前囟膨隆。紧急CT排除占位。", source: "agent_auto", created_at: "2026-03-19", reference_count: 6 },
  { id: 2, text: "急性脑梗死：突发偏瘫、失语、视野缺损。NIHSS评分＞4分考虑溶栓或取栓。4.5h窗口期rtPA，24h窗口期机械取栓。", source: "doctor", created_at: "2026-03-18", reference_count: 3 },
  { id: 10, text: "脊髓压迫症：进行性双下肢无力、感觉平面、大小便障碍。MRI急查，外科会诊。", source: "doctor", created_at: "2026-03-17", reference_count: 2 },
  { id: 11, text: "重症肌无力危象：呼吸肌无力导致呼吸困难，吞咽困难加重。紧急插管准备，新斯的明试验。", source: "doctor", created_at: "2026-03-16", reference_count: 1 },
  { id: 3, text: "高血压患者首诊：必须询问头痛、头晕、视物模糊、胸闷。必须测量双上肢血压。询问家族史、用药依从性。", source: "doctor", created_at: "2026-03-15", reference_count: 8 },
  { id: 6, text: "腰椎穿刺术后护理要点：去枕平卧6小时、观察穿刺点渗液、监测头痛程度。鼓励饮水促进脑脊液恢复。", source: "upload:腰穿护理指南.pdf", created_at: "2026-03-12", reference_count: 3 },
  { id: 4, title: "高血压分级与危险分层", text: "高血压分级：1级（140-159/90-99）2级（160-179/100-109）3级（≥180/≥110）。危险分层：低危/中危/高危/很高危。", source: "agent_auto", created_at: "2026-03-10", reference_count: 12 },
];

export const MOCK_FIELD_LABELS = {
  chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

export const MOCK_SETTINGS_TEMPLATES = [
  { name: "神经外科门诊模板", desc: "包含GCS评分、瞳孔检查、肌力分级、病理反射等神经系统查体", badge: "默认" },
  { name: "开颅术后随访模板", desc: "术后恢复评估：切口愈合、颅内压监测、并发症筛查、复查计划" },
  { name: "脊柱外科模板", desc: "腰椎/颈椎病历：疼痛评分、神经根定位体征、影像学分级" },
];
