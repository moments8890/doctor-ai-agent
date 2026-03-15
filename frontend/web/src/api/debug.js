import { debugRequest } from "./base";

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
