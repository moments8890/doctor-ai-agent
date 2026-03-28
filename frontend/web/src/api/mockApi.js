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

// ── Mutable state (resets on page refresh) ──
let patients = [...MOCK_PATIENTS];
let records = [...MOCK_RECORDS];
let tasks = [...MOCK_TASKS];
let suggestions = [...MOCK_SUGGESTIONS];
let knowledgeItems = [...MOCK_KNOWLEDGE_ITEMS];

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

export async function getTaskRecord(recordId) {
  return records.find((r) => r.id === Number(recordId)) || null;
}

export async function getSuggestions(recordId) {
  return { suggestions: suggestions.filter((s) => s.record_id === Number(recordId)) };
}

export async function getKnowledgeItems() {
  const sorted = [...knowledgeItems].sort((a, b) =>
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

export async function getPatientChat() {
  return { messages: MOCK_PATIENT_MESSAGES };
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

export async function decideSuggestion(suggestionId, decision, opts = {}) {
  suggestions = suggestions.map((s) =>
    s.id === suggestionId ? { ...s, decision, ...opts } : s
  );
  return {};
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

// ── Complex flows (canned responses) ──

export async function sendChat(payload) {
  const text = (payload.text || payload.message || "");
  if (text.includes("总结") || text.includes("最近情况")) {
    return {
      reply: "**陈伟强 临床总结**\n\n**基本信息：** 男，42岁\n\n**主要诊断：**\n- 2026-03-26 主诉：头痛3天伴恶心呕吐，诊断：高血压\n- 2026-03-19 主诉：头晕反复发作1月\n\n**治疗经过：** 口服降压药（氨氯地平5mg qd），症状有所缓解\n\n**当前状态：** 最近一次就诊血压控制尚可，仍有间断头痛\n\n**注意事项：** ⚠ 需复查血常规和肝肾功能，监测血压变化",
      view_payload: {
        records: [
          { id: 1, patient_id: 1, patient_name: "陈伟强", chief_complaint: "头痛3天伴恶心呕吐", record_type: "visit", created_at: "2026-03-26" },
          { id: 2, patient_id: 1, patient_name: "陈伟强", chief_complaint: "头晕反复发作1月", record_type: "visit", created_at: "2026-03-19" },
        ],
      },
    };
  }
  if (text.includes("患者") || text.includes("查询")) {
    return {
      reply: "找到 2 位患者：",
      view_payload: {
        patients: [
          { id: 1, name: "陈伟强", gender: "male", age: 42 },
          { id: 3, name: "王明", gender: "male", age: 71 },
        ],
      },
    };
  }
  if (text.includes("任务") || text.includes("今日")) {
    return {
      reply: "您有 2 个待办任务：",
      view_payload: {
        tasks: [
          { id: 1, title: "复查血常规", task_type: "checkup", due_at: "2026-03-28T10:00", status: "pending" },
          { id: 2, title: "调整降压药剂量", task_type: "medication", due_at: "2026-03-29T09:00", status: "pending" },
        ],
      },
    };
  }
  if (text.includes("病历") || text.includes("记录")) {
    return {
      reply: "找到 2 条病历记录：",
      view_payload: {
        records: [
          { id: 1, patient_id: 1, patient_name: "陈伟强", chief_complaint: "头痛3天伴恶心呕吐", record_type: "visit", created_at: "2026-03-26" },
          { id: 2, patient_id: 3, patient_name: "王明", chief_complaint: "头晕反复发作1月", record_type: "visit", created_at: "2026-03-25" },
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

export async function confirmCarryForward() {
  return {};
}

export async function updateInterviewField() {
  return {};
}

export async function triggerDiagnosis() {
  return { status: "pending" };
}

export async function finalizeReview() {
  return { status: "reviewed" };
}

export async function clearContext() {
  return {};
}

export async function ocrImage() {
  return { text: "模拟OCR文本：患者张三，男，45岁，主诉头痛3天。" };
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

export async function replyToPatient() {
  return {};
}

export async function transcribeAudio() {
  return { text: "模拟语音转文字结果" };
}

// ── Knowledge stats, AI activity, drafts (MyAIPage) ──

export async function fetchKnowledgeStats() {
  return { citations_7d: 26, today_processed: 3, total_rules: 12 };
}

export async function fetchAIActivity() {
  return [
    { id: "a1", patient_name: "王建国", description: "按你的话术起草了随访回复", status: "pending" },
    { id: "a2", patient_name: "李阿姨", description: "诊断建议引用了 2 条规则", time_label: "10分钟前", rule_name: "术后头痛红旗" },
  ];
}

export async function fetchDraftSummary() {
  return {
    pending_reply: 2,
    ai_drafted: 3,
    upcoming: 4,
    today_processed: 3,
    // backward compat fields used by DoctorPage badge counts
    pending_count: 3,
    followup_count: 5,
  };
}

export async function fetchAIAttention() {
  return {
    patients: [
      { patient_id: 1, patient_name: "陈伟强", reason: "术后第7天 · 需复查CT", short_tag: "需复查CT", urgency: "urgent" },
      { patient_id: 2, patient_name: "李复诊", reason: "随访回复已起草 · 待你确认发送", short_tag: "回复已起草", urgency: "pending" },
    ],
  };
}

export async function getReviewQueue() {
  return {
    summary: { pending: 3, confirmed: 8, modified: 2 },
    pending: [
      {
        id: "r1", record_id: 102, suggestion_id: 301,
        patient_id: 1, patient_name: "陈伟强", time: "今天 14:32",
        urgency: "urgent",
        section: "differential", content: "术后迟发性血肿",
        detail: "术后第7天头痛加剧，需排除迟发性硬膜外/下血肿，建议急查头颅CT",
        rule_cited: "术后头痛红旗",
      },
      {
        id: "r2", record_id: 106, suggestion_id: 401,
        patient_id: 5, patient_name: "刘建国", time: "今天 14:08",
        urgency: "pending",
        section: "workup", content: "颈动脉超声 + MRA",
        detail: "首发TIA，ABCD2评分4分，48h内完成血管评估",
        rule_cited: "TIA复查路径",
      },
      {
        id: "r3", record_id: 102, suggestion_id: 303,
        patient_id: 1, patient_name: "陈伟强", time: "今天 13:45",
        urgency: "pending",
        section: "differential", content: "良性阵发性位置性眩晕",
        detail: "反复发作位置性头晕，Dix-Hallpike试验阳性可能",
        rule_cited: null,
      },
    ],
    completed: [
      { id: "c1", patient_name: "赵敏", content: "三叉神经痛药物方案", decision: "confirmed", rule_count: 1, time: "昨天" },
      { id: "c2", patient_name: "陈大伟", content: "腰椎管狭窄保守方案", decision: "edited", detail: "你调整了用药剂量", time: "3月25日" },
      { id: "c3", patient_name: "周小林", content: "颈椎间盘突出评估", decision: "confirmed", rule_count: 0, time: "3月24日" },
    ],
  };
}

export async function fetchDrafts() {
  return {
    pending_messages: [
      {
        id: "d1",
        patient_id: 5,
        patient_name: "刘明",
        patient_context: "眩晕症随访第3天",
        time: "今天 13:20",
        badge: "new",
        patient_message: "张医生您好，我昨天晚上又头晕了一次，大概持续了十几秒，翻身的时候发作的，需要去医院吗？",
        draft_text: "刘先生您好，根据您描述的情况（翻身时短暂头晕），考虑可能与体位变化有关。建议您先观察2-3天，如果发作频率增加或持续时间超过1分钟，请及时来院复查。",
        rule_cited: "随访安抚话术",
        status: "drafted",
      },
      {
        id: "d2",
        patient_id: 1,
        patient_name: "王建国",
        patient_context: "脑膜瘤术后第12天",
        time: "今天 11:45",
        badge: "urgent",
        patient_message: "张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？",
        draft_text: "王先生，您术后头痛加剧伴恶心需要重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。如果头痛突然加剧或出现呕吐，请立即拨打120。",
        rule_cited: "术后头痛红旗",
        status: "drafted",
      },
    ],
    upcoming_followups: [
      { id: "f1", patient_name: "王建国", task: "术后复查CT", detail: "脑膜瘤术后第7天常规复查", due_label: "今天", soon: true },
      { id: "f2", patient_name: "李阿姨", task: "颈动脉超声", detail: "TIA首发48h内血管评估", due_label: "明天", soon: true },
      { id: "f3", patient_name: "赵敏", task: "用药效果复查", detail: "卡马西平2周疗效评估", due_label: "4月3日", soon: false },
      { id: "f4", patient_name: "陈大伟", task: "腰椎复查", detail: "保守治疗1个月评估", due_label: "4月10日", soon: false },
    ],
    recently_sent: [
      { id: "s1", patient_name: "赵敏", task: "服药提醒", read_status: "已读", time: "昨天" },
      { id: "s2", patient_name: "周小林", task: "复查提醒", read_status: "未读", time: "3月25日" },
    ],
  };
}

export async function sendDraft(draftId) {
  await new Promise((r) => setTimeout(r, 400));
  return { success: true };
}
export async function editDraft(draftId, _doctorId, editedText) {
  await new Promise((r) => setTimeout(r, 300));
  return { success: true, edited_text: editedText };
}
export async function dismissDraft(draftId) {
  return { success: true };
}
export async function getDraftConfirmation(draftId) {
  return {
    patient_name: "王建国",
    patient_context: "脑膜瘤术后第12天",
    draft_text: "王先生，您术后头痛加剧伴恶心需要重视。请您尽快到医院急诊做一个头颅CT检查，排除术后出血可能。",
    rules_cited: ["术后头痛红旗"],
  };
}
export async function createRuleFromEdit() { return {}; }

export async function fetchKnowledgeUsageHistory(doctorId, itemId) {
  return {
    usage: [
      { id: 1, type: "diagnosis", patient_name: "王建国", context: "诊断审核", detail: "鉴别诊断：术后迟发性血肿", date: "2026-03-27", patient_id: "1", record_id: 101 },
      { id: 2, type: "followup", patient_name: "刘明", context: "随访回复", detail: "按此规则起草了回复", date: "2026-03-26", patient_id: "3" },
      { id: 3, type: "diagnosis", patient_name: "李复诊", context: "诊断审核", detail: "检查建议：急查头颅CT", date: "2026-03-25", patient_id: "2", record_id: 102 },
    ],
  };
}
