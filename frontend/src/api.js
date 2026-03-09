async function readError(response) {
  const text = await response.text();
  return text || `HTTP ${response.status}`;
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
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const headers = { ...(options.headers || {}) };
    const token = _getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(url, { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      const err = new Error(await readError(response));
      err.status = response.status;
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

export async function webLogin(doctorId, name) {
  return request("/api/auth/web/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, name: name || undefined }),
  });
}

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

export async function createAdminInviteCode(doctorId, doctorName, customCode) {
  return adminRequest("/api/admin/invite-codes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doctor_id: doctorId,
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
  });
}

export async function transcribeAudio(audioBlob, filename = "audio.webm") {
  const form = new FormData();
  form.append("audio", audioBlob, filename);
  return request("/api/records/transcribe", { method: "POST", body: form });
}

export async function ocrImage(imageFile) {
  const form = new FormData();
  form.append("image", imageFile, imageFile.name);
  return request("/api/records/ocr", { method: "POST", body: form });
}

export async function getPatients(doctorId, filters = {}, limit = 50, offset = 0) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit), offset: String(offset) });
  if (filters.category) qs.set("category", filters.category);
  return request(`/api/manage/patients?${qs.toString()}`);
}

export async function exportPatientPdf(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  const headers = {};
  if (_webToken) headers["Authorization"] = `Bearer ${_webToken}`;
  const response = await fetch(`/api/export/patient/${patientId}/pdf?${qs.toString()}`, { headers });
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
  const response = await fetch(`/api/export/patient/${patientId}/outpatient-report?${qs.toString()}`, { headers });
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
  const response = await fetch("/api/export/template/upload", { method: "POST", headers, body: form });
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
  const response = await fetch(`/api/export/template?${qs.toString()}`, { method: "DELETE", headers });
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

export async function getCvdContext(patientId, doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/patients/${patientId}/cvd-context?${qs.toString()}`);
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
    "X-Patient-Token": patientToken || "",
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { ...options, headers, signal: controller.signal });
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
  return fetch("/api/patient/session", {
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
