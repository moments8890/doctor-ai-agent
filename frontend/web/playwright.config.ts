import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for doctor-ai-agent e2e workflow tests.
 *
 * These tests run against a *manually started* backend + frontend — NOT
 * Playwright's webServer — because the backend needs `NO_PROXY=*` and a
 * specific startup order that's documented in docs/qa/workflows/README.md.
 *
 * Default base URL is the frontend dev server on :5173. The backend lives
 * at :8000; specs talk to it via `API_BASE_URL`.
 *
 * Spec files live in tests/e2e/ and match docs/qa/workflows/*.md 1:1.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",

  // Parallel within a file is fine, but workflows share DB state — run files serially.
  fullyParallel: false,
  workers: 1,

  // Fail the build on .only() left in CI.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,

  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Mobile-first layout — the doctor app is a mobile PWA. Matches the hero path.
    viewport: { width: 390, height: 844 },
    ignoreHTTPSErrors: true,
  },

  projects: [
    {
      name: "chromium-mobile",
      use: { ...devices["iPhone 13"] },
    },
  ],

  // No webServer — see README. User starts backend + frontend manually.
});
