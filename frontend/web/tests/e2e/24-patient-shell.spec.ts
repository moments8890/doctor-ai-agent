import { test, expect } from "@playwright/test";

// Seed identity directly into the new zustand-persisted store
// (`patient-portal-auth`). Bypasses LoginPage, which still writes legacy
// per-key localStorage; PatientPage now reads from the store. The store's
// legacy-key migration IIFE only fires at module-import time, so a SPA
// nav from /login to /patient after login won't pick those up — direct
// seed is the simplest stable path until LoginPage is also migrated.
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

test.describe("patient shell", () => {
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
    await page.goto("/patient");
    await page.waitForURL(/\/patient/);
  });

  test("each tab URL activates the correct tab and NavBar title", async ({ page }) => {
    const cases = [
      { path: "/patient",         title: "聊天" },
      { path: "/patient/chat",    title: "聊天" },
      { path: "/patient/records", title: "病历" },
      { path: "/patient/tasks",   title: "任务" },
      { path: "/patient/profile", title: "我的" },
    ];
    for (const c of cases) {
      await page.goto(c.path);
      await expect(page.locator(".adm-nav-bar-title")).toHaveText(c.title);
    }
  });

  test("records tab shows + action in NavBar", async ({ page }) => {
    await page.goto("/patient/records");
    await expect(page.locator('[aria-label="新问诊"]')).toBeVisible();
  });

  test("other tabs hide the + action", async ({ page }) => {
    for (const path of ["/patient/chat", "/patient/tasks", "/patient/profile"]) {
      await page.goto(path);
      await expect(page.locator('[aria-label="新问诊"]')).toHaveCount(0);
    }
  });

  test("full-screen subpages hide NavBar + TabBar", async ({ page }) => {
    await page.goto("/patient/records/42");
    // Subpage's own NavBar shows, but tab bar is gone
    await expect(page.locator(".adm-tab-bar")).toHaveCount(0);
  });
});
