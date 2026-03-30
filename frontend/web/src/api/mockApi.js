import {
  MOCK_DOCTOR,
  MOCK_PATIENTS,
  MOCK_RECORDS,
  MOCK_TASKS,
  MOCK_SUGGESTIONS,
  MOCK_BRIEFING,
  MOCK_OVERDUE,
  MOCK_INTERVIEW_STATE,
  MOCK_PATIENT_MESSAGES,
  MOCK_KNOWLEDGE_ITEMS,
  MOCK_SETTINGS_TEMPLATES,
} from "../pages/doctor/debug/MockData";

const INITIAL_DRAFT_MESSAGES = [
  {
    id: 101,
    patient_id: 1,
    patient_name: "陈伟强",
    patient_message: "张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？",
    draft_text: "陈先生，您术后头痛加剧伴恶心需要高度重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。如果出现剧烈头痛、呕吐或意识不清，请立即拨打120。",
    original_draft_text: "陈先生，您术后头痛加剧伴恶心需要高度重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。如果出现剧烈头痛、呕吐或意识不清，请立即拨打120。",
    cited_knowledge_ids: [7],
    cited_rules: [{ id: 7, title: "术后头痛危险信号" }],
    confidence: 0.95,
    status: "generated",
    ai_disclosure: "【此回复由AI辅助起草，经医生审核】",
    created_at: "2026-03-27T11:45:00",
    patient_context: "右额叶脑膜瘤术后第7天",
    time: "今天 11:45",
    badge: "urgent",
    rule_cited: "术后头痛危险信号",
  },
  {
    id: 102,
    patient_id: 2,
    patient_name: "李复诊",
    patient_message: "张医生，我想问下我下次检查是什么时候？需要做什么准备吗？",
    draft_text: "李女士您好，根据您TIA的情况，明天需要做颈动脉超声检查，评估颈部血管情况。检查前无需空腹，正常饮食即可。同时还会安排头颅MRA检查。请按时服用阿司匹林和氯吡格雷，不要自行停药。",
    original_draft_text: "李女士您好，根据您TIA的情况，明天需要做颈动脉超声检查，评估颈部血管情况。检查前无需空腹，正常饮食即可。同时还会安排头颅MRA检查。请按时服用阿司匹林和氯吡格雷，不要自行停药。",
    cited_knowledge_ids: [5],
    cited_rules: [{ id: 5, title: "TIA复查路径" }],
    confidence: 0.90,
    status: "generated",
    ai_disclosure: "【此回复由AI辅助起草，经医生审核】",
    created_at: "2026-03-27T13:10:00",
    patient_context: "TIA首发48小时",
    time: "今天 13:10",
    badge: "new",
    rule_cited: "TIA复查路径",
  },
  {
    id: 103,
    patient_id: 3,
    patient_name: "王明",
    patient_message: "张医生，我术后第12天了，今天还是有点隐隐头痛，这个正常吗？",
    draft_text: "王先生您好，动脉瘤夹闭术后第12天仍有轻微头痛属于正常恢复过程，不必过于担心。请注意观察：如果头痛突然加剧、伴呕吐或意识模糊，请立即就医。下周我们安排DSA复查，评估夹闭效果。",
    original_draft_text: "王先生您好，动脉瘤夹闭术后第12天仍有轻微头痛属于正常恢复过程，不必过于担心。请注意观察：如果头痛突然加剧、伴呕吐或意识模糊，请立即就医。下周我们安排DSA复查，评估夹闭效果。",
    cited_knowledge_ids: [7],
    cited_rules: [{ id: 7, title: "术后头痛危险信号" }],
    confidence: 0.92,
    status: "generated",
    ai_disclosure: "【此回复由AI辅助起草，经医生审核】",
    created_at: "2026-03-27T13:25:00",
    patient_context: "前交通动脉瘤夹闭术后第12天",
    time: "今天 13:25",
    badge: "new",
    rule_cited: "术后头痛危险信号",
  },
  {
    id: 104,
    patient_id: 5,
    patient_name: "刘建国",
    patient_message: "医生您好，我腰椎的问题能不能做腰椎穿刺检查一下？",
    draft_text: "刘先生您好，腰椎管狭窄的诊断主要依靠MRI检查，目前您的MRI已经明确了L3/4、L4/5狭窄的情况。腰椎穿刺一般用于排除感染或测量脑脊液压力，对您目前的情况不是必要的检查。建议先继续保守治疗方案，4月10日来院评估疗效。",
    original_draft_text: "刘先生您好，腰椎管狭窄的诊断主要依靠MRI检查，目前您的MRI已经明确了L3/4、L4/5狭窄的情况。腰椎穿刺一般用于排除感染或测量脑脊液压力，对您目前的情况不是必要的检查。建议先继续保守治疗方案，4月10日来院评估疗效。",
    cited_knowledge_ids: [6],
    cited_rules: [{ id: 6, title: "腰椎穿刺术后护理要点" }],
    confidence: 0.88,
    status: "generated",
    ai_disclosure: "【此回复由AI辅助起草，经医生审核】",
    created_at: "2026-03-27T13:20:00",
    patient_context: "腰椎管狭窄保守治疗中",
    time: "今天 13:20",
    badge: "new",
    rule_cited: "腰椎穿刺术后护理要点",
  },
];

