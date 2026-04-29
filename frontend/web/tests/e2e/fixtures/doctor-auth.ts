/**
 * doctorAuth fixture — registers a fresh test doctor and test patient,
 * then returns a `page` pre-authed into the doctor app.
 *
 * Usage:
 *
 *   import { test, expect } from "./fixtures/doctor-auth";
 *
 *   test("does the thing", async ({ doctorPage, doctor, patient }) => {
 *     await doctorPage.goto("/doctor");
 *     await expect(doctorPage.getByText(doctor.name)).toBeVisible();
 *   });
 *
 * The fixture registers one doctor per test (phone-unique) so re-runs on a
 * dirty DB do not collide. Downstream seed helpers live in `./seed.ts`.
 */
import { test as base, expect, type Page } from "@playwright/test";
import { StepRecorder } from "./step-recorder";

// E2E targets the isolated test backend on :8001 (per AGENTS.md and
// scripts/validate-v2-e2e.sh) — never the dev backend on :8000. Prior runs
// silently polluted the dev DB because the default pointed at :8000; pinning
// to :8001 here means an accidental run cannot register E2E test rows
// against real dev data. Override only with E2E_API_BASE_URL when the test
// backend is genuinely on a different port.
export const API_BASE_URL = process.env.E2E_API_BASE_URL || "http://127.0.0.1:8001";

export interface TestDoctor {
  doctorId: string;
  name: string;
  nickname: string;
  passcode: string;
  token: string;
}

/**
 * Fixed credentials for the shared test doctor + test patient. Seeded
 * via `scripts/ensure_test_doctor.py` and `scripts/ensure_test_patient.py`
 * before the suite runs (both wired into `scripts/validate-v2-e2e.sh`).
 *
 * Every spec that pulls the `doctor` / `doctorPage` / `patient` /
 * `patientPage` fixture logs in as this same pair — no per-test
 * registration, no random nicknames, no rate-limit thrash, no state
 * pollution from racing register-then-login flows.
 *
 * Patient nickname uniqueness is scoped per-doctor on the backend, so a
 * patient and a doctor sharing the nickname `test` is fine — the unified
 * login disambiguates by `role` (and `doctor_id` for patient).
 *
 * Specs that explicitly verify the register endpoints (seed-smoke) call
 * `registerDoctor` / `registerPatient` directly and continue to use random
 * per-call nicknames.
 */
export const TEST_DOCTOR_NICKNAME = "test";
export const TEST_DOCTOR_PASSCODE = "123456";
export const TEST_PATIENT_NICKNAME = "test";
export const TEST_PATIENT_PASSCODE = "123456";

export interface TestPatient {
  patientId: string;
  doctorId: string;
  name: string;
  nickname: string;
  passcode: string;
  gender: string;
  token: string;
}

/**
 * Generate a unique nickname so re-runs on a shared DB don't collide on the
 * backend's "nickname already registered" guard. The login UI requires
 * a numeric passcode, so we pair it with a random one per run.
 */
function uniqueNickname(prefix: "doctor" | "patient"): string {
  const lead = prefix === "doctor" ? "doc" : "pat";
  const rand = String(Math.floor(Math.random() * 1e9)).padStart(9, "0");
  return `${lead}_${rand}`;
}

function randomPasscode(): string {
  return String(Math.floor(100000 + Math.random() * 900000));
}

/**
 * Wipe the seeded test doctor's per-test state (KB items, persona, records,
 * messages, tasks, intake sessions, etc.) and any non-test patients under
 * that doctor. The test doctor row and the test patient row are preserved
 * so subsequent logins still work.
 *
 * Calls `/api/test/reset-test-doctor-data`, which is mounted only when the
 * backend runs with ENVIRONMENT=development AND PATIENTS_DB_PATH contains
 * "e2e" or "test" (triple-guarded against firing on a real DB).
 */
