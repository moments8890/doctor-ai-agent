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

export async function getPatients(doctorId, filters = {}) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (filters.category) qs.set("category", filters.category);
  if (filters.risk) qs.set("risk", filters.risk);
  if (filters.followUpState) qs.set("follow_up_state", filters.followUpState);
  if (filters.staleRisk !== undefined && filters.staleRisk !== null && filters.staleRisk !== "") {
    qs.set("stale_risk", String(filters.staleRisk));
  }
  return request(`/api/manage/patients?${qs.toString()}`);
}

export async function getRecords({ doctorId, patientId, patientName, dateFrom, dateTo }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (patientId) qs.set("patient_id", patientId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
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

export async function getPatientTimeline({ doctorId, patientId, limit = 100 }) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit) });
  return request(`/api/manage/patients/${patientId}/timeline?${qs.toString()}`);
}

export async function getLabels(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/labels?${qs.toString()}`);
}

export async function createLabel({ doctorId, name, color }) {
  return request("/api/manage/labels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, name, color }),
  });
}

export async function deleteLabelById({ doctorId, labelId }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/labels/${labelId}?${qs.toString()}`, {
    method: "DELETE",
  });
}

export async function assignLabelToPatient({ doctorId, patientId, labelId }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients/${patientId}/labels/${labelId}?${qs.toString()}`, {
    method: "POST",
  });
}

export async function removeLabelFromPatient({ doctorId, patientId, labelId }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients/${patientId}/labels/${labelId}?${qs.toString()}`, {
    method: "DELETE",
  });
}

export async function getAdminDbView({ doctorId, patientName, dateFrom, dateTo, limit = 100 }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  qs.set("limit", String(limit));
  return request(`/api/admin/db-view?${qs.toString()}`);
}

export async function getAdminTables({ doctorId, patientName, dateFrom, dateTo }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  return request(`/api/admin/tables?${qs.toString()}`);
}

export async function getAdminTableRows({ tableKey, doctorId, patientName, dateFrom, dateTo, limit = 200 }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  qs.set("limit", String(limit));
  return request(`/api/admin/tables/${encodeURIComponent(tableKey)}?${qs.toString()}`);
}
