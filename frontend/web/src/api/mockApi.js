import {
  MOCK_DOCTOR,
  MOCK_PATIENTS,
  MOCK_RECORDS,
  MOCK_TASKS,
  MOCK_SUGGESTIONS,
  MOCK_BRIEFING,
  MOCK_CHAT_MESSAGES,
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
  return { items: knowledgeItems };
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

export async function addKnowledgeItem(doctorId, content, category = "custom") {
  const newItem = {
    id: Date.now(),
    category,
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
  return {
    reply: "这是模拟回复。Mock mode 不支持真实对话。",
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

export async function getWorkingContext() {
  return { messages: MOCK_CHAT_MESSAGES };
}
