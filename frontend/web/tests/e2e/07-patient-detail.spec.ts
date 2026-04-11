/**
 * Workflow 07 — Patient detail + records
 *
 * Mirrors docs/qa/workflows/07-patient-detail.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  completePatientInterview,
  sendPatientMessage,
} from "./fixtures/seed";

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
    request,
  }) => {
    // Seed a message so the "患者消息" section is non-empty and the link
    // is guaranteed to render. Removes the old soft-assert guard.
    await sendPatientMessage(request, patient, "医生，复查结果出来了。");
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    const chatLink = doctorPage.getByText(/查看聊天记录|患者消息/);
    await expect(chatLink).toBeVisible();
    await chatLink.click();
    await expect(doctorPage).toHaveURL(/view=chat/);
  });

  test("5. Delete patient confirm dialog", async ({
    doctorPage,
    patient,
    request,
  }) => {
    // Seed a record so the patient page is fully populated — the overflow
    // menu is always visible once the page loads.
    await completePatientInterview(request, patient);
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // The overflow icon is a clickable Box, not a standard button. Look
    // for common identifiers: aria-label, the MoreVert icon text, or the
    // menu items themselves. PatientDetail.jsx uses a SheetDialog with menu
    // items, typically triggered by an icon in the header.
    // First, try the more-icon approach; fall back to header actions.
    const moreIcon = doctorPage.locator('[aria-label="更多"], [aria-label="操作"]').first();
    if (await moreIcon.count() > 0) {
      await moreIcon.click();
    } else {
      // If there's a visible "更多" text button, use that instead.
      await doctorPage.getByText("更多").first().click();
    }

    // Assert the sheet opened with the danger action visible.
    const deleteRow = doctorPage.getByText("删除患者");
    await expect(deleteRow).toBeVisible();
    await deleteRow.click();

    // ConfirmDialog opens.
    await expect(doctorPage.getByText(/所有病历和任务将一并删除/)).toBeVisible();

    // Cancel via the grey button — don't actually delete the test patient.
    await doctorPage.getByRole("button", { name: /取消|保留/ }).click();

    // Patient still visible after cancel.
    await expect(doctorPage.getByText(patient.name)).toBeVisible();
  });
});
