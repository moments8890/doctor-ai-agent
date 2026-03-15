import { request, apiUrl, getWebToken } from "./base";

export async function inviteLogin(code, specialty) {
  return request("/api/auth/invite/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, specialty: specialty || undefined }),
  });
}

export async function sendChat(payload) {
  return request("/api/records/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    _timeout: 35000,
  });
}

export async function ocrImage(imageFile) {
  const form = new FormData();
  form.append("image", imageFile, imageFile.name);
  return request("/api/records/ocr", { method: "POST", body: form });
}

export async function extractFileForChat(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/api/records/extract-file", { method: "POST", body: form, _timeout: 120000 });
}

export async function getPatients(doctorId, filters = {}, limit = 50, offset = 0) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit), offset: String(offset) });
  if (filters.risk) qs.set("risk", filters.risk);
  if (filters.category) qs.set("category", filters.category);
  return request(`/api/manage/patients?${qs.toString()}`);
}

export async function searchPatients(doctorId, q) {
  const qs = new URLSearchParams({ doctor_id: doctorId, q });
  return request(`/api/manage/patients/search?${qs.toString()}`);
}

export async function exportPatientPdf(patientId, doctorId, sections) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (sections) {
    const { visitRange, ...flags } = sections;
    Object.entries(flags).forEach(([k, v]) => { qs.set(k, v ? "1" : "0"); });
    if (visitRange) qs.set("visitRange", visitRange);
  }
  const headers = {};
  const token = getWebToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(apiUrl(`/api/export/patient/${patientId}/pdf?${qs.toString()}`), { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `病历_patient_${patientId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportOutpatientReport(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  const headers = {};
  const token = getWebToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(apiUrl(`/api/export/patient/${patientId}/outpatient-report?${qs.toString()}`), { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `门诊病历_patient_${patientId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function getTemplateStatus(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/export/template/status?${qs.toString()}`);
}

export async function uploadTemplate(doctorId, file) {
  const headers = {};
  const token = getWebToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const form = new FormData();
  form.append("file", file);
  form.append("doctor_id", doctorId);
  const response = await fetch(apiUrl("/api/export/template/upload"), { method: "POST", headers, body: form });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function deleteTemplate(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  const headers = {};
  const token = getWebToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(apiUrl(`/api/export/template?${qs.toString()}`), { method: "DELETE", headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function getRecords({ doctorId, patientId, patientName, dateFrom, dateTo, limit = 50, offset = 0 }) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit), offset: String(offset) });
  if (patientId) qs.set("patient_id", patientId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  return request(`/api/manage/records?${qs.toString()}`);
}

export async function updateRecord(doctorId, recordId, fields) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/records/${recordId}?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function deleteRecord(doctorId, recordId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/records/${recordId}?${qs.toString()}`, { method: "DELETE" });
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

export async function deletePatient(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients/${patientId}?${qs.toString()}`, { method: "DELETE" });
}

export async function getTasks(doctorId, status = null) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (status) qs.set("status", status);
  return request(`/api/tasks?${qs.toString()}`);
}

export async function patchTask(taskId, doctorId, status) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/${taskId}?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export async function postponeTask(taskId, doctorId, dueAt) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/${taskId}/due?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ due_at: dueAt }),
  });
}

export async function createTask(doctorId, { taskType, title, dueAt, patientId, content }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task_type: taskType,
      title,
      due_at: dueAt || undefined,
      patient_id: patientId || undefined,
      content: content || undefined,
    }),
  });
}

export async function getPendingRecord(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/pending-record?${qs.toString()}`);
}

export async function confirmPendingRecord(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/pending-record/confirm?${qs.toString()}`, { method: "POST" });
}

export async function abandonPendingRecord(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/pending-record/abandon?${qs.toString()}`, { method: "POST" });
}

export async function confirmPendingRecordById(pendingId) {
  return request(`/api/records/pending/${encodeURIComponent(pendingId)}/confirm`, { method: "POST" });
}

export async function abandonPendingRecordById(pendingId) {
  return request(`/api/records/pending/${encodeURIComponent(pendingId)}/abandon`, { method: "POST" });
}

export async function getWorkingContext(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/working-context?${qs.toString()}`);
}

export async function getDoctorProfile(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/profile?${qs.toString()}`);
}

export async function updateDoctorProfile(doctorId, { name, specialty, visit_scenario, note_style }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  const payload = {};
  if (name !== undefined) payload.name = name;
  if (specialty !== undefined) payload.specialty = specialty || null;
  if (visit_scenario !== undefined) payload.visit_scenario = visit_scenario || null;
  if (note_style !== undefined) payload.note_style = note_style || null;
  return request(`/api/manage/profile?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getKnowledgeItems(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge?${qs.toString()}`);
}

export async function deleteKnowledgeItem(doctorId, itemId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge/${itemId}?${qs.toString()}`, {
    method: "DELETE",
  });
}

export async function addKnowledgeItem(doctorId, content) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}
