/**
 * Workflow 20 — Patient auth smoke
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("Workflow 20 — Patient auth", () => {
  test("patient portal loads with 4 bottom nav tabs", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    // Mark onboarding done so it doesn't block nav assertions
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");

    // Use role selectors to avoid matching onboarding/quickaction text
    await expect(page.getByRole("button", { name: "主页" })).toBeVisible();
    await expect(page.getByRole("button", { name: "病历" })).toBeVisible();
    await expect(page.getByRole("button", { name: "任务" })).toBeVisible();
    await expect(page.getByRole("button", { name: "我的" })).toBeVisible();
  });
});
