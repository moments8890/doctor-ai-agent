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

export const API_BASE_URL = process.env.E2E_API_BASE_URL || "http://127.0.0.1:8000";

export interface TestDoctor {
  doctorId: string;
  name: string;
  phone: string;
  yearOfBirth: number;
  token: string;
}

export interface TestPatient {
  patientId: string;
  doctorId: string;
  name: string;
  phone: string;
  yearOfBirth: number;
  gender: string;
  token: string;
}

/**
 * Generate a unique 11-digit phone so re-runs on a shared DB don't collide on
 * the backend's "phone already registered" guard. Keeps the 13x prefix the
 * unified/register endpoint accepts for mobile numbers.
 */
function uniquePhone(prefix: "doctor" | "patient"): string {
  const lead = prefix === "doctor" ? "138" : "139";
  // 11-digit total: lead (3) + random (8)
  const rand = String(Math.floor(Math.random() * 1e8)).padStart(8, "0");
  return lead + rand;
}

export async function registerDoctor(
  request: import("@playwright/test").APIRequestContext,
  opts: { name?: string; yearOfBirth?: number } = {},
): Promise<TestDoctor> {
  // Append random suffix to name to avoid DB uniqueness collisions across runs
  const suffix = String(Math.floor(Math.random() * 1e6)).padStart(6, "0");
  const name = (opts.name || "E2E测试医生") + suffix;
  const yearOfBirth = opts.yearOfBirth || 1980;
  const phone = uniquePhone("doctor");

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/doctor`, {
    data: { name, phone, year_of_birth: yearOfBirth, invite_code: "WELCOME" },
  });
  expect(
    res.ok(),
    `register doctor failed: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
  const body = await res.json();
  // Real response shape (src/infra/auth/unified.py:261):
  //   { token, role: "doctor", doctor_id, name }
  return {
    doctorId: body.doctor_id,
    name: body.name || name,
    phone,
    yearOfBirth,
    token: body.token,
  };
}

export async function registerPatient(
  request: import("@playwright/test").APIRequestContext,
  doctorId: string,
  opts: { name?: string; yearOfBirth?: number; gender?: string } = {},
): Promise<TestPatient> {
  const name = opts.name || "E2E测试患者";
  const yearOfBirth = opts.yearOfBirth || 1990;
  // Backend stores gender verbatim; production data uses 男/女 (see
  // OnboardingWizard createOnboardingPatientEntry). BUG-06 regressed when the
  // NL search filter only matched male/female; the fix normalizes both, but
  // seeded patients should match what production actually writes.
  const gender = opts.gender || "男";
  const phone = uniquePhone("patient");

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/patient`, {
    data: {
      name,
      phone,
      year_of_birth: yearOfBirth,
      doctor_id: doctorId,
      gender,
    },
  });
  expect(
    res.ok(),
    `register patient failed: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
  const body = await res.json();
  // Real response shape (src/infra/auth/unified.py:313):
  //   { token, role: "patient", doctor_id, patient_id, name }
  // patient_id is a DB integer row PK; coerce to string so selectors &
  // URL params treat it consistently.
  return {
    patientId: String(body.patient_id),
    doctorId: body.doctor_id || doctorId,
    name: body.name || name,
    phone,
    yearOfBirth,
    gender,
    token: body.token,
  };
}

/**
 * Hydrate the doctor session the same way the app does after a successful login.
 *
 * The doctor store (frontend/web/src/store/doctorStore.js) uses
 * `persist(…, { name: "doctor-session" })`, which means localStorage carries
 * a single JSON blob:
 *
 *   localStorage["doctor-session"] = JSON.stringify({
 *     state: { doctorId, doctorName, accessToken },
 *     version: 0,
 *   })
 *
 * api.js `_getToken()` falls back to reading that blob directly if the
 * module-level cache is empty, so setting it *before* the first navigation is
 * enough to make authed API calls from the first request onward.
 *
 * We additionally seed `unified_auth_doctor_id / _token / _name` because
 * App.jsx `restoreRealSession()` reads them as a fallback when the zustand
 * store looks synthetic in DEV_MODE. Writing both paths is cheap insurance.
 */
export async function authenticateDoctorPage(page: Page, doctor: TestDoctor) {
  // localStorage is origin-scoped — we have to land on the frontend origin
  // before we can write to it. An empty page avoids triggering any app code.
  await page.goto("/login");
  await page.evaluate((d) => {
    const blob = JSON.stringify({
      state: {
        doctorId: d.doctorId,
        doctorName: d.name,
        accessToken: d.token,
      },
      version: 0,
    });
    localStorage.setItem("doctor-session", blob);
    localStorage.setItem("unified_auth_doctor_id", d.doctorId);
    localStorage.setItem("unified_auth_token", d.token);
    localStorage.setItem("unified_auth_name", d.name);
  }, doctor);
}

/**
 * Hydrate the patient session the same way the app does after login.
 * The patient app reads these localStorage keys directly.
 */
export async function authenticatePatientPage(page: Page, patient: TestPatient, doctorName?: string) {
  await page.goto("/login");
  await page.evaluate((p) => {
    localStorage.setItem("patient_portal_token", p.token);
    localStorage.setItem("patient_portal_name", p.name);
    localStorage.setItem("patient_portal_doctor_id", p.doctorId);
    localStorage.setItem("patient_portal_doctor_name", p.doctorName || "");
    localStorage.setItem("patient_portal_patient_id", p.patientId);
  }, { ...patient, doctorName: doctorName || "" });
}

type Fixtures = {
  doctor: TestDoctor;
  patient: TestPatient;
  doctorPage: Page;
  patientPage: Page;
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
    await use(page);
  },

  patientPage: async ({ page, patient, doctor }, use) => {
    await authenticatePatientPage(page, patient, doctor.name);
    await use(page);
  },
});

export { expect };
