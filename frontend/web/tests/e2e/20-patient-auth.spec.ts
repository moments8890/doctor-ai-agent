/**
 * Workflow 20 — Patient auth smoke
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("Workflow 20 — Patient auth", () => {
  test("patient portal loads with 4 bottom nav tabs", async ({ page, request }) => {
    const doctor = await registerDoctor(request, { name: "E2E患者端医生" });
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("主页")).toBeVisible();
    await expect(page.getByText("病历")).toBeVisible();
    await expect(page.getByText("任务")).toBeVisible();
    await expect(page.getByText("我的")).toBeVisible();
  });
});
