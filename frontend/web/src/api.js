// In mobile builds (Capacitor), set VITE_API_BASE_URL to the backend origin,
// e.g. https://your-server.com — relative /api/... paths don't resolve in WebView.
const _API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function apiUrl(path) {
  return `${_API_BASE}${path}`;
}

async function readError(response) {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;
  try {
    const json = JSON.parse(text);
    const detail = typeof json.detail === "string" ? json.detail
      : Array.isArray(json.detail) ? json.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
      : json.detail ? JSON.stringify(json.detail) : null;
    const msg = detail || (typeof json.message === "string" ? json.message : null) || text;
    // Replace raw Pydantic English validation errors with friendly Chinese messages
    if (/valid integer/i.test(msg)) return "口令必须为纯数字";
    if (/field required/i.test(msg)) return "请填写完整信息";
    return msg;
  } catch {
    return text;
  }
}

let _webToken = "";

export function setWebToken(token) {
  _webToken = token || "";
}

/** Read token from module cache, falling back to Zustand's persisted localStorage entry.
 *  This handles the window between page load (store re-hydrated) and the App.jsx
 *  useEffect that calls setWebToken — during that gap _webToken is empty but the
 *  token already exists in localStorage. */
function _getToken() {
  if (_webToken) return _webToken;
  try {
    const raw = localStorage.getItem("doctor-session");
    if (raw) {
      const token = JSON.parse(raw)?.state?.accessToken;
      if (token) {
        _webToken = token; // warm the cache for subsequent calls
        return token;
      }
    }
  } catch {
    // ignore parse errors
  }
  return "";
}

