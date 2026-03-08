async function readError(response) {
  const text = await response.text();
  return text || `HTTP ${response.status}`;
}

async function request(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    if (!response.ok) {
      throw new Error(await readError(response));
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

export function setAdminToken(token) {
  _adminToken = token || "";
}

async function adminRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_adminToken) headers["X-Admin-Token"] = _adminToken;
  return request(url, { ...options, headers });
}

let _debugToken = "";

export function setDebugToken(token) {
  _debugToken = token || "";
}

async function debugRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_debugToken) headers["X-Debug-Token"] = _debugToken;
  return request(url, { ...options, headers });
}

export async function sendChat(payload) {
  return request("/api/records/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getPatients(doctorId, filters = {}, limit = 50, offset = 0) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit), offset: String(offset) });
  if (filters.category) qs.set("category", filters.category);
  if (filters.risk) qs.set("risk", filters.risk);
  if (filters.followUpState) qs.set("follow_up_state", filters.followUpState);
  if (filters.staleRisk !== undefined && filters.staleRisk !== null && filters.staleRisk !== "") {
    qs.set("stale_risk", String(filters.staleRisk));
  }
  return request(`/api/manage/patients?${qs.toString()}`);
}

export async function getRecords({ doctorId, patientId, patientName, dateFrom, dateTo, limit = 50, offset = 0 }) {
  const qs = new URLSearchParams({ doctor_id: doctorId, limit: String(limit), offset: String(offset) });
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

export async function getAdminTableRows({ tableKey, doctorId, patientName, dateFrom, dateTo, limit = 200 }) {
  const qs = new URLSearchParams();
  if (doctorId) qs.set("doctor_id", doctorId);
  if (patientName) qs.set("patient_name", patientName);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  qs.set("limit", String(limit));
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