// ── Mutable state (resets on page refresh) ──
let patients = [...MOCK_PATIENTS];
let records = [...MOCK_RECORDS];
let tasks = [...MOCK_TASKS];
let suggestions = [...MOCK_SUGGESTIONS];
let knowledgeItems = [...MOCK_KNOWLEDGE_ITEMS];
let patientMessages = [...MOCK_PATIENT_MESSAGES];
let draftMessages = INITIAL_DRAFT_MESSAGES.map((draft) => ({
  ...draft,
  cited_knowledge_ids: [...(draft.cited_knowledge_ids || [])],
  cited_rules: [...(draft.cited_rules || [])],
}));
let nextMockMessageId = 900;
let previewSessions = {};

// ── Read operations ──

export async function getBriefing() {
  return {
    stats: MOCK_BRIEFING,
    cards: MOCK_OVERDUE.map((t) => ({
      type: "urgent",
      title: `${t.patient_name} ${t.title}`,
      context: t.due,
    })),
  };
}

export async function getPatients() {
  return { items: patients };
}

export async function searchPatients(doctorId, q) {
  const filtered = patients.filter((p) => p.name.includes(q));
  return { items: filtered };
}

export async function getRecords({ doctorId, patientId, limit = 100 }) {
  const filtered = patientId
    ? records.filter((r) => r.patient_id === patientId)
    : records;
  return { items: filtered.slice(0, limit) };
}

export async function getTasks(doctorId, status = null) {
  const filtered = status
    ? tasks.filter((t) => {
        if (status === "completed") return t.status === "done" || t.status === "completed";
        if (status === "cancelled") return t.status === "cancelled";
        return t.status === status;
      })
    : tasks;
  return { items: filtered };
}

export async function getTaskById(taskId, doctorId) {
  const task = tasks.find((t) => t.id === Number(taskId));
  if (!task) return null;
  const patient = task.patient_id
    ? patients.find((p) => p.id === task.patient_id)
    : null;
  return {
    ...task,
    patient_name: patient?.name || task.patient_name || null,
    notes: task.notes || null,
    reminder_at: task.reminder_at || null,
    completed_at: task.completed_at || null,
    source_type: task.source_type || null,
  };
}

export async function getTaskRecord(recordId) {
  return records.find((r) => r.id === Number(recordId)) || null;
}

export async function getSuggestions(recordId) {
  return { suggestions: suggestions.filter((s) => s.record_id === Number(recordId)) };
}

export async function getKnowledgeItems() {
  // Real API: GET /api/manage/knowledge → { items: [{ id, text, source, confidence, category, title, summary, created_at }] }
  // Ensure every item has the fields the real API returns
  const sorted = [...knowledgeItems]
    .map((item) => ({
      title: "",
      summary: "",
      category: "custom",
      confidence: 1.0,
      ...item,
    }))
    .sort((a, b) =>
      (b.created_at || "").localeCompare(a.created_at || "")
    );
  return { items: sorted };
}

export async function getDoctorProfile() {
  return { name: MOCK_DOCTOR.doctorName, specialty: MOCK_DOCTOR.specialty, onboarded: true };
}

export async function getTemplateStatus() {
  return { templates: MOCK_SETTINGS_TEMPLATES, hasCustom: false };
}

export async function getPatientChat(patientId) {
  const filtered = patientId
    ? patientMessages.filter((message) => String(message.patient_id) === String(patientId))
    : patientMessages;
  return {
    messages: [...filtered].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "")),
  };
}

export async function getPatientTimeline({ patientId }) {
  return { items: records.filter((r) => r.patient_id === patientId) };
}

// ── Write operations ──

export async function createTask(doctorId, data) {
  const newTask = {
    id: Date.now(),
    doctor_id: doctorId,
    status: "pending",
    created_at: new Date().toISOString().slice(0, 10),
    ...data,
  };
  tasks = [...tasks, newTask];
  return newTask;
}

export async function patchTask(taskId, doctorId, status) {
  tasks = tasks.map((t) => (t.id === taskId ? { ...t, status } : t));
  return {};
}

export async function postponeTask(taskId, doctorId, dueAt) {
  tasks = tasks.map((t) => (t.id === taskId ? { ...t, due_at: dueAt } : t));
  return {};
}

export async function patchTaskNotes(taskId, doctorId, notes) {
  tasks = tasks.map((t) => (t.id === Number(taskId) ? { ...t, notes } : t));
  return {};
}

