import {
  MOCK_PATIENT,
  MOCK_RECORDS,
  MOCK_TASKS,
  MOCK_CHAT_MESSAGES,
  MOCK_INTERVIEW_STATE,
} from "../pages/patient/debug/MockData";

const delay = () => new Promise((r) => setTimeout(r, 100));

// ── Mutable state (resets on page refresh) ──
let tasks = [...MOCK_TASKS];

// ── Read operations ──

export async function getPatientMe(token) {
  await delay();
  return MOCK_PATIENT;
}

export async function getPatientRecords(token) {
  await delay();
  return MOCK_RECORDS;
}

export async function getPatientRecordDetail(token, recordId) {
  await delay();
  const record = MOCK_RECORDS.find((r) => r.id === Number(recordId));
  if (!record) return null;
  const { structured, ...rest } = record;
  return { ...rest, ...structured };
}

export async function getPatientTasks(token) {
  await delay();
  return tasks;
}

// ── Write operations ──

export async function completePatientTask(token, taskId) {
  await delay();
  tasks = tasks.map((t) =>
    t.id === Number(taskId)
      ? { ...t, status: "completed", completed_at: new Date().toISOString().slice(0, 10) }
      : t
  );
  return tasks.find((t) => t.id === Number(taskId)) || null;
}

// ── Chat ──

export async function getPatientChatMessages(token, sinceId) {
  await delay();
  if (sinceId) {
    return MOCK_CHAT_MESSAGES.filter((m) => m.id > Number(sinceId));
  }
  return MOCK_CHAT_MESSAGES;
}

export async function sendPatientChat(token, text) {
  await delay();
  return {
    reply: "这是模拟回复。Mock mode 不支持真实对话。",
    message_id: Date.now(),
  };
}

export async function sendPatientMessage(token, text) {
  await delay();
  return {
    reply: "这是模拟回复。Mock mode 不支持真实对话。",
    message_id: Date.now(),
  };
}

// ── Interview ──

export async function interviewStart(token) {
  await delay();
  return {
    session_id: MOCK_INTERVIEW_STATE.session_id,
    reply: MOCK_INTERVIEW_STATE.conversation[0].content,
    collected: {},
    progress: { filled: 0, total: 7 },
    status: "interviewing",
    resumed: false,
  };
}

export async function interviewTurn(token, sessionId, text) {
  await delay();
  return {
    reply: MOCK_INTERVIEW_STATE.reply,
    collected: MOCK_INTERVIEW_STATE.collected,
    progress: MOCK_INTERVIEW_STATE.progress,
    status: "interviewing",
    suggestions: MOCK_INTERVIEW_STATE.suggestions,
    missing_fields: [
      "past_history",
      "allergy_history",
      "family_history",
      "personal_history",
      "physical_exam",
    ],
    complete: false,
  };
}

export async function interviewConfirm(token, sessionId) {
  await delay();
  return { message: "病历已保存", record_id: 999 };
}

export async function interviewCancel(token, sessionId) {
  await delay();
  return { status: "cancelled" };
}
