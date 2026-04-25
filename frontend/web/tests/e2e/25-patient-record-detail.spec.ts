import { test, expect } from "@playwright/test";

// Seed identity directly into the new zustand-persisted store
// (`patient-portal-auth`). Bypasses LoginPage, which still writes legacy
// per-key localStorage; PatientPage now reads from the store.
const SEEDED_AUTH = {
  state: {
    token: "seeded-patient-token",
    patientId: "1",
    patientName: "测试患者",
    doctorId: "seeded_doctor",
    doctorName: "测试医生",
  },
  version: 0,
};

const RECORD_FULL = {
  id: 42,
  record_type: "visit",
  structured: {
    chief_complaint: "头痛",
    present_illness: "持续两天",
  },
  created_at: "2026-04-20T10:00:00Z",
};

const RECORD_NO_HISTORY = {
  id: 42,
  record_type: "visit",
  structured: {
    chief_complaint: "x",
    // No past_history / allergy_history / personal_history / family_history.
  },
  created_at: "2026-04-20T10:00:00Z",
};

test.describe("patient record detail", () => {
  test.beforeEach(async ({ page }) => {
    // Stub /api/patient/me so the refresh effect doesn't 401 + clear identity.
    await page.route("**/api/patient/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          patient_id: 1,
          patient_name: "测试患者",
          doctor_id: "seeded_doctor",
          doctor_name: "测试医生",
        }),
      }),
    );
    await page.addInitScript((auth) => {
      localStorage.setItem("patient-portal-auth", JSON.stringify(auth));
    }, SEEDED_AUTH);
  });

  test("list → detail → back round-trip", async ({ page }) => {
    await page.route("**/api/patient/records", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([RECORD_FULL]),
      }),
    );
    await page.route("**/api/patient/records/42", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(RECORD_FULL),
      }),
    );

    await page.goto("/patient/records");
    const row = page.locator('[data-testid="patient-record-row"]').first();
    await expect(row).toBeVisible();
    await row.click();

    await expect(page).toHaveURL(/\/patient\/records\/42/);
    await expect(page.getByText("病历详情")).toBeVisible();
    await expect(page.getByText("头痛")).toBeVisible();
    await expect(page.getByText("持续两天")).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/patient\/records(?!\/42)/);
  });

  test("既往史 card omitted when all 4 history fields empty", async ({ page }) => {
    await page.route("**/api/patient/records/42", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(RECORD_NO_HISTORY),
      }),
    );

    await page.goto("/patient/records/42");
    await expect(page.getByText("主诉", { exact: true })).toBeVisible();
    await expect(page.getByText("既往史", { exact: true })).toHaveCount(0);
  });

  test("error state on fetch failure", async ({ page }) => {
    await page.route("**/api/patient/records/42", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "boom" }),
      }),
    );

    await page.goto("/patient/records/42");
    await expect(page.getByText("加载失败")).toBeVisible();
  });
});
