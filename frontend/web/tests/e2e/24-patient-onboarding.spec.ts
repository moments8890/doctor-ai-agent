/**
 * Workflow 24 — Patient onboarding
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("Workflow 24 — Patient onboarding", () => {
  test("first-time patient sees onboarding, dismiss persists", async ({ page, request }) => {
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

    await page.getByText("开始使用").click();

    await expect(page.getByText("开始使用")).not.toBeVisible();

    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("开始使用")).not.toBeVisible({ timeout: 3000 });
  });
});