export async function decideSuggestion(suggestionId, decision, opts = {}) {
  // Real API: POST /api/doctor/suggestions/{suggestion_id}/decide →
  //   { status: "ok", id: int, decision: str, teach_prompt?: bool, edit_id?: int }
  suggestions = suggestions.map((s) =>
    s.id === suggestionId ? { ...s, decision, ...opts } : s
  );
  return { status: "ok", id: suggestionId, decision };
}

export async function addSuggestion(recordId, doctorId, section, content, detail) {
  const newSuggestion = {
    id: Date.now(),
    record_id: Number(recordId),
    section,
    content,
    detail: detail || "",
    decision: null,
    is_custom: true,
  };
  suggestions = [...suggestions, newSuggestion];
  return newSuggestion;
}

export async function addKnowledgeItem(doctorId, content) {
  const newItem = {
    id: Date.now(),
    text: content,
    content,
    source: "doctor",
    created_at: new Date().toISOString().slice(0, 10),
    reference_count: 0,
  };
  knowledgeItems = [...knowledgeItems, newItem];
  return newItem;
}

export async function updateKnowledgeItem(_doctorId, itemId, text, title) {
  const item = knowledgeItems.find((i) => i.id === itemId);
  if (item) {
    item.content = text;
    item.text = text;
    if (title !== undefined) item.title = title;
  }
  return { status: "ok", id: itemId };
}

export async function deleteKnowledgeItem(doctorId, itemId) {
  knowledgeItems = knowledgeItems.filter((i) => i.id !== itemId);
  return {};
}

export async function uploadKnowledgeExtract(_doctorId, file) {
  await new Promise((r) => setTimeout(r, 800)); // simulate network
  return {
    extracted_text: `（模拟提取）${file.name} 的内容摘要：\n\n本文件包含临床诊疗指南相关内容，建议医生在相关场景中参考使用。`,
    source_filename: file.name,
    llm_processed: true,
  };
}

export async function uploadKnowledgeSave(doctorId, text, sourceFilename) {
  const newItem = {
    id: Date.now(),
    text,
    content: text,
    source: `upload:${sourceFilename}`,
    created_at: new Date().toISOString().slice(0, 10),
    reference_count: 0,
  };
  knowledgeItems = [...knowledgeItems, newItem];
  return newItem;
}

export async function processKnowledgeText(_doctorId, text) {
  await new Promise((r) => setTimeout(r, 600)); // simulate network
  const trimmed = (text || "").trim();
  if (trimmed.length >= 500) {
    const processed = `（AI整理）${trimmed.slice(0, 200)}...\n\n以上内容已由AI整理，保留了核心临床要点。`;
    return {
      processed_text: processed,
      original_length: trimmed.length,
      processed_length: processed.length,
      llm_processed: true,
    };
  }
  return {
    processed_text: trimmed,
    original_length: trimmed.length,
    processed_length: trimmed.length,
    llm_processed: false,
  };
}

export async function fetchKnowledgeUrl(_doctorId, url) {
  await new Promise((r) => setTimeout(r, 800));
  const mockText = `（AI整理）从 ${url} 提取的内容摘要\n\n这是一篇关于临床指南的文章，主要内容包括诊断标准、治疗方案和随访建议。`;
  return {
    extracted_text: mockText,
    source_url: url,
    char_count: mockText.length,
    llm_processed: true,
  };
}

export async function getKnowledgeBatch(_doctorId, ids) {
  return { items: knowledgeItems.filter((i) => ids.includes(i.id)) };
}

export async function deletePatient(patientId) {
  patients = patients.filter((p) => p.id !== patientId);
  return {};
}

export async function deleteRecord(doctorId, recordId) {
  records = records.filter((r) => r.id !== recordId);
  return {};
}

export async function updateRecord(doctorId, recordId, fields) {
  records = records.map((r) => (r.id === recordId ? { ...r, ...fields } : r));
  return records.find((r) => r.id === recordId);
}

export async function updateDoctorProfile(doctorId, data) {
  return { ...data };
}

export async function createOnboardingPatientEntry(_doctorId, { patientName, gender, age } = {}) {
  const trimmedName = (patientName || "").trim();
  if (!trimmedName) throw new Error("patient_name is required");
  let patient = patients.find((item) => item.name === trimmedName);
  let created = false;
  if (!patient) {
    patient = {
      id: Math.max(0, ...patients.map((p) => Number(p.id) || 0)) + 1,
      name: trimmedName,
      gender: gender || null,
      year_of_birth: age ? new Date().getFullYear() - age : null,
      created_at: new Date().toISOString(),
      last_activity_at: null,
      record_count: 0,
    };
    patients = [patient, ...patients];
    created = true;
  }
  return {
    status: "ok",
    patient_id: patient.id,
    patient_name: patient.name,
    created,
    portal_token: `mock-patient-${patient.id}`,
    portal_url: `http://localhost:5173/patient?token=mock-patient-${patient.id}`,
    expires_in_days: 30,
  };
}

export async function ensureOnboardingExamples() {
  return {
    status: "ok",
    knowledge_item_id: 7,
    diagnosis_record_id: 102,
    reply_draft_id: 101,
    reply_message_id: 201,
  };
}

