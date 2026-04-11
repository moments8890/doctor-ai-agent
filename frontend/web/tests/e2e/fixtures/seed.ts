/**
 * Seed helpers — hit the backend API directly to set up fixture state.
 *
 * Use these from specs when a workflow needs pre-existing data (e.g. the
 * review workflow needs a completed patient interview to review). Driving
 * the UI to create setup data is slow and flaky; API seeding is fast and
 * deterministic.
 *
 * All endpoints here mirror the paths the real frontend uses in
 * `frontend/web/src/api.js`. If you're changing these, cross-check against
 * that file first — the "/api/doctor/*" vs "/api/manage/*" split is easy to
 * get wrong and silent 404s are the hardest failure mode to debug.
 */
import type { APIRequestContext } from "@playwright/test";
import { API_BASE_URL, type TestDoctor, type TestPatient } from "./doctor-auth";

/** Doctor-session routes use Bearer auth; this keeps the pattern in one place. */
function doctorHeaders(doctor: TestDoctor): Record<string, string> {
  return {
    "Authorization": `Bearer ${doctor.token}`,
    "Content-Type": "application/json",
  };
}

function patientHeaders(patient: TestPatient): Record<string, string> {
  return {
    "Authorization": `Bearer ${patient.token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Add a knowledge item as the seeded doctor.
 *
 * Route: `POST /api/manage/knowledge?doctor_id=...` (api.js:842).
 * Body:  `{ content, category }` — the backend extracts the title from the
 *        first line of `content`, so a separate title field isn't needed.
 */
export async function addKnowledgeText(
  request: APIRequestContext,
  doctor: TestDoctor,
  content: string,
  category = "custom",
): Promise<{ id: string }> {
  const url = `${API_BASE_URL}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: { content, category },
  });
  if (!res.ok()) {
    throw new Error(`seed addKnowledgeText failed: ${res.status()} ${await res.text()}`);
  }
  return await res.json();
}

/**
 * Add a persona rule to one of the 5 field sections.
 *
 * Route: `POST /api/manage/persona/rules?doctor_id=...` (api.js:635).
 * Body:  `{ field, text }` — field is the persona section key.
 */
