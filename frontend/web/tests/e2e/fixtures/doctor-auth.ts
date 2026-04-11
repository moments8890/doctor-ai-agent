/**
 * doctorAuth fixture — registers a fresh test doctor and test patient,
 * then returns a `page` pre-authed into the doctor app.
 *
 * Usage:
 *
 *   import { test, expect } from "../fixtures/doctor-auth";
 *
 *   test("does the thing", async ({ doctorPage, doctor, patient }) => {
 *     await doctorPage.goto("/doctor");
 *     await expect(doctorPage.getByText(doctor.name)).toBeVisible();
 *   });
 *
 * The fixture is **session-scoped** per spec file — one doctor per spec,
 * re-used across tests within that file. This keeps setup cost down while
 * preventing cross-file state leakage.
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
  name: string;
  phone: string;
  yearOfBirth: number;
  token: string;
}

/**
 * Generate a unique phone number for this test run so re-runs on the same DB
 * don't collide on the "phone already registered" 400.
 */
function uniquePhone(prefix: string): string {
  // prefix (e.g. "138E2E") padded to 11 digits with timestamp tail.
  const tail = String(Date.now()).slice(-5);
  return (prefix + tail).replace(/[A-Z]/g, "0").slice(0, 11);
}

export async function registerDoctor(
  request: import("@playwright/test").APIRequestContext,
  opts: { name?: string; yearOfBirth?: number } = {},
): Promise<TestDoctor> {
  const name = opts.name || "E2E测试医生";
  const yearOfBirth = opts.yearOfBirth || 1980;
  const phone = uniquePhone("1380000");

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/doctor`, {
    data: { name, phone, year_of_birth: yearOfBirth, invite_code: "WELCOME" },
  });
  expect(res.ok(), `register doctor failed: ${await res.text()}`).toBeTruthy();
  const body = await res.json();

  return {
    doctorId: body.doctor_id || body.user_id,
    name,
    phone,
    yearOfBirth,
    token: body.token,
  };
}

export async function registerPatient(
  request: import("@playwright/test").APIRequestContext,
  doctorId: string,
  opts: { name?: string; yearOfBirth?: number; gender?: "male" | "female" } = {},
): Promise<TestPatient> {
  const name = opts.name || "E2E测试患者";
  const yearOfBirth = opts.yearOfBirth || 1990;
  const gender = opts.gender || "male";
  const phone = uniquePhone("1390000");

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/patient`, {
    data: {
      name,
      phone,
      year_of_birth: yearOfBirth,
      doctor_id: doctorId,
      gender,
    },
  });
  expect(res.ok(), `register patient failed: ${await res.text()}`).toBeTruthy();
  const body = await res.json();

  return {
    patientId: body.patient_id || body.user_id,
    name,
    phone,
    yearOfBirth,
    token: body.token,
  };
}

/**
 * Write the doctor's auth token + id into localStorage so the frontend
 * treats the page as logged-in. Mirrors what the real /login form does.
 */
export async function authenticateDoctorPage(page: Page, doctor: TestDoctor) {
  // Must navigate to the frontend origin first before touching localStorage.
  await page.goto("/");
  await page.evaluate((d) => {
    // Keys mirror src/store/doctorStore.js / ApiContext.jsx.
    localStorage.setItem("doctor_token", d.token);
    localStorage.setItem("doctor_id", d.doctorId);
    localStorage.setItem("doctor_name", d.name);
  }, doctor);
}

type Fixtures = {
  doctor: TestDoctor;
  patient: TestPatient;
  doctorPage: Page;
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
});

export { expect };