// ── Complex flows (canned responses) ──

export async function sendChat(payload) {
  const text = (payload.text || payload.message || "");
  if (text.includes("总结") || text.includes("最近情况")) {
    return {
      reply: "**陈伟强 临床总结**\n\n**基本信息：** 男，42岁\n\n**主要诊断：** 右额叶脑膜瘤（WHO I级）\n\n**手术记录：**\n- 2026-03-20 开颅脑膜瘤切除术（Simpson I级切除）\n\n**当前状态：** 术后第7天，今日头痛加剧伴恶心\n\n**注意事项：** ⚠ 需急查头颅CT排除迟发性血肿",
      view_payload: {
        records: [
          { id: 101, patient_id: 1, patient_name: "陈伟强", chief_complaint: "右额叶占位性病变", record_type: "visit", created_at: "2026-03-20" },
          { id: 102, patient_id: 1, patient_name: "陈伟强", chief_complaint: "术后头痛加剧伴恶心1天", record_type: "interview_summary", created_at: "2026-03-27" },
        ],
      },
    };
  }
  if (text.includes("患者") || text.includes("查询")) {
    return {
      reply: "找到 5 位患者：",
      view_payload: {
        patients: [
          { id: 1, name: "陈伟强", gender: "male", age: 42 },
          { id: 2, name: "李复诊", gender: "female", age: 56 },
          { id: 3, name: "王明", gender: "male", age: 71 },
          { id: 4, name: "张小红", gender: "female", age: 36 },
          { id: 5, name: "刘建国", gender: "male", age: 58 },
        ],
      },
    };
  }
  if (text.includes("任务") || text.includes("今日")) {
    return {
      reply: "您有 5 个待办任务，其中1个紧急：",
      view_payload: {
        tasks: [
          { id: 201, title: "陈伟强 术后复查CT", task_type: "imaging", due_at: "2026-03-27", status: "pending" },
          { id: 202, title: "李复诊 颈动脉超声", task_type: "checkup", due_at: "2026-03-28", status: "pending" },
          { id: 203, title: "王明 术后复查DSA", task_type: "imaging", due_at: "2026-04-03", status: "pending" },
          { id: 204, title: "张小红 用药效果复查", task_type: "follow_up", due_at: "2026-04-03", status: "pending" },
          { id: 205, title: "刘建国 保守治疗1月评估", task_type: "follow_up", due_at: "2026-04-10", status: "pending" },
        ],
      },
    };
  }
  if (text.includes("病历") || text.includes("记录")) {
    return {
      reply: "找到最近的病历记录：",
      view_payload: {
        records: [
          { id: 102, patient_id: 1, patient_name: "陈伟强", chief_complaint: "术后头痛加剧伴恶心1天", record_type: "interview_summary", created_at: "2026-03-27" },
          { id: 105, patient_id: 3, patient_name: "王明", chief_complaint: "术后恢复中，轻微头痛", record_type: "visit", created_at: "2026-03-27" },
          { id: 103, patient_id: 2, patient_name: "李复诊", chief_complaint: "右侧肢体无力20分钟自行缓解", record_type: "visit", created_at: "2026-03-25" },
        ],
      },
    };
  }
  return {
    reply: "这是模拟回复。Mock mode 不支持真实对话。\n\n试试输入「查询患者」「今日任务」或「查病历」看看消息卡片。",
    records: [],
    tasks: [],
  };
}

export async function doctorInterviewGetSession(sessionId) {
  return MOCK_INTERVIEW_STATE;
}

export async function doctorInterviewTurn() {
  return {
    ...MOCK_INTERVIEW_STATE,
    conversation: [
      ...MOCK_INTERVIEW_STATE.conversation,
      { role: "assistant", content: "收到。请继续补充信息。" },
    ],
  };
}

export async function doctorInterviewConfirm() {
  return { record_id: 999, status: "confirmed" };
}

export async function doctorInterviewCancel() {
  return {};
}

export async function interviewStart(token) {
  const patientId = Number(String(token || "").split("-").pop()) || 1;
  const patient = patients.find((item) => Number(item.id) === patientId);
  const sessionId = `preview-${patientId}`;
  previewSessions[sessionId] = {
    patientId,
    patientName: patient?.name || "患者",
    turn: 0,
    collected: {},
  };
  return {
    session_id: sessionId,
    reply: `您好，我是医生的AI助手。请先说说${patient?.name || "患者"}这次最不舒服的症状。`,
    collected: {},
    progress: { filled: 0, total: 7 },
    status: "interviewing",
    ready_to_review: false,
    resumed: false,
  };
}

