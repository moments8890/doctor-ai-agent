/**
 * Workflow 22 — Patient records
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { completePatientInterview, addKnowledgeText } from "./fixtures/seed";

test.describe("Workflow 22 — Patient records", () => {
  test("completed interview shows in records list", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await addKnowledgeText(request, doctor, "高血压患者头痛需排除高血压脑病");
    await completePatientInterview(request, patient);

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/records");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("预问诊", { exact: true })).toBeVisible({ timeout: 10000 });
  });

  test("filter tabs switch between record types", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await addKnowledgeText(request, doctor, "高血压患者头痛需排除高血压脑病");
    await completePatientInterview(request, patient);

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/records");
    await page.waitForLoadState("networkidle");

    await page.getByText("问诊", { exact: true }).click();
    await expect(page.getByText("预问诊", { exact: true })).toBeVisible();
  });
});