export async function resetTestDoctorData(
  request: import("@playwright/test").APIRequestContext,
): Promise<void> {
  const res = await request.post(`${API_BASE_URL}/api/test/reset-test-doctor-data`);
  expect(
    res.ok(),
    `reset-test-doctor-data failed: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
}

/**
 * Login as the shared seeded test doctor (nickname=test, passcode=123456).
 * This is the default path used by the `doctor` and `doctorPage` fixtures.
 *
 * Resets per-test state by default (`opts.reset = true`) so each test gets
 * a clean doctor row with no leftover KBs, persona, messages, etc. from
 * earlier tests in the run. Pass `{ reset: false }` for the rare case
 * where a test wants to observe accumulated state.
 *
 * Requires `scripts/ensure_test_doctor.py` to have run against the test DB
 * before the suite — `scripts/validate-v2-e2e.sh` does this in preflight.
 */
export async function loginAsTestDoctor(
  request: import("@playwright/test").APIRequestContext,
  opts: { reset?: boolean } = {},
): Promise<TestDoctor> {
  if (opts.reset !== false) {
    await resetTestDoctorData(request);
  }
  const res = await request.post(`${API_BASE_URL}/api/auth/unified/login`, {
    data: {
      nickname: TEST_DOCTOR_NICKNAME,
      passcode: TEST_DOCTOR_PASSCODE,
      role: "doctor",
    },
  });
  expect(
    res.ok(),
    `login as test doctor failed: ${res.status()} ${await res.text()}\n` +
      `Did you run scripts/ensure_test_doctor.py against the test DB?`,
  ).toBeTruthy();
  const body = await res.json();
  return {
    doctorId: body.doctor_id,
    name: body.name || TEST_DOCTOR_NICKNAME,
    nickname: TEST_DOCTOR_NICKNAME,
    passcode: TEST_DOCTOR_PASSCODE,
    token: body.token,
  };
}

export async function registerDoctor(
  request: import("@playwright/test").APIRequestContext,
  opts: { name?: string } = {},
): Promise<TestDoctor> {
  const suffix = String(Math.floor(Math.random() * 1e6)).padStart(6, "0");
  const name = (opts.name || "E2E测试医生") + suffix;
  const nickname = uniqueNickname("doctor");
  const passcode = randomPasscode();

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/doctor`, {
    data: { nickname, passcode, invite_code: "WELCOME" },
  });
  expect(
    res.ok(),
    `register doctor failed: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
  const body = await res.json();
  // Response shape:  { token, role: "doctor", doctor_id, name }
  return {
    doctorId: body.doctor_id,
    name: body.name || name,
    nickname,
    passcode,
    token: body.token,
  };
}

/**
 * Login as the shared seeded test patient (nickname=test, passcode=123456)
 * under the seeded test doctor. This is the default path used by the
 * `patient` and `patientPage` fixtures.
 *
 * Requires both `scripts/ensure_test_doctor.py` and
 * `scripts/ensure_test_patient.py` to have run against the test DB.
 *
 * Patient login uses `/unified/login-role` (not `/unified/login`) because
 * the backend requires `doctor_id` to disambiguate per-doctor patient
 * nicknames before mutating any failure counter (DOS guard).
 */
export async function loginAsTestPatient(
  request: import("@playwright/test").APIRequestContext,
  doctorId: string,
): Promise<TestPatient> {
  const res = await request.post(`${API_BASE_URL}/api/auth/unified/login-role`, {
    data: {
      nickname: TEST_PATIENT_NICKNAME,
      passcode: TEST_PATIENT_PASSCODE,
      role: "patient",
      doctor_id: doctorId,
    },
  });
  expect(
    res.ok(),
    `login as test patient failed: ${res.status()} ${await res.text()}\n` +
      `Did you run scripts/ensure_test_patient.py against the test DB?`,
  ).toBeTruthy();
  const body = await res.json();
  return {
    patientId: String(body.patient_id),
    doctorId: body.doctor_id,
    name: body.name || TEST_PATIENT_NICKNAME,
    nickname: TEST_PATIENT_NICKNAME,
    passcode: TEST_PATIENT_PASSCODE,
    gender: "男",
    token: body.token,
  };
}

export async function registerPatient(
  request: import("@playwright/test").APIRequestContext,
  doctorId: string,
  opts: { name?: string; gender?: string; yearOfBirth?: number } = {},
): Promise<TestPatient> {
  // Backend uses `nickname` as the display name (register_patient stores
  // name=nickname). The legacy fixture took an opts.name that was ignored.
  // Now we use opts.name AS the nickname when provided, so specs that
  // assert on a specific name (e.g. 06-patient-list searches for "张秀兰")
  // see what they wrote. Per-doctor uniqueness is preserved by the reset
  // endpoint wiping patients before each test.
  const nickname = opts.name || uniqueNickname("patient");
  // Backend stores gender verbatim; production data uses 男/女 (see
  // OnboardingWizard createOnboardingPatientEntry).
  const gender = opts.gender || "男";
  const passcode = randomPasscode();

  // Patient registration now requires a per-doctor `attach_code` (replaces
  // the legacy `doctor_id` body field — that endpoint dropped 2026-04-26
  // alongside the public `/unified/doctors` enumeration). Fetch the doctor's
  // permanent code via the doctor-side endpoint first.
  const codeRes = await request.get(
    `${API_BASE_URL}/api/manage/patient-attach-code?doctor_id=${encodeURIComponent(doctorId)}`,
  );
  expect(
    codeRes.ok(),
    `attach code fetch failed: ${codeRes.status()} ${await codeRes.text()}`,
  ).toBeTruthy();
  const { code: attach_code } = await codeRes.json();

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/patient`, {
    data: {
      nickname,
      passcode,
      attach_code,
      gender,
    },
  });
  expect(
    res.ok(),
    `register patient failed: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
  const body = await res.json();
  // Response shape:  { token, role: "patient", doctor_id, patient_id, name }
  return {
    patientId: String(body.patient_id),
    doctorId: body.doctor_id || doctorId,
    name: body.name || nickname,
    nickname,
    passcode,
    gender,
    token: body.token,
  };
}

/**
 * Log in as a doctor through the real login form, then bypass the onboarding
 * wizard + setup dialog so subsequent navigations land on the doctor workbench.
 *
 * Why login through the UI instead of injecting localStorage?
 * - The zustand `doctor-session` blob requires hydration before the auth
 *   guard in App.jsx recognizes the session. If you inject the blob and
 *   navigate to `/doctor`, there's a race: the auth guard fires before
 *   hydration, sees no `accessToken`, and redirects to `/login`. Logging in
 *   through the form calls `setAuth()` synchronously, so the store is warm
 *   from the first render.
 * - The login form also calls `setWebToken()`, writes `unified_auth_*`
 *   localStorage keys, and triggers the miniprogram postMessage path (no-op
 *   in headless Chrome). All of these mirror production behavior exactly.
 *
 * After login we pre-set two keys to skip the wizard:
 * - `onboarding_wizard_done:<id>` — checked by `isWizardDone()` in
 *   DoctorPage.jsx:747, redirects to `/doctor/onboarding` if missing.
 * - `onboarding_setup_done:<id>` — checked by `useDoctorPageState` in
 *   DoctorPage.jsx:714, shows a name-input overlay if missing.
 */
export async function authenticateDoctorPage(page: Page, doctor: TestDoctor) {
  await page.goto("/login");

  // Pre-set wizard + setup flags BEFORE login redirects to /doctor. The
  // DoctorPage useEffect that checks these fires on mount — by the time the
  // login redirect lands, the keys are already present.
  await page.evaluate((id) => {
    localStorage.setItem(
      `onboarding_wizard_done:${id}`,
      JSON.stringify({ status: "completed", completedAt: new Date().toISOString() }),
    );
    localStorage.setItem(`onboarding_setup_done:${id}`, "1");
  }, doctor.doctorId);

  // Fill the doctor login form. Tab 0 (医生) is the default.
  // antd-mobile Form.Item renders labels as plain divs (no aria-label / for=),
  // so getByLabel can't locate the inputs. Use placeholder text instead.
  await page.getByPlaceholder("请输入昵称").fill(doctor.nickname);
  await page.getByPlaceholder("请输入数字口令").fill(doctor.passcode);
  await page.getByRole("button", { name: "登录" }).click();

  // Wait for the login to succeed and land on the doctor workbench.
  await page.waitForURL(/\/doctor/, { timeout: 15_000 });
}

/**
 * Log in as a patient through the real login form. Patient login uses the
 * same /login page but on the "患者" tab with phone + birth year.
 *
 * After login the app writes patient_portal_* localStorage keys and
 * redirects to /patient. We wait for that redirect as the success signal.
 */
export async function authenticatePatientPage(
  page: Page,
  patient: TestPatient,
  doctorNameOrOpts?: string | { skipOnboarding?: boolean },
) {
  // Legacy 3rd-arg call sites passed doctor.name (now ignored). New callers
  // pass an options object. Detect which flavor we got.
  const opts: { skipOnboarding?: boolean } =
    typeof doctorNameOrOpts === "object" && doctorNameOrOpts !== null
      ? doctorNameOrOpts
      : {};
  const skipOnboarding = opts.skipOnboarding !== false;

  await page.goto("/login");

  if (skipOnboarding) {
    // Pre-set the onboarding-done flag BEFORE login redirects to /patient.
    // PatientPage.jsx initializes its `onboardingDone` React state via a
    // useState initializer that reads localStorage exactly once at mount.
    // If the flag isn't set before the post-login mount, the onboarding
    // overlay renders and stays — setting localStorage after the fact does
    // not re-trigger the initializer. Mirrors the doctor wizard pre-set
    // pattern in authenticateDoctorPage().
    //
    // Pass `{ skipOnboarding: false }` from specs that explicitly want to
    // see and interact with the onboarding overlay (e.g. 24-onboarding).
    await page.evaluate((pid) => {
      localStorage.setItem(`patient_onboarding_done_${pid}`, "1");
      // PatientPage useState reads this key to look up the patient id; pre-set
      // it so the first mount sees a hit on the keyed onboarding-done check.
      localStorage.setItem("patient_portal_patient_id", pid);
    }, patient.patientId);
  }

  // Switch to 患者 tab (index 1).
  await page.getByRole("tab", { name: "患者" }).click();

  await page.getByPlaceholder("请输入昵称").fill(patient.nickname);
  await page.getByPlaceholder("请输入数字口令").fill(patient.passcode);
  await page.getByRole("button", { name: "登录" }).click();

  await page.waitForURL(/\/patient/, { timeout: 15_000 });
}

type Fixtures = {
  doctor: TestDoctor;
  patient: TestPatient;
  doctorPage: Page;
  patientPage: Page;
  steps: StepRecorder;
};

export const test = base.extend<Fixtures>({
  doctor: async ({ request }, use) => {
    // Default: log in as the shared seeded test doctor (test/123456).
    // For specs that explicitly need a freshly registered doctor (seed-smoke
    // contract tests, auth tests), call `registerDoctor(request)` directly
    // inside the test body instead of using this fixture.
    const d = await loginAsTestDoctor(request);
    await use(d);
  },

  patient: async ({ request, doctor }, use) => {
    // Default: log in as the shared seeded test patient (test/123456) under
    // the test doctor. For specs that explicitly need a freshly registered
    // patient (seed-smoke contract tests), call `registerPatient(request,
    // doctorId)` directly inside the test body instead of using this fixture.
    const p = await loginAsTestPatient(request, doctor.doctorId);
    await use(p);
  },

  doctorPage: async ({ page, doctor }, use) => {
    await authenticateDoctorPage(page, doctor);
    // Inject click indicator AFTER auth (page is loaded and DOM exists).
    const { injectClickIndicator } = await import("./click-indicator");
    await injectClickIndicator(page);
    await use(page);
  },

  patientPage: async ({ page, patient }, use) => {
    await authenticatePatientPage(page, patient);
    const { injectClickIndicator } = await import("./click-indicator");
    await injectClickIndicator(page);
    await use(page);
  },

  steps: async ({}, use, testInfo) => {
    const recorder = new StepRecorder(testInfo);
    await use(recorder);
    // Teardown: write result.json after the test body finishes.
    await recorder.writeResult(testInfo.titlePath[0] || "", testInfo.title);
  },
});

export { expect };
export { StepRecorder } from "./step-recorder";
export type { Step, TestResult } from "./step-recorder";