export async function interviewTurn(_token, sessionId, text) {
  const session = previewSessions[sessionId] || {
    patientId: 1,
    patientName: "患者",
    turn: 0,
    collected: {},
  };
  const nextTurn = session.turn + 1;
  let reply = "我已经记录下来，请继续补充。";
  let suggestions = [];
  let progress = { filled: Math.min(nextTurn * 2, 7), total: 7 };
  let status = "interviewing";
  let collected = { ...(session.collected || {}) };

  if (nextTurn === 1) {
    collected = {
      ...collected,
      chief_complaint: text || "术后头痛伴恶心",
      present_illness: "头痛逐渐加重，伴间断恶心呕吐。",
    };
    reply = "头痛持续多久了？有没有呕吐、肢体无力或说话含糊？";
    suggestions = ["伴恶心呕吐", "无肢体无力", "今天加重"];
    progress = { filled: 2, total: 7 };
  } else if (nextTurn === 2) {
    collected = {
      ...collected,
      past_history: "近期有开颅手术史。",
      allergy_history: "否认明确药物过敏。",
      family_history: "无特殊。",
    };
    reply = "既往做过什么手术？平时有高血压、糖尿病或长期用药吗？";
    suggestions = ["术后第7天", "平时血压偏高", "无糖尿病"];
    progress = { filled: 5, total: 7 };
  } else {
    collected = {
      ...collected,
      personal_history: "无吸烟饮酒嗜好。",
      marital_reproductive: "已婚。",
    };
    reply = "好的，我已整理完主要信息。请确认后提交给医生审核。";
    progress = { filled: 7, total: 7 };
    status = "reviewing";
  }

  previewSessions[sessionId] = {
    ...session,
    turn: nextTurn,
    collected,
  };

  return {
    reply,
    collected,
    progress,
    status,
    ready_to_review: status === "reviewing",
    suggestions,
    missing_fields: [],
    complete: status === "reviewing",
  };
}

export async function interviewConfirm(token, sessionId) {
  const patientId = Number(String(token || "").split("-").pop()) || 1;
  const patient = patients.find((item) => Number(item.id) === patientId) || patients[0];
  const session = previewSessions[sessionId] || {};
  const recordId = Math.max(0, ...records.map((r) => Number(r.id) || 0)) + 1;
  const reviewId = Math.max(0, ...tasks.map((t) => Number(t.id) || 0)) + 1;
  const createdAt = new Date().toISOString();
  const chiefComplaint = session.collected?.chief_complaint || "术后头痛伴恶心";
  records = [
    {
      id: recordId,
      patient_id: patient.id,
      patient_name: patient.name,
      record_type: "interview_summary",
      status: "pending_review",
      created_at: createdAt,
      chief_complaint: chiefComplaint,
      structured: {
        chief_complaint: chiefComplaint,
        present_illness: session.collected?.present_illness || "头痛逐渐加重，伴恶心呕吐。",
        past_history: session.collected?.past_history || "近期有开颅手术史。",
        allergy_history: session.collected?.allergy_history || "否认明确药物过敏。",
        family_history: session.collected?.family_history || "无特殊。",
        personal_history: session.collected?.personal_history || "无吸烟饮酒嗜好。",
        marital_reproductive: session.collected?.marital_reproductive || "已婚。",
      },
      content: `主诉：${chiefComplaint}\n现病史：${session.collected?.present_illness || "头痛逐渐加重，伴恶心呕吐。"}`,
    },
    ...records,
  ];
  tasks = [
    {
      id: reviewId,
      doctor_id: "mock_doctor",
      patient_id: patient.id,
      record_id: recordId,
      task_type: "review",
      title: `审阅患者【${patient.name}】预问诊记录`,
      content: "患者已完成预问诊，请审阅病历记录。",
      status: "pending",
      due_at: null,
      created_at: createdAt,
      target: "doctor",
    },
    ...tasks,
  ];
  suggestions = [
    {
      id: Math.max(0, ...suggestions.map((s) => Number(s.id) || 0)) + 1,
      record_id: recordId,
      section: "differential",
      content: "术后颅内血肿或脑水肿",
      detail: "患者预问诊提示术后头痛加重伴恶心呕吐，需尽快排除术后并发症。",
      confidence: "高",
      urgency: "urgent",
      decision: null,
      cited_knowledge_ids: [7],
    },
    {
      id: Math.max(0, ...suggestions.map((s) => Number(s.id) || 0)) + 2,
      record_id: recordId,
      section: "workup",
      content: "尽快完成头颅CT平扫",
      detail: "必要时结合生命体征和神经系统查体。",
      urgency: "urgent",
      decision: null,
      cited_knowledge_ids: [7],
    },
    ...suggestions,
  ];
  return {
    status: "confirmed",
    record_id: recordId,
    review_id: reviewId,
    message: "您的预问诊信息已提交给医生，请等待医生审阅。",
  };
}

export async function interviewCancel() {
  return { status: "abandoned" };
}

export async function confirmCarryForward() {
  return {};
}

export async function updateInterviewField() {
  return {};
}

export async function triggerDiagnosis() {
  return { status: "pending" };
}

