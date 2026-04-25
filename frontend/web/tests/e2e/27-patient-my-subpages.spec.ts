import { test, expect } from "@playwright/test";

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

test.describe("patient MyPage subpages", () => {
  test.beforeEach(async ({ page }) => {
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

  test("MyPage → 关于 → back", async ({ page }) => {
    await page.goto("/patient/profile");
    await page.getByText("关于", { exact: true }).first().click();
    await expect(page).toHaveURL(/\/patient\/profile\/about/);
    await expect(page.getByText("患者助手")).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/patient\/profile(?!\/about)/);
  });

  test("MyPage → 隐私政策 → back", async ({ page }) => {
    await page.goto("/patient/profile");
    await page.getByText("隐私政策", { exact: true }).first().click();
    await expect(page).toHaveURL(/\/patient\/profile\/privacy/);
    // Any paragraph from PrivacyContent — the section heading is stable.
    await expect(page.getByText("一、我们收集的信息")).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/patient\/profile(?!\/privacy)/);
  });

  test("font Popup selects 特大 and persists", async ({ page }) => {
    await page.goto("/patient/profile");
    await page.getByText("字体大小", { exact: true }).click();

    // Popup with 标准 / 大 / 特大 radios
    await expect(page.getByText("标准", { exact: true })).toBeVisible();
    await expect(page.getByText("大", { exact: true })).toBeVisible();
    await expect(page.getByText("特大", { exact: true })).toBeVisible();

    await page.getByText("特大", { exact: true }).click();

    await page.reload();
    await page.getByText("字体大小", { exact: true }).click();

    // After reload + reopen, the 特大 radio should be selected.
    const extraLargeRadio = page
      .locator(".adm-radio")
      .filter({ hasText: "特大" });
    await expect(extraLargeRadio).toHaveClass(/adm-radio-checked/);
  });
});
