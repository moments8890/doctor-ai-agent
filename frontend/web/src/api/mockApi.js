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