export async function finalizeReview(recordId) {
  const record = records.find((item) => Number(item.id) === Number(recordId));
  const patientId = record?.patient_id || 1;
  const patientName = patients.find((item) => Number(item.id) === Number(patientId))?.name || "患者";
  records = records.map((item) => (
    Number(item.id) === Number(recordId) ? { ...item, status: "completed" } : item
  ));
  const existingIds = tasks
    .filter((task) => Number(task.record_id) === Number(recordId) && task.task_type !== "review" && task.status === "pending")
    .map((task) => task.id);
  if (existingIds.length > 0) {
    return {
      status: "completed",
      record_id: Number(recordId),
      follow_up_task_ids: existingIds,
      follow_up_task_count: existingIds.length,
    };
  }
  const firstId = Math.max(0, ...tasks.map((t) => Number(t.id) || 0)) + 1;
  const createdAt = new Date().toISOString();
  const newTasks = [
    {
      id: firstId,
      doctor_id: "mock_doctor",
      patient_id: patientId,
      record_id: Number(recordId),
      task_type: "follow_up",
      title: `${patientName} 3天内复查症状变化`,
      content: "观察头痛、恶心是否继续加重。",
      status: "pending",
      due_at: "2026-03-30T09:00:00",
      created_at: createdAt,
      target: "doctor",
    },
    {
      id: firstId + 1,
      doctor_id: "mock_doctor",
      patient_id: patientId,
      record_id: Number(recordId),
      task_type: "checkup",
      title: `${patientName} 预约头颅CT复查`,
      content: "结合复诊情况安排影像复查。",
      status: "pending",
      due_at: "2026-03-31T09:00:00",
      created_at: createdAt,
      target: "doctor",
    },
  ];
  tasks = [...newTasks, ...tasks];
  return {
    status: "completed",
    record_id: Number(recordId),
    follow_up_task_ids: newTasks.map((item) => item.id),
    follow_up_task_count: newTasks.length,
  };
}

export async function clearContext() {
  return {};
}

export async function ocrImage() {
  return { text: "模拟OCR文本：患者陈伟强，男，42岁，右额叶脑膜瘤术后第7天，头痛加剧伴恶心。术前MRI示右额叶脑膜瘤4.2x3.8cm，3月20日行开颅切除术（Simpson I级）。" };
}

export async function extractFileForChat() {
  return { text: "模拟文件提取：出院小结内容。" };
}

export async function importToInterview() {
  return {
    session_id: "mock-import-session",
    fields: MOCK_INTERVIEW_STATE.collected,
  };
}

export async function textToInterview() {
  return {
    session_id: "mock-text-session",
    fields: MOCK_INTERVIEW_STATE.collected,
  };
}

export async function exportPatientPdf() {
  return {};
}

export async function exportOutpatientReport() {
  return {};
}

export async function uploadTemplate() {
  return {};
}

export async function deleteTemplate() {
  return {};
}

export async function replyToPatient(patientId, text) {
  const patient = patients.find((item) => String(item.id) === String(patientId));
  const createdAt = new Date().toISOString();
  patientMessages = [
    ...patientMessages,
    {
      id: nextMockMessageId++,
      patient_id: Number(patientId),
      patient_name: patient?.name || "患者",
      content: text,
      source: "doctor",
      created_at: createdAt,
    },
  ];
  draftMessages = draftMessages.map((draft) => (
    String(draft.patient_id) === String(patientId) && draft.status !== "sent"
      ? { ...draft, status: "sent", sent_at: createdAt }
      : draft
  ));
  return {};
}

export async function transcribeAudio() {
  return { text: "模拟语音转文字结果" };
}

// ── Knowledge stats, AI activity, drafts (MyAIPage) ──

export async function fetchKnowledgeStats() {
  // Real API: GET /api/manage/knowledge/stats → { stats: [{ knowledge_item_id, total_count, last_used }] }
  return {
    stats: [
      { knowledge_item_id: 7, total_count: 7, last_used: "2026-03-27T13:25:00" },  // 术后头痛危险信号 — patients 1,3
      { knowledge_item_id: 5, total_count: 2, last_used: "2026-03-27T13:10:00" },  // TIA复查路径 — patient 2
      { knowledge_item_id: 9, total_count: 6, last_used: "2026-03-26T11:00:00" },  // 颅内压增高三联征
      { knowledge_item_id: 1, total_count: 5, last_used: "2026-03-25T16:00:00" },  // 蛛网膜下腔出血
      { knowledge_item_id: 6, total_count: 3, last_used: "2026-03-27T13:20:00" },  // 腰椎穿刺术后护理 — patient 5
    ],
    // display-only, not in real API — convenience aggregates for dashboard
    citations_7d: 23,
    today_processed: 6,
    total_rules: 11,
  };
}

