// Frontend Sentry/GlitchTip wiring.
//
// Tags every browser-emitted log envelope with `service.name = frontend`
// so GlitchTip's Logs Service dropdown can filter to React-only events,
// in parallel with the 5 backend categories (backend / llm / vision /
// scheduler / db) tagged server-side via _before_send_log in src/main.py.
//
// No-op when VITE_SENTRY_DSN is unset, so dev builds don't ship to
// GlitchTip and offline/CI doesn't fail.
import * as Sentry from "@sentry/browser";

export function initSentry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) {
    return;
  }
  try {
    Sentry.init({
      dsn,
      environment: import.meta.env.MODE,
      release: import.meta.env.VITE_GIT_COMMIT || "dev",
      sampleRate: 1.0,
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
      _experiments: {
        enableLogs: true,
        beforeSendLog: (log) => {
          log.attributes = log.attributes || {};
          log.attributes["service.name"] = "frontend";
          return log;
        },
      },
    });
  } catch (_err) {
    // Sentry init must never break the React boot path.
  }
}
