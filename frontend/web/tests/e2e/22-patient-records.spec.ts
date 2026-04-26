/**
 * Workflow 22 — Patient records
 *
 * As of 2026-04-24, RecordsTab is a single chronological timeline grouped by
 * month — no view toggle, no type filter. Test only the simplified surface.
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { completePatientIntake, addKnowledgeText } from "./fixtures/seed";

test.describe("工作流 22 — 患者病历", () => {
  test("完成问诊后病历列表中显示记录", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await addKnowledgeText(request, doctor, "高血压患者头痛需排除高血压脑病");
    await completePatientIntake(request, patient);

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/records");
    await page.waitForLoadState("networkidle");
    await steps.capture(page, "打开患者病历页面");

    // Month section header from groupByMonth — confirms timeline rendered.
    await expect(page.locator("text=/\\d{4}年\\d+月/").first()).toBeVisible({ timeout: 10000 });

    // The seeded intake produces a 预问诊 record card.
    await expect(page.getByText("预问诊", { exact: true })).toBeVisible({ timeout: 10000 });

    // Card row carries the testid so taps can be wired downstream.
    await expect(page.locator('[data-testid="patient-record-row"]').first()).toBeVisible();
    await steps.capture(page, "验证病历记录显示");
  });
});