export async function fetchAIActivity() {
  // Real API: GET /api/manage/ai/activity → { activity: [{ type, description, patient_id, timestamp, record_id? }] }
  return {
    activity: [
      {
        type: "draft",
        description: "起草了安抚回复 — 术后轻微头痛属正常恢复",
        patient_id: 3,
        patient_name: "王明",
        timestamp: "2026-03-27T13:25:00",
      },
      {
        type: "draft",
        description: "起草了常规回复 — 建议先保守治疗",
        patient_id: 5,
        patient_name: "刘建国",
        timestamp: "2026-03-27T13:20:00",
      },
      {
        type: "citation",
        description: "回复中引用了「TIA复查路径」",
        patient_id: 2,
        patient_name: "李复诊",
        timestamp: "2026-03-27T13:10:00",
      },
      {
        type: "draft",
        description: "起草了常规回复 — 明天做颈动脉超声",
        patient_id: 2,
        patient_name: "李复诊",
        timestamp: "2026-03-27T13:05:00",
      },
      {
        type: "diagnosis",
        description: "生成鉴别诊断：术后迟发性血肿",
        patient_id: 1,
        patient_name: "陈伟强",
        record_id: 102,
        timestamp: "2026-03-27T12:00:00",
      },
      {
        type: "draft",
        description: "起草了紧急回复 — 建议急查头颅CT",
        patient_id: 1,
        patient_name: "陈伟强",
        timestamp: "2026-03-27T11:45:00",
      },
    ],
  };
}

export async function fetchDraftSummary() {
  // Real API: GET /api/manage/drafts/summary → { pending, ai_drafted, due_soon, review_pending_count }
  // pending=4 (patients 1,2,3,5), review_pending_count=2 (patients 1,2), recently_sent=2 (patients 4,5)
  return {
    pending: 4,
    review_pending_count: 2,
    today_processed: 6,
  };
}

export async function fetchAIAttention() {
  // Real API: GET /api/manage/patients/ai-attention → { patients: [{ patient_id, reason, urgency, type, record_id? }] }
  return {
    patients: [
      {
        patient_id: 1,
        patient_name: "陈伟强",
        reason: "术后头痛加剧伴恶心，需急查头颅CT排除再出血",
        urgency: "high",
        type: "due_task",
        short_tag: "紧急复查CT",
      },
      {
        patient_id: 2,
        patient_name: "李复诊",
        reason: "TIA首发48h内需完成颈动脉超声+MRA血管评估",
        urgency: "medium",
        type: "due_task",
        short_tag: "明天颈动脉超声",
      },
    ],
  };
}

export async function getReviewQueue() {
  return {
    summary: { pending: 2, confirmed: 2, modified: 1 },
    pending: [
      {
        id: "r1", record_id: 102, suggestion_id: 301,
        patient_id: 1, patient_name: "陈伟强", time: "今天 12:00",
        urgency: "urgent",
        section: "differential", content: "术后迟发性血肿",
        detail: "脑膜瘤术后第7天头痛加剧伴恶心，需排除迟发性硬膜外/硬膜下血肿，建议急查头颅CT平扫\n\n【类似病例参考】\n1. 相似度92% — 脑膜瘤开颅术后第6天头痛加剧 → 硬膜下血肿（治疗：急诊血肿清除术）\n2. 相似度85% — 开颅术后第8天恶心呕吐 → 术区脑水肿加重（治疗：甘露醇脱水+地塞米松）",
        rule_cited: "术后头痛危险信号",
      },
      {
        id: "r2", record_id: 103, suggestion_id: 401,
        patient_id: 2, patient_name: "李复诊", time: "今天 11:30",
        urgency: "pending",
        section: "workup", content: "颈动脉超声 + MRA",
        detail: "TIA首发，ABCD2评分4分，48h内需完成颈动脉超声+头颅MRA血管评估，排除大血管狭窄",
        rule_cited: "TIA复查路径",
      },
    ],
    completed: [
      { id: "c1", patient_id: 3, patient_name: "王明", content: "动脉瘤夹闭术后恢复评估", decision: "confirmed", rule_count: 1, time: "今天 08:30" },
      { id: "c2", patient_id: 4, patient_name: "张小红", content: "三叉神经痛 — 卡马西平治疗方案", decision: "confirmed", rule_count: 0, time: "3月25日" },
      { id: "c3", patient_id: 5, patient_name: "刘建国", content: "腰椎管狭窄 — 保守治疗方案", decision: "edited", detail: "你调整了塞来昔布用药剂量", time: "3月22日" },
    ],
  };
}

export async function fetchDrafts(_doctorId, { includeSent = false } = {}) {
  const visibleDrafts = includeSent
    ? draftMessages
    : draftMessages.filter((draft) => draft.status !== "sent");
  return {
    pending_messages: visibleDrafts,
    upcoming_followups: [],
    recently_sent: draftMessages
      .filter((draft) => draft.status === "sent")
      .map((draft) => ({
        id: draft.id,
        patient_id: draft.patient_id,
        patient_name: draft.patient_name,
        task: "回复消息",
        read_status: "未读",
        time: "刚刚",
      })),
  };
}

