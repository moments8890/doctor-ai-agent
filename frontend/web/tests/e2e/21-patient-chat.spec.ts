/**
 * Workflow 21 — Patient chat
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { sendDoctorReply } from "./fixtures/seed";

test.describe("工作流 21 — 患者对话", () => {
  test("患者发送消息且无虚假AI回复", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    // Mark onboarding done so overlay doesn't block input
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);

    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");
    await steps.capture(page, "打开患者聊天页面");

    await page.getByPlaceholder("请输入…").fill("医生你好，我头痛");
    await page.getByLabel("发送").click();

    await expect(page.getByText("医生你好，我头痛")).toBeVisible();
    await steps.capture(page, "消息发送成功");

    // No fake reply should appear
    await page.waitForTimeout(2000);
    await expect(page.getByText("收到您的消息")).not.toBeVisible();
    await steps.capture(page, "确认无虚假回复");
  });

  test("医生回复显示医生姓名", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);

    await sendDoctorReply(request, doctor, patient.patientId, "注意休息，明天来复查");

    await authenticatePatientPage(page, patient, doctor.name);
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);
    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("注意休息，明天来复查")).toBeVisible({ timeout: 15000 });
    await steps.capture(page, "医生回复显示成功");
  });
});
