async function readError(response) {
  const text = await response.text();
  return text || `HTTP ${response.status}`;
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function sendChat(payload) {
  return request("/api/records/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getPatients(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients?${qs.toString()}`);
}

export async function getRecords({ doctorId, patientId }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (patientId) qs.set("patient_id", patientId);
  return request(`/api/manage/records?${qs.toString()}`);
}

export async function getPrompts() {
  return request("/api/manage/prompts");
}

export async function updatePrompt(key, content) {
  return request(`/api/manage/prompts/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}
