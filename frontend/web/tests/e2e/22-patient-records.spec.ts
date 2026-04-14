/**
 * Workflow 22 — Patient records
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { completePatientInterview, addKnowledgeText } from "./fixtures/seed";

test.describe("工作流 22 — 患者病历", () => {
  test("完成问诊后病历列表中显示记录", async ({ page, request, steps }) => {
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
    await steps.capture(page, "打开患者病历页面");

    await expect(page.getByText("预问诊", { exact: true })).toBeVisible({ timeout: 10000 });
    await steps.capture(page, "验证病历记录显示");
  });

  test("筛选标签切换病历类型", async ({ page, request, steps }) => {
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
    await steps.capture(page, "切换筛选标签");
    await expect(page.getByText("预问诊", { exact: true })).toBeVisible();
    await steps.capture(page, "验证筛选结果");
  });
});
