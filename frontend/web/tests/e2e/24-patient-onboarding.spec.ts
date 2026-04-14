/**
 * Workflow 24 — Patient onboarding
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("工作流 24 — 患者引导", () => {
  test("首次患者看到引导页，关闭后不再显示", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    await page.evaluate((pid) => {
      localStorage.setItem("patient_portal_patient_id", pid);
    }, patient.patientId);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("开始使用")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("随时咨询")).toBeVisible();
    await steps.capture(page, "引导页面显示");

    await page.getByText("开始使用").click();

    await expect(page.getByText("开始使用")).not.toBeVisible();
    await steps.capture(page, "点击开始使用后引导消失");

    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("开始使用")).not.toBeVisible({ timeout: 3000 });
    await steps.capture(page, "刷新后引导不再显示");
  });
});
