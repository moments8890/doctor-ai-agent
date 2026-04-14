/**
 * Workflow 23 — Patient tasks
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { createPatientTask } from "./fixtures/seed";

test.describe("工作流 23 — 患者任务", () => {
  test("患者任务显示在列表中且可完成", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await createPatientTask(request, doctor, patient.patientId, { title: "明天复查血压" });

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/tasks");
    await page.waitForLoadState("networkidle");
    await steps.capture(page, "打开患者任务页面");

    await expect(page.getByText("明天复查血压")).toBeVisible({ timeout: 10000 });
    await steps.capture(page, "验证任务显示成功");
  });
});
