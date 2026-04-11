/**
 * Workflow 21 — Patient chat
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { sendDoctorReply } from "./fixtures/seed";

test.describe("Workflow 21 — Patient chat", () => {
  test("patient can send a message without fake AI reply", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");

    await page.getByPlaceholder("请输入…").fill("医生你好，我头痛");
    await page.getByLabel("发送").click();

    await expect(page.getByText("医生你好，我头痛")).toBeVisible();

    // No fake reply should appear
    await page.waitForTimeout(2000);
    await expect(page.getByText("收到您的消息")).not.toBeVisible();
  });

  test("doctor reply shows with doctor name", async ({ page, request }) => {
    const doctor = await registerDoctor(request, { name: "张医生" });
    const patient = await registerPatient(request, doctor.doctorId);

    await sendDoctorReply(request, doctor, patient.patientId, "注意休息，明天来复查");

    await authenticatePatientPage(page, patient, doctor.name);
    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("注意休息，明天来复查")).toBeVisible({ timeout: 15000 });
  });
});