async function request(url, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options._timeout ?? 15000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { ...(options.headers || {}) };
    const token = _getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (typeof window !== "undefined" && window.__wxjs_environment === "miniprogram") {
      headers["X-Client-Channel"] = "miniapp";
    }
    const response = await fetch(apiUrl(url), { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      const err = new Error(await readError(response));
      err.status = response.status;
      if (response.status === 401) { _authExpiredHandler?.(); }
      throw err;
    }
    return response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

let _authExpiredHandler = null;
export function onAuthExpired(handler) { _authExpiredHandler = handler; }

let _adminToken = "";
let _adminAuthErrorHandler = null;

export function setAdminToken(token) { _adminToken = token || ""; }
export function onAdminAuthError(handler) { _adminAuthErrorHandler = handler; }

async function adminRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_adminToken) headers["X-Admin-Token"] = _adminToken;
  try {
    return await request(url, { ...options, headers });
  } catch (err) {
    if (err.status === 403 || err.status === 503) {
      _adminAuthErrorHandler?.();
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Unified auth API
// ---------------------------------------------------------------------------

export async function unifiedLogin(phone, yearOfBirth) {
  const res = await fetch(apiUrl("/api/auth/unified/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, year_of_birth: yearOfBirth }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function unifiedLoginWithRole(phone, yearOfBirth, role, doctorId, patientId) {
  const res = await fetch(apiUrl("/api/auth/unified/login-role"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, year_of_birth: yearOfBirth, role, doctor_id: doctorId, patient_id: patientId }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function unifiedRegisterDoctor(phone, name, yearOfBirth, inviteCode, specialty) {
  const res = await fetch(apiUrl("/api/auth/unified/register/doctor"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, name, year_of_birth: yearOfBirth, invite_code: inviteCode, specialty }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function unifiedRegisterPatient(phone, name, yearOfBirth, doctorId, gender) {
  const res = await fetch(apiUrl("/api/auth/unified/register/patient"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, name, year_of_birth: yearOfBirth, doctor_id: doctorId, gender }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function unifiedListDoctors() {
  const res = await fetch(apiUrl("/api/auth/unified/doctors"));
  return res.json();
}

export async function getAdminInviteCodes() {
  return adminRequest("/api/admin/invite-codes");
}

export async function createAdminInviteCode(doctorName, customCode) {
  return adminRequest("/api/admin/invite-codes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doctor_name: doctorName || undefined,
      code: customCode || undefined,
    }),
  });
}

export async function revokeAdminInviteCode(code) {
  return adminRequest(`/api/admin/invite-codes/${encodeURIComponent(code)}`, { method: "DELETE" });
}


// sendChat removed — routing layer deleted, use interview/diagnosis APIs directly

// ---------------------------------------------------------------------------
// Doctor-side interview API (ADR 0016 — doctor mode)
// ---------------------------------------------------------------------------

export async function doctorInterviewGetSession(sessionId, doctorId) {
  const params = new URLSearchParams({ doctor_id: doctorId || "" });
  return request(`/api/records/interview/session/${sessionId}?${params}`);
}

export async function doctorInterviewTurn(formData) {
  return request("/api/records/interview/turn", {
    method: "POST",
    body: formData,
    _timeout: 120000,
  });
}

export async function doctorInterviewConfirm(sessionId, doctorId, patientName) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (doctorId) formData.append("doctor_id", doctorId);
  if (patientName) formData.append("patient_name", patientName);
  return request("/api/records/interview/confirm", {
    method: "POST",
    body: formData,
    _timeout: 120000,
  });
}

export async function confirmCarryForward(sessionId, doctorId, field, action = "confirm") {
  return request("/api/records/interview/carry-forward-confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, doctor_id: doctorId, field, action }),
  });
}

export async function doctorInterviewCancel(sessionId, doctorId) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (doctorId) formData.append("doctor_id", doctorId);
  return request("/api/records/interview/cancel", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload image/PDF → OCR + LLM extract → create interview session with pre-populated fields.
 * Returns: { session_id, mode, source, pre_populated: { field: value, ... } }
 */
export async function importToInterview(file, doctorId, patientId) {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("doctor_id", doctorId || "");
  if (patientId) form.append("patient_id", String(patientId));
  return request("/api/import/medical-record", { method: "POST", body: form, _timeout: 120000 });
}

/**
 * Send text (paste/voice) → LLM extract → create interview session with pre-populated fields.
 * Returns: { session_id, mode, source, pre_populated: { field: value, ... } }
 */
export async function textToInterview(text, doctorId, patientId) {
  return request("/api/records/from-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, doctor_id: doctorId || "", patient_id: patientId || null }),
    _timeout: 120000,
  });
}

/**
 * Update a single field value in an interview session (for inline-edit in import review).
 */
export async function updateInterviewField(sessionId, doctorId, field, value) {
  return request("/api/records/interview/field", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, doctor_id: doctorId, field, value }),
  });
}

export async function transcribeAudio(blob, filename) {
  const form = new FormData();
  form.append("audio", blob, filename || "recording.webm");
  return request("/api/records/transcribe", { method: "POST", body: form, _timeout: 30000 });
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

export async function exportPatientPdf(patientId, doctorId, { sections, visitRange } = {}) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (sections && sections.length > 0) qs.set("sections", sections.join(","));
  if (visitRange) qs.set("visit_range", visitRange);
  const headers = {};
  if (_webToken) headers["Authorization"] = `Bearer ${_webToken}`;
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
  if (_webToken) headers["Authorization"] = `Bearer ${_webToken}`;
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
  if (_webToken) headers["Authorization"] = `Bearer ${_webToken}`;
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
  if (_webToken) headers["Authorization"] = `Bearer ${_webToken}`;
  const response = await fetch(apiUrl(`/api/export/template?${qs.toString()}`), { method: "DELETE", headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Bulk export API
// ---------------------------------------------------------------------------

export async function startBulkExport(doctorId) {
  return request(`/api/export/bulk?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
  });
}

export async function getBulkExportStatus(taskId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/export/bulk/${taskId}?${qs.toString()}`);
}

export async function downloadBulkExport(taskId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  const headers = {};
  const token = _getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(apiUrl(`/api/export/bulk/${taskId}/download?${qs.toString()}`), { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `导出_${new Date().toISOString().slice(0, 10)}.zip`;
  a.click();
  URL.revokeObjectURL(url);
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

export async function getPatientTimeline({ doctorId, patientId, limit = 100 }) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit) });
  return request(`/api/manage/patients/${patientId}/timeline?${qs.toString()}`);
}


export async function deletePatient(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients/${patientId}?${qs.toString()}`, { method: "DELETE" });
}

export async function getAdminTables({ doctorId, patientName, dateFrom, dateTo }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  return adminRequest(`/api/admin/tables?${qs.toString()}`);
}

export async function getAdminTableRows({ tableKey, doctorId, patientName, dateFrom, dateTo, limit = 200, offset = 0 }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  qs.set("limit", String(limit));
  if (offset > 0) qs.set("offset", String(offset));
  return adminRequest(`/api/admin/tables/${encodeURIComponent(tableKey)}?${qs.toString()}`);
}

export async function getAdminFilterOptions({ doctorId } = {}) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  return adminRequest(`/api/admin/filter-options?${qs.toString()}`);
}

export async function getAdminRuntimeConfig() {
  return adminRequest("/api/admin/config");
}

export async function updateAdminRuntimeConfig(config) {
  return adminRequest("/api/admin/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
}

export async function verifyAdminRuntimeConfig(config) {
  return adminRequest("/api/admin/config/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
}

export async function applyAdminRuntimeConfig() {
  return adminRequest("/api/admin/config/apply", { method: "POST" });
}

export async function getAdminTunnelUrl() {
  return adminRequest("/api/admin/dev/tunnel-url");
}

export async function getAdminRoutingKeywords(token) {
  return adminRequest("/api/admin/fast-router/keywords");
}
export async function putAdminRoutingKeywords(token, body) {
  return adminRequest("/api/admin/fast-router/keywords", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
export async function reloadAdminRoutingKeywords(token) {
  return adminRequest("/api/admin/fast-router/keywords/reload", { method: "POST" });
}

export async function getAdminRoutingMetrics() {
  return adminRequest("/api/admin/routing-metrics");
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

export async function getTaskById(taskId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/${taskId}?${qs.toString()}`);
}

export async function patchTaskNotes(taskId, doctorId, notes) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/${taskId}/notes?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}

export async function getTaskRecord(recordId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/record/${recordId}?${qs.toString()}`);
}


export async function clearContext(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/clear-context?${qs.toString()}`, { method: "POST" });
}

export async function updateAdminRecord(recordId, fields) {
  return adminRequest(`/api/admin/records/${recordId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function getAdminPrompts() {
  return adminRequest("/api/admin/prompts");
}

export async function updateAdminPrompt(key, content) {
  return adminRequest(`/api/admin/prompts/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function getDoctorProfile(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/profile?${qs.toString()}`);
}

export async function updateDoctorProfile(doctorId, { name, specialty }) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/profile?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, specialty: specialty || null }),
  });
}

export async function getPreferences(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/preferences?${qs.toString()}`);
}

export async function updatePreferences(doctorId, prefs) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/preferences?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs),
  });
}