export async function addPersonaRule(
  request: APIRequestContext,
  doctor: TestDoctor,
  field: "reply_style" | "closing" | "structure" | "avoid" | "edits",
  text: string,
): Promise<{ id: string }> {
  const url = `${API_BASE_URL}/api/manage/persona/rules?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: { field, text },
  });
  if (!res.ok()) {
    throw new Error(`seed addPersonaRule failed: ${res.status()} ${await res.text()}`);
  }
  return await res.json();
}

/**
 * Run a patient through a full pre-interview session and return the created
 * record_id. Several workflows need a reviewable record to exist; this is the
 * fastest way to get one without driving the patient UI.
 *
 * Routes: `/api/patient/interview/{start, turn, confirm}` with patient Bearer
 *         auth (api.js:795-812).
 */
export async function completePatientInterview(
  request: APIRequestContext,
  patient: TestPatient,
  messages: string[] = [
    "头痛三天，血压160/100，有高血压病史",
    "今天早上量的",
    "之前吃过降压药但没坚持",
  ],
): Promise<{ recordId: string }> {
  const headers = patientHeaders(patient);

  const start = await request.post(`${API_BASE_URL}/api/patient/interview/start`, {
    headers,
  });
  if (!start.ok()) {
    throw new Error(`interview start failed: ${start.status()} ${await start.text()}`);
  }
  const { session_id } = await start.json();

  for (const text of messages) {
    const r = await request.post(`${API_BASE_URL}/api/patient/interview/turn`, {
      headers,
      data: { session_id, text },
    });
    if (!r.ok()) {
      throw new Error(`interview turn failed: ${r.status()} ${await r.text()}`);
    }
  }

  const confirm = await request.post(`${API_BASE_URL}/api/patient/interview/confirm`, {
    headers,
    data: { session_id },
  });
  if (!confirm.ok()) {
    throw new Error(`interview confirm failed: ${confirm.status()} ${await confirm.text()}`);
  }
  const body = await confirm.json();
  return { recordId: String(body.record_id) };
}

/**
 * Send a patient-side chat message so the doctor's 待回复 queue has a draft
 * to review.
 *
 * Route: `POST /api/patient/message` (singular, api.js:784). Not
 * `/api/patient/messages` — the plural form doesn't exist. Body: `{ text }`.
 */
export async function sendPatientMessage(
  request: APIRequestContext,
  patient: TestPatient,
  text: string,
): Promise<{ messageId: string }> {
  const res = await request.post(`${API_BASE_URL}/api/patient/message`, {
    headers: patientHeaders(patient),
    data: { text },
  });
  if (!res.ok()) {
    throw new Error(`seed sendPatientMessage failed: ${res.status()} ${await res.text()}`);
  }
  const body = await res.json();
  return { messageId: String(body.id || body.message_id || "") };
}

/**
 * Poll the drafts endpoint until the backend has generated an AI draft for a
 * given patient. The draft pipeline is async: sendPatientMessage returns
 * immediately, then the LLM runs out-of-band. Workflows that need to see the
 * draft in the doctor UI should call this before asserting.
 *
 * Route: `GET /api/manage/drafts?doctor_id=...&patient_id=...` (api.js:1013).
 */
export async function waitForDraft(
  request: APIRequestContext,
  doctor: TestDoctor,
  patientId: string,
  opts: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<void> {
  const timeoutMs = opts.timeoutMs ?? 30_000;
  const intervalMs = opts.intervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const qs = new URLSearchParams({
      doctor_id: doctor.doctorId,
      patient_id: patientId,
    });
    const res = await request.get(
      `${API_BASE_URL}/api/manage/drafts?${qs.toString()}`,
      { headers: doctorHeaders(doctor) },
    );
    if (res.ok()) {
      const body = await res.json();
      const drafts = Array.isArray(body) ? body : body?.drafts || body?.items || [];
      if (drafts.length > 0) return;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `waitForDraft timed out after ${timeoutMs}ms for patient_id=${patientId}`,
  );
}

/**
 * Poll the review queue until the AI has produced diagnosis suggestions for a
 * given record. Mirrors waitForDraft for the review workflow — suggestion
 * generation is async and the spec must not race it.
 *
 * Route: `GET /api/doctor/records/{id}/suggestions?doctor_id=...` (api.js:963).
 */
export async function waitForSuggestions(
  request: APIRequestContext,
  doctor: TestDoctor,
  recordId: string,
  opts: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<void> {
  const timeoutMs = opts.timeoutMs ?? 30_000;
  const intervalMs = opts.intervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const qs = new URLSearchParams({ doctor_id: doctor.doctorId });
    const res = await request.get(
      `${API_BASE_URL}/api/doctor/records/${recordId}/suggestions?${qs.toString()}`,
      { headers: doctorHeaders(doctor) },
    );
    if (res.ok()) {
      const body = await res.json();
      const suggestions = Array.isArray(body) ? body : body?.suggestions || body?.items || [];
      if (suggestions.length > 0) return;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `waitForSuggestions timed out after ${timeoutMs}ms for record_id=${recordId}`,
  );
}

/**
 * Create a patient-targeted task via the doctor task API.
 * Route: POST /api/manage/tasks?doctor_id=...
 */
export async function createPatientTask(
  request: APIRequestContext,
  doctor: TestDoctor,
  patientId: string,
  opts: { title?: string; taskType?: string; content?: string } = {},
): Promise<{ taskId: string }> {
  const url = `${API_BASE_URL}/api/manage/tasks?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: {
      task_type: opts.taskType || "follow_up",
      title: opts.title || "E2E测试随访任务",
      content: opts.content || "请按时复查",
      patient_id: parseInt(patientId, 10),
      target: "patient",
    },
  });
  if (!res.ok()) {
    throw new Error(`seed createPatientTask failed: ${res.status()} ${await res.text()}`);
  }
  const body = await res.json();
  return { taskId: String(body.id) };
}

/**
 * Send a doctor reply to a patient (creates a doctor-source message).
 * Route: POST /api/manage/patients/{patient_id}/reply?doctor_id=...
 */
export async function sendDoctorReply(
  request: APIRequestContext,
  doctor: TestDoctor,
  patientId: string,
  text: string,
): Promise<{ messageId: string }> {
  const url = `${API_BASE_URL}/api/manage/patients/${patientId}/reply?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: { text },
  });
  if (!res.ok()) {
    throw new Error(`seed sendDoctorReply failed: ${res.status()} ${await res.text()}`);
  }
  const body = await res.json();
  return { messageId: String(body.message_id || "") };
}
