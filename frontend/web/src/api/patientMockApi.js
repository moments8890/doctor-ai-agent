import {
  MOCK_PATIENT,
  MOCK_RECORDS,
  MOCK_TASKS,
  MOCK_CHAT_MESSAGES,
  MOCK_INTAKE_STATE,
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
  return { ...record };
}

export async function getPatientTasks(token) {
  await delay();
  return tasks;
}

export async function getPatientTaskDetail(_token, taskId) {
  const all = await getPatientTasks(_token);
  const found = all.find((t) => String(t.id) === String(taskId));
  if (!found) {
    const err = new Error("Task not found");
    err.status = 404;
    throw err;
  }
  return found;
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

export async function uncompletePatientTask(token, taskId) {
  await delay();
  tasks = tasks.map((t) =>
    t.id === Number(taskId)
      ? { ...t, status: "pending", completed_at: null }
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

// ── Intake ──

export async function intakeStart(token) {
  await delay();
  return {
    session_id: MOCK_INTAKE_STATE.session_id,
    reply: MOCK_INTAKE_STATE.conversation[0].content,
    collected: {},
    progress: { filled: 0, total: 7 },
    status: "active",
    resumed: false,
  };
}

const MOCK_TURN_SEQUENCE = [
  { reply: "收到，主诉和现病史已记录。请问您有什么既往病史吗？比如高血压、糖尿病？", filled: 2, missing: ["past_history", "allergy_history", "family_history", "personal_history", "physical_exam"] },
  { reply: "好的，已记录。请问您有药物或食物过敏吗？", filled: 3, missing: ["allergy_history", "family_history", "personal_history", "physical_exam"] },
  { reply: "了解了。您的家族中有类似疾病史吗？", filled: 4, missing: ["family_history", "personal_history", "physical_exam"] },
  { reply: "谢谢。最后一个问题：您目前的生活习惯如何？吸烟、饮酒情况？", filled: 5, missing: ["personal_history", "physical_exam"] },
  { reply: "信息已收集完整，请确认提交。", filled: 7, missing: [], complete: true },
];
let _mockTurnIndex = 0;

export async function intakeTurn(token, sessionId, text) {
  await delay();
  const step = MOCK_TURN_SEQUENCE[Math.min(_mockTurnIndex, MOCK_TURN_SEQUENCE.length - 1)];
  _mockTurnIndex++;
  return {
    reply: step.reply,
    collected: { ...MOCK_INTAKE_STATE.collected },
    progress: { filled: step.filled, total: 7 },
    status: step.complete ? "confirming" : "active",
    suggestions: MOCK_INTAKE_STATE.suggestions,
    missing_fields: step.missing,
    complete: step.complete || false,
  };
}

export async function intakeConfirm(token, sessionId) {
  await delay();
  return { message: "病历已保存", record_id: 999 };
}

export async function intakeCancel(token, sessionId) {
  await delay();
  return { status: "cancelled" };
}

// ── Chat-intake confirm / per-field (mock) ──

export async function confirmIntake(token, sessionId) {
  await delay();
  return {
    status: "confirmed",
    session_id: sessionId,
    record_id: 999,
    message: "您的问诊信息已提交给医生，请等待医生审阅。",
  };
}

export async function updateIntakeFieldPatient(token, sessionId, field, newValue) {
  await delay();
  return { status: "ok", session_id: sessionId, field, value: newValue };
}

export async function confirmAllCarryForward(token, sessionId) {
  await delay();
  return { status: "ok", session_id: sessionId };
}
