/**
 * Seed helpers — hit the backend API directly to set up fixture state.
 *
 * Use these from specs when a workflow needs pre-existing data (e.g. the
 * review workflow needs a completed patient interview to review). Driving
 * the UI to create setup data is slow and flaky; API seeding is fast and
 * deterministic.
 */
import type { APIRequestContext } from "@playwright/test";
import { API_BASE_URL, type TestDoctor, type TestPatient } from "./doctor-auth";

export async function addKnowledgeText(
  request: APIRequestContext,
  doctor: TestDoctor,
  text: string,
  title = "E2E 知识条目",
): Promise<{ id: string }> {
  const res = await request.post(`${API_BASE_URL}/api/doctor/knowledge`, {
    headers: { Authorization: `Bearer ${doctor.token}` },
    data: { title, content: text, source: "text" },
  });
  if (!res.ok()) throw new Error(`seed knowledge failed: ${await res.text()}`);
  return await res.json();
}

export async function addPersonaRule(
  request: APIRequestContext,
  doctor: TestDoctor,
  field: "reply_style" | "closing" | "structure" | "avoid" | "edits",
  text: string,
): Promise<{ id: string }> {
  const res = await request.post(
    `${API_BASE_URL}/api/doctor/persona/${field}/rules`,
    {
      headers: { Authorization: `Bearer ${doctor.token}` },
      data: { text },
    },
  );
  if (!res.ok()) throw new Error(`seed persona rule failed: ${await res.text()}`);
  return await res.json();
}

/**
 * Run a patient through a full pre-interview session and return the created
 * record_id. Several workflows need a reviewable record to exist; this is the
 * fastest way to get one without driving the patient UI.
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
  const auth = { Authorization: `Bearer ${patient.token}` };

  const start = await request.post(
    `${API_BASE_URL}/api/patient/interview/start`,
    { headers: auth },
  );
  if (!start.ok()) throw new Error(`interview start: ${await start.text()}`);
  const { session_id } = await start.json();

  for (const text of messages) {
    const r = await request.post(
      `${API_BASE_URL}/api/patient/interview/turn`,
      { headers: auth, data: { session_id, text } },
    );
    if (!r.ok()) throw new Error(`interview turn: ${await r.text()}`);
  }

  const confirm = await request.post(
    `${API_BASE_URL}/api/patient/interview/confirm`,
    { headers: auth, data: { session_id } },
  );
  if (!confirm.ok()) throw new Error(`interview confirm: ${await confirm.text()}`);
  const body = await confirm.json();
  return { recordId: body.record_id };
}

/**
 * Post a patient message to the doctor so the "待回复" tab has a draft to review.
 */
export async function sendPatientMessage(
  request: APIRequestContext,
  patient: TestPatient,
  text: string,
): Promise<{ messageId: string }> {
  const res = await request.post(`${API_BASE_URL}/api/patient/messages`, {
    headers: { Authorization: `Bearer ${patient.token}` },
    data: { text },
  });
  if (!res.ok()) throw new Error(`seed patient message failed: ${await res.text()}`);
  return await res.json();
}
