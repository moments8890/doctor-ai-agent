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
    return json.detail || json.message || text;
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

let _debugToken = "";
let _debugAuthErrorHandler = null;

export function setDebugToken(token) { _debugToken = token || ""; }
export function onDebugAuthError(handler) { _debugAuthErrorHandler = handler; }

async function debugRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_debugToken) headers["X-Debug-Token"] = _debugToken;
  try {
    return await request(url, { ...options, headers });
  } catch (err) {
    if (err.status === 403 || err.status === 503) {
      _debugAuthErrorHandler?.();
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

export async function unifiedMe(token) {
  const res = await fetch(apiUrl("/api/auth/unified/me"), {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Token invalid");
  return res.json();
}

export async function unifiedListDoctors() {
  const res = await fetch(apiUrl("/api/auth/unified/doctors"));
  return res.json();
}

// ---------------------------------------------------------------------------
// Legacy invite login (kept for backward compat)
// ---------------------------------------------------------------------------

export async function inviteLogin(code, specialty) {
  return request("/api/auth/invite/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, specialty: specialty || undefined }),
  });
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


export async function sendChat(payload) {
  return request("/api/records/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    _timeout: 120000,
  });
}

// ---------------------------------------------------------------------------
// Doctor-side interview API (ADR 0016 — doctor mode)
// ---------------------------------------------------------------------------

export async function doctorInterviewTurn(formData) {
  return request("/api/records/interview/turn", {
    method: "POST",
    body: formData,
    _timeout: 120000,
  });
}

export async function doctorInterviewConfirm(sessionId, doctorId) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (doctorId) formData.append("doctor_id", doctorId);
  return request("/api/records/interview/confirm", {
    method: "POST",
    body: formData,
    _timeout: 120000,
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

export async function exportPatientPdf(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
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

export async function getAdminDbView({ doctorId, patientName, dateFrom, dateTo, limit = 100 }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  qs.set("limit", String(limit));
  return adminRequest(`/api/admin/db-view?${qs.toString()}`);
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

export async function getAdminObservability({
  traceLimit = 80,
  summaryLimit = 500,
  spanLimit = 200,
  slowSpanLimit = 30,
  scope = "public",
  traceId = "",
} = {}) {
  const qs = new URLSearchParams({
    trace_limit: String(traceLimit),
    summary_limit: String(summaryLimit),
    span_limit: String(spanLimit),
    slow_span_limit: String(slowSpanLimit),
    scope,
  });
  if (traceId) qs.set("trace_id", traceId);
  return adminRequest(`/api/admin/observability?${qs.toString()}`);
}

export async function clearAdminObservabilityTraces() {
  return adminRequest("/api/admin/observability/traces", { method: "DELETE" });
}

export async function seedAdminObservabilitySamples(count = 3) {
  const qs = new URLSearchParams({ count: String(count) });
  return adminRequest(`/api/admin/observability/sample?${qs.toString()}`, { method: "POST" });
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

export async function resetAdminRoutingMetrics() {
  return adminRequest("/api/admin/routing-metrics/reset", { method: "POST" });
}

export async function getDebugLogs({ level = "WARNING", limit = 200, source = "app" } = {}) {
  const qs = new URLSearchParams({ level, limit: String(limit), source });
  return debugRequest(`/api/debug/logs?${qs.toString()}`);
}

export async function getDebugObservability({
  traceLimit = 80,
  summaryLimit = 500,
  spanLimit = 300,
  slowSpanLimit = 30,
  scope = "public",
  traceId = "",
} = {}) {
  const qs = new URLSearchParams({
    trace_limit: String(traceLimit),
    summary_limit: String(summaryLimit),
    span_limit: String(spanLimit),
    slow_span_limit: String(slowSpanLimit),
    scope,
  });
  if (traceId) qs.set("trace_id", traceId);
  return debugRequest(`/api/debug/observability?${qs.toString()}`);
}

export async function clearDebugObservabilityTraces() {
  return debugRequest("/api/debug/observability/traces", { method: "DELETE" });
}

export async function seedDebugObservabilitySamples(count = 3) {
  const qs = new URLSearchParams({ count: String(count) });
  return debugRequest(`/api/debug/observability/sample?${qs.toString()}`, { method: "POST" });
}

export async function getDebugRoutingMetrics() {
  return debugRequest("/api/debug/routing-metrics");
}

export async function resetDebugRoutingMetrics() {
  return debugRequest("/api/debug/routing-metrics/reset", { method: "POST" });
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

export async function getTaskRecord(recordId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/tasks/record/${recordId}?${qs.toString()}`);
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

export async function patientSession(doctorId, patientName) {
  return fetch(apiUrl("/api/patient/session"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, patient_name: patientName }),
  }).then(async (res) => {
    if (!res.ok) {
      const err = new Error(await readError(res));
      err.status = res.status;
      throw err;
    }
    return res.json();
  });
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

export async function listDoctors() {
  const res = await fetch(apiUrl("/api/patient/doctors"));
  return res.json();
}

export async function patientRegister(doctorId, name, gender, yearOfBirth, phone) {
  const res = await fetch(apiUrl("/api/patient/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, name, gender, year_of_birth: yearOfBirth, phone }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function patientLogin(phone, yearOfBirth, doctorId) {
  const res = await fetch(apiUrl("/api/patient/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, year_of_birth: yearOfBirth, doctor_id: doctorId || undefined }),
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

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

export async function interviewCurrent(token) {
  return patientRequest("/api/patient/interview/current", token);
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

export async function patientUpload(token, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(apiUrl("/api/patient/upload"), {
    method: "POST",
    headers: { "X-Patient-Token": token },
    body: form,
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function getKnowledgeItems(doctorId) {
  return request(`/api/manage/knowledge?doctor_id=${doctorId}`);
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

export async function getCaseLibrary(doctorId) {
  return request(`/api/manage/case-history?doctor_id=${doctorId}&status=confirmed`);
}

export async function getCaseDetail(caseId, doctorId) {
  return request(`/api/manage/case-history/${caseId}?doctor_id=${doctorId}`);
}

// ── Review Queue ──────────────────────────────────────────────────────────────

export async function getReviewQueue(doctorId, status = "pending_review", limit = 50) {
  return request(`/api/manage/review-queue?doctor_id=${doctorId}&status=${status}&limit=${limit}`);
}

export async function getReviewDetail(queueId, doctorId) {
  return request(`/api/manage/review-queue/${queueId}?doctor_id=${doctorId}`);
}

export async function confirmReview(queueId, doctorId) {
  return request(`/api/manage/review-queue/${queueId}/confirm?doctor_id=${doctorId}`, {
    method: "POST",
  });
}

export async function updateReviewField(queueId, doctorId, field, value) {
  return request(`/api/manage/review-queue/${queueId}/record?doctor_id=${doctorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
}

// ── Briefing ──────────────────────────────────────────────────────────────────

export async function getBriefing(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/doctor/briefing?${qs.toString()}`);
}

// ── Diagnosis ─────────────────────────────────────────────────────────────────

export async function getDiagnosis(recordId, doctorId) {
  return request(`/api/manage/diagnosis/${recordId}?doctor_id=${doctorId}`);
}

export async function decideDiagnosisItem(diagnosisId, doctorId, type, index, decision) {
  return request(`/api/manage/diagnosis/${diagnosisId}/decide?doctor_id=${doctorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, index, decision }),
  });
}

export async function confirmDiagnosis(diagnosisId, doctorId) {
  return request(`/api/manage/diagnosis/${diagnosisId}/confirm?doctor_id=${doctorId}`, {
    method: "POST",
  });
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
export async function getPatientChat(patientId) {
  return request(`/api/manage/patients/${patientId}/chat`);
}

export async function replyToPatient(patientId, text) {
  return request(`/api/manage/patients/${patientId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}
