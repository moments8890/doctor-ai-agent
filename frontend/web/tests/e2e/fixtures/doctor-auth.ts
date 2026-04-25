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

export const API_BASE_URL = process.env.E2E_API_BASE_URL || "http://127.0.0.1:8000";

export interface TestDoctor {
  doctorId: string;
  name: string;
  nickname: string;
  passcode: string;
  token: string;
}

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

export async function registerPatient(
  request: import("@playwright/test").APIRequestContext,
  doctorId: string,
  opts: { name?: string; gender?: string } = {},
): Promise<TestPatient> {
  const name = opts.name || "E2E测试患者";
  // Backend stores gender verbatim; production data uses 男/女 (see
  // OnboardingWizard createOnboardingPatientEntry). BUG-06 regressed when the
  // NL search filter only matched male/female; the fix normalizes both, but
  // seeded patients should match what production actually writes.
  const gender = opts.gender || "男";
  const nickname = uniqueNickname("patient");
  const passcode = randomPasscode();

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/patient`, {
    data: {
      nickname,
      passcode,
      doctor_id: doctorId,
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
    name: body.name || name,
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
export async function authenticatePatientPage(page: Page, patient: TestPatient) {
  await page.goto("/login");

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
    const d = await registerDoctor(request);
    await use(d);
  },

  patient: async ({ request, doctor }, use) => {
    const p = await registerPatient(request, doctor.doctorId);
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
