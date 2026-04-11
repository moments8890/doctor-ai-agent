/**
 * Workflow 23 — Patient tasks
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { createPatientTask } from "./fixtures/seed";

test.describe("Workflow 23 — Patient tasks", () => {
  test("patient task appears in list and can be completed", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await createPatientTask(request, doctor, patient.patientId, { title: "明天复查血压" });

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/tasks");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("明天复查血压")).toBeVisible({ timeout: 10000 });
  });
});