export async function getPersona(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona?${qs.toString()}`);
}

export async function addPersonaRule(doctorId, field, text) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, text }),
  });
}

export async function updatePersonaRule(doctorId, field, ruleId, text) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, rule_id: ruleId, text }),
  });
}

export async function deletePersonaRule(doctorId, field, ruleId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, rule_id: ruleId }),
  });
}

export async function activatePersona(doctorId, action) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/activate?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active: Boolean(action) }),
  });
}

export async function getPersonaPending(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/pending?${qs.toString()}`);
}

export async function acceptPendingItem(doctorId, itemId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/pending/${itemId}/accept?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

export async function rejectPendingItem(doctorId, itemId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/pending/${itemId}/reject?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

export async function getOnboardingScenarios(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/onboarding/scenarios?${qs.toString()}`);
}

export async function completeOnboarding(doctorId, picks) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/onboarding/complete?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ picks }),
  });
}

export async function teachByExample(doctorId, exampleText) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/teach?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ example_text: exampleText }),
  });
}

export async function generateQRToken(role, doctorId, patientId) {
  return request("/api/auth/qr-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role,
      doctor_id: doctorId,
      ...(patientId != null && { patient_id: patientId }),
    }),
  });
}

export async function createOnboardingPatientEntry(doctorId, { patientName, gender, age } = {}) {
  return request("/api/manage/onboarding/patient-entry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doctor_id: doctorId,
      patient_name: patientName,
      gender: gender || null,
      age: age ?? null,
    }),
  });
}

export async function ensureOnboardingExamples(doctorId, { knowledgeItemId } = {}) {
  const payload = { doctor_id: doctorId };
  if (knowledgeItemId != null) payload.knowledge_item_id = knowledgeItemId;
  return request("/api/manage/onboarding/examples", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Patient portal API (uses X-Patient-Token header, not doctor Bearer token)
// ---------------------------------------------------------------------------

async function patientRequest(url, patientToken, options = {}) {
  const headers = {
    ...(options.headers || {}),
    "Authorization": `Bearer ${patientToken || ""}`,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(apiUrl(url), { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      const err = new Error(await readError(response));
      err.status = response.status;
      throw err;
    }
    return response.json();
  } catch (err) {
    if (err.name === "AbortError") throw new Error("Request timed out");
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function getPatientMe(patientToken) {
  return patientRequest("/api/patient/me", patientToken);
}

export async function getPatientRecords(patientToken) {
  return patientRequest("/api/patient/records", patientToken);
}

export async function sendPatientMessage(patientToken, text) {
  return patientRequest("/api/patient/message", patientToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// ---------------------------------------------------------------------------
// Patient interview API (ADR 0016)
// ---------------------------------------------------------------------------

export async function interviewStart(token) {
  return patientRequest("/api/patient/interview/start", token, { method: "POST" });
}

export async function interviewTurn(token, sessionId, text) {
  return patientRequest("/api/patient/interview/turn", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text }),
  });
}

export async function interviewConfirm(token, sessionId) {
  return patientRequest("/api/patient/interview/confirm", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function interviewCancel(token, sessionId) {
  return patientRequest("/api/patient/interview/cancel", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function getKnowledgeItems(doctorId) {
  return request(`/api/manage/knowledge?doctor_id=${doctorId}`);
}

export async function updateKnowledgeItem(doctorId, itemId, text, title) {
  const payload = { text };
  if (title !== undefined) payload.title = title;
  return request(`/api/manage/knowledge/${itemId}?doctor_id=${doctorId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteKnowledgeItem(doctorId, itemId) {
  return request(`/api/manage/knowledge/${itemId}?doctor_id=${doctorId}`, { method: "DELETE" });
}

export async function addKnowledgeItem(doctorId, content, category = "custom") {
  return request(`/api/manage/knowledge?doctor_id=${doctorId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, category }),
  });
}

export async function uploadKnowledgeExtract(doctorId, file) {
  const form = new FormData();
  form.append("file", file);
  const token = _getToken();
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(apiUrl(`/api/manage/knowledge/upload/extract?doctor_id=${encodeURIComponent(doctorId)}`), {
    method: "POST",
    headers,
    body: form,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function uploadKnowledgeSave(doctorId, text, sourceFilename, { sourceUrl } = {}) {
  const payload = { text, source_filename: sourceFilename };
  if (sourceUrl) payload.source_url = sourceUrl;
  return request(`/api/manage/knowledge/upload/save?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function processKnowledgeText(doctorId, text) {
  return request(`/api/manage/knowledge/process-text?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function fetchKnowledgeUrl(doctorId, url) {
  return request(`/api/manage/knowledge/fetch-url?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function getKnowledgeBatch(doctorId, ids) {
  const idsStr = ids.join(",");
  return request(`/api/manage/knowledge/batch?doctor_id=${encodeURIComponent(doctorId)}&ids=${idsStr}`);
}

// ── Briefing ──────────────────────────────────────────────────────────────────

export async function getBriefing(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/doctor/briefing?${qs.toString()}`);
}

// ---------------------------------------------------------------------------
// Patient portal — post-visit (ADR 0020)
// ---------------------------------------------------------------------------

export async function getPatientRecordDetail(token, recordId) {
  return patientRequest(`/api/patient/records/${recordId}`, token);
}

export async function getPatientTasks(token) {
  return patientRequest("/api/patient/tasks", token);
}

export async function completePatientTask(token, taskId) {
  return patientRequest(`/api/patient/tasks/${taskId}/complete`, token, { method: "POST" });
}

export async function uncompletePatientTask(token, taskId) {
  return patientRequest(`/api/patient/tasks/${taskId}/uncomplete`, token, { method: "POST" });
}

export async function getPatientChatMessages(token, sinceId) {
  const qs = sinceId != null ? `?since=${sinceId}` : "";
  return patientRequest(`/api/patient/chat/messages${qs}`, token);
}

export async function sendPatientChat(token, text) {
  return patientRequest("/api/patient/chat", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// Doctor-side patient chat/reply
export async function getPatientChat(patientId, doctorId) {
  const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
  return request(`/api/manage/patients/${patientId}/chat${qs}`);
}

export async function replyToPatient(patientId, text) {
  return request(`/api/manage/patients/${patientId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// ── Diagnosis / Review ────────────────────────────────────────────────────────

export async function triggerDiagnosis(recordId, doctorId) {
  return request(`/api/doctor/records/${recordId}/diagnose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}

export async function getSuggestions(recordId, doctorId) {
  return request(`/api/doctor/records/${recordId}/suggestions?doctor_id=${doctorId}`);
}

export async function decideSuggestion(suggestionId, decision, opts = {}) {
  return request(`/api/doctor/suggestions/${suggestionId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, ...opts }),
  });
}

export async function addSuggestion(recordId, doctorId, section, content, detail) {
  return request(`/api/doctor/records/${recordId}/suggestions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, section, content, detail }),
  });
}

// ---------------------------------------------------------------------------
// Knowledge stats, AI activity, drafts
// ---------------------------------------------------------------------------

export async function fetchKnowledgeUsageHistory(doctorId, itemId) {
  return request(`/api/manage/knowledge/${itemId}/usage?doctor_id=${encodeURIComponent(doctorId)}`);
}

export async function fetchKnowledgeStats(doctorId, days = 7) {
  return request(`/api/manage/knowledge/stats?doctor_id=${encodeURIComponent(doctorId)}&days=${days}`);
}

export async function fetchAIActivity(doctorId, limit = 20) {
  return request(`/api/manage/ai/activity?doctor_id=${encodeURIComponent(doctorId)}&limit=${limit}`);
}

export async function fetchDraftSummary(doctorId) {
  return request(`/api/manage/drafts/summary?doctor_id=${encodeURIComponent(doctorId)}`);
}

export async function fetchAIAttention(doctorId) {
  return request(`/api/manage/patients/ai-attention?doctor_id=${encodeURIComponent(doctorId)}`);
}

export async function getReviewQueue(doctorId) {
  return request(`/api/manage/review/queue?doctor_id=${encodeURIComponent(doctorId)}`);
}

export async function fetchDrafts(doctorId, { includeSent = false, patientId = null } = {}) {
  let params = `doctor_id=${encodeURIComponent(doctorId)}${includeSent ? "&include_sent=true" : ""}`;
  if (patientId) params += `&patient_id=${patientId}`;
  return request(`/api/manage/drafts?${params}`);
}

export async function sendDraft(draftId, doctorId) {
  return request(`/api/manage/drafts/${draftId}/send?doctor_id=${encodeURIComponent(doctorId)}`, { method: "POST" });
}

export async function editDraft(draftId, doctorId, editedText) {
  return request(`/api/manage/drafts/${draftId}/edit?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edited_text: editedText }),
  });
}

export async function dismissDraft(draftId, doctorId) {
  return request(`/api/manage/drafts/${draftId}/dismiss?doctor_id=${encodeURIComponent(doctorId)}`, { method: "POST" });
}

export async function getDraftConfirmation(draftId, doctorId) {
  return request(`/api/manage/drafts/${draftId}/send-confirmation?doctor_id=${encodeURIComponent(doctorId)}`, { method: "POST" });
}

export async function createRuleFromEdit(editId, doctorId) {
  return request(`/api/manage/teaching/create-rule?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edit_id: editId }),
  });
}

export async function finalizeReview(recordId, doctorId) {
  return request(`/api/doctor/records/${recordId}/review/finalize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}

export async function seedDemo(doctorId) {
  return request("/api/manage/onboarding/seed-demo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}
