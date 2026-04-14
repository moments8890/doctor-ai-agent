/**
 * Workflow 20 — Patient auth smoke
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("工作流 20 — 患者登录", () => {
  test("患者端加载显示4个底部标签", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    // Mark onboarding done so it doesn't block nav assertions
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");
    await steps.capture(page, "患者端主页加载");

    // Use role selectors to avoid matching onboarding/quickaction text
    await expect(page.getByRole("button", { name: "主页" })).toBeVisible();
    await expect(page.getByRole("button", { name: "病历" })).toBeVisible();
    await expect(page.getByRole("button", { name: "任务" })).toBeVisible();
    await expect(page.getByRole("button", { name: "我的" })).toBeVisible();
    await steps.capture(page, "验证四个导航标签");
  });
});