export async function sendDraft(draftId) {
  // Real API: POST /api/manage/drafts/{draft_id}/send → { status: "ok", message_id: int }
  await new Promise((r) => setTimeout(r, 400));
  const draft = draftMessages.find((item) => String(item.id) === String(draftId));
  const createdAt = new Date().toISOString();
  if (draft) {
    draftMessages = draftMessages.map((item) => (
      String(item.id) === String(draftId)
        ? { ...item, status: "sent", sent_at: createdAt }
        : item
    ));
    patientMessages = [
      ...patientMessages,
      {
        id: nextMockMessageId++,
        patient_id: draft.patient_id,
        patient_name: draft.patient_name,
        content: draft.draft_text,
        source: "doctor",
        created_at: createdAt,
      },
    ];
  }
  return { status: "ok", message_id: nextMockMessageId - 1 };
}
export async function editDraft(draftId, _doctorId, editedText) {
  // Real API: PUT /api/manage/drafts/{draft_id}/edit → { status: "ok", teach_prompt: bool, edit_id: int|null }
  await new Promise((r) => setTimeout(r, 300));
  draftMessages = draftMessages.map((draft) => (
    String(draft.id) === String(draftId)
      ? { ...draft, draft_text: editedText }
      : draft
  ));
  return { status: "ok", teach_prompt: false, edit_id: null };
}
export async function dismissDraft(draftId) {
  // Real API: POST /api/manage/drafts/{draft_id}/dismiss → { status: "ok" }
  return { status: "ok" };
}
export async function getDraftConfirmation(draftId) {
  // Real API: POST /api/manage/drafts/{draft_id}/send-confirmation →
  //   { draft_id, patient_name, patient_message, draft_text, ai_disclosure,
  //     full_text_preview, cited_rules: [{ id, title, text }], confidence, status }
  return {
    draft_id: draftId || 101,
    patient_name: "陈伟强",
    patient_message: "张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？",
    draft_text: "陈先生，您术后头痛加剧伴恶心需要高度重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。如果出现剧烈头痛、呕吐或意识不清，请立即拨打120。",
    ai_disclosure: "【此回复由AI辅助起草，经医生审核】",
    full_text_preview: "陈先生，您术后头痛加剧伴恶心需要高度重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。如果出现剧烈头痛、呕吐或意识不清，请立即拨打120。\n\n【此回复由AI辅助起草，经医生审核】",
    cited_rules: [
      { id: 7, title: "术后头痛危险信号", text: "开颅术后头痛加剧需警惕：迟发性颅内血肿（术后3-10天多见）、脑水肿加重、颅内感染。危险信号：头痛进行性加剧、伴恶心呕吐、一侧瞳孔散大、意识水平下降。" },
    ],
    confidence: 0.95,
    status: "generated",
    patient_context: "右额叶脑膜瘤术后第7天",
  };
}
export async function createRuleFromEdit() {
  // Real API: POST /api/manage/teaching/create-rule → { status: "ok", rule_id: int, title: str }
  return { status: "ok", rule_id: 99, title: "新规则" };
}

export async function fetchKnowledgeUsageHistory(doctorId, itemId) {
  // Real API: GET /api/manage/knowledge/{item_id}/usage →
  //   { usage: [{ id, usage_context, patient_id, record_id, created_at }] }
  // Return citations matching the patient stories. itemId determines which knowledge item.
  const usageMap = {
    // KB-7: 术后头痛危险信号 — cited for patients 1 and 3
    7: [
      {
        id: 1, usage_context: "diagnosis", patient_id: 1, record_id: 102,
        created_at: "2026-03-27T12:00:00",
        patient_name: "陈伟强", detail: "鉴别诊断：术后迟发性颅内血肿",
      },
      {
        id: 2, usage_context: "followup", patient_id: 3, record_id: null,
        created_at: "2026-03-27T13:25:00",
        patient_name: "王明", detail: "起草安抚回复：术后轻微头痛属正常恢复",
      },
      {
        id: 3, usage_context: "followup", patient_id: 1, record_id: null,
        created_at: "2026-03-27T11:45:00",
        patient_name: "陈伟强", detail: "起草紧急回复：建议急查头颅CT",
      },
    ],
    // KB-5: TIA复查路径 — cited for patient 2
    5: [
      {
        id: 4, usage_context: "followup", patient_id: 2, record_id: null,
        created_at: "2026-03-27T13:10:00",
        patient_name: "李复诊", detail: "起草回复：明天做颈动脉超声+MRA",
      },
      {
        id: 5, usage_context: "diagnosis", patient_id: 2, record_id: 103,
        created_at: "2026-03-27T11:30:00",
        patient_name: "李复诊", detail: "检查建议：48h内颈动脉超声+MRA",
      },
    ],
    // KB-6: 腰椎穿刺术后护理要点 — cited for patient 5
    6: [
      {
        id: 6, usage_context: "followup", patient_id: 5, record_id: null,
        created_at: "2026-03-27T13:20:00",
        patient_name: "刘建国", detail: "起草回复：腰椎穿刺非必要检查",
      },
    ],
  };
  return { usage: usageMap[itemId] || usageMap[7] };
}
