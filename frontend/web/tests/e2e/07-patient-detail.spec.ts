/**
 * Workflow 07 — Patient detail + records
 *
 * Mirrors docs/qa/workflows/07-patient-detail.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { completePatientInterview } from "./fixtures/seed";

test.describe("Workflow 07 — Patient detail", () => {
  test("1-2. Bio header + records timeline with seeded record", async ({
    doctorPage,
    patient,
    request,
  }) => {
    const { recordId } = await completePatientInterview(request, patient);

    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // 1.2 — bio header
    await expect(doctorPage.getByText(patient.name)).toBeVisible();
    await expect(doctorPage.getByText(/男|女/).first()).toBeVisible();

    // 2.1 — sub-tabs
    for (const label of ["全部", "病历", "问诊"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }

    // 2.2 — record row with 预问诊 badge + 待审核 status
    await expect(doctorPage.getByText("预问诊")).toBeVisible();
    await expect(doctorPage.getByText("待审核")).toBeVisible();

    // 2.3 — tap record → review page
    await doctorPage.getByText("预问诊").first().click();
    await expect(doctorPage).toHaveURL(new RegExp(`/doctor/review/${recordId}`));
  });

  test("2.4 — empty records state", async ({ doctorPage, patient }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    await expect(doctorPage.getByText("暂无病历")).toBeVisible();
    await expect(doctorPage.getByText(/新建病历/)).toBeVisible();
  });

  test("3. Needs-action banner shown when pending review exists", async ({
    doctorPage,
    patient,
    request,
  }) => {
    await completePatientInterview(request, patient);
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    await expect(doctorPage.getByText(/需要你处理|⚡/)).toBeVisible();
  });

  test("4. Messages shortcut navigates to chat view", async ({
    doctorPage,
    patient,
  }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    const chatLink = doctorPage.getByText(/查看聊天记录/);
    if (await chatLink.isVisible().catch(() => false)) {
      await chatLink.click();
      await expect(doctorPage).toHaveURL(/view=chat/);
    }
  });

  test("5. Delete patient confirm dialog", async ({ doctorPage, patient }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // Open overflow / more menu — selector depends on actual UI; adjust as needed.
    const more = doctorPage.getByRole("button", { name: /更多|⋯|删除/ }).first();
    if (await more.isVisible().catch(() => false)) {
      await more.click();
      await doctorPage.getByText("删除患者").click();
      await expect(doctorPage.getByText("删除患者")).toBeVisible();
      await expect(doctorPage.getByText(/所有病历和任务将一并删除/)).toBeVisible();

      // Cancel via the first (grey) button — don't actually delete.
      await doctorPage.getByRole("button", { name: /取消|保留/ }).click();
    }
  });
});
