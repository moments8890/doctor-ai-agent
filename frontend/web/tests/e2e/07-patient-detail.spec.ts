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

    // 1.2 — bio header. On mobile, list pane elements are hidden in DOM.
    // Wait for any instance to become visible using a filter.
    await doctorPage.getByText(patient.name).first().waitFor({ state: "attached", timeout: 10_000 });
    const nameCount = await doctorPage.getByText(patient.name).count();
    let found = false;
    for (let i = 0; i < nameCount; i++) {
      if (await doctorPage.getByText(patient.name).nth(i).isVisible()) { found = true; break; }
    }
    expect(found, `patient name "${patient.name}" should be visible`).toBeTruthy();
    // Gender text appears in hidden list pane on mobile. Check bio section
    // rendered by verifying any bio field (birth year, file date, etc.)
    await expect(doctorPage.getByText(/出生|建档/).first()).toBeVisible();

    // 2.1 — sub-tabs (use .first() — "全部" appears in both tab and filter)
    for (const label of ["全部", "病历", "问诊"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // 2.2 — record row with 预问诊 badge + 待审核 status
    await expect(doctorPage.getByText("预问诊").first()).toBeVisible();
    await expect(doctorPage.getByText("待审核").first()).toBeVisible();

    // 2.3 — tap record → review page
    await doctorPage.getByText("预问诊").first().click();
    await expect(doctorPage).toHaveURL(new RegExp(`/doctor/review/${recordId}`));
  });

  test("2.4 — empty records state", async ({ doctorPage, patient }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    await expect(doctorPage.getByText("暂无病历")).toBeVisible();
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

    // "患者消息" appears multiple times (section header, link row).
    // Use .first() to avoid strict mode violation. May need scrolling on mobile.
    // On mobile, the first match is a hidden list card subtitle. The visible
    // one is further down — use .last() to get the detail page's chat link.
    const chatLink = doctorPage.getByText(/查看聊天记录/).last();
    await chatLink.scrollIntoViewIfNeeded();
    await expect(chatLink).toBeVisible({ timeout: 10_000 });
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

    // The overflow icon is MoreHorizIcon inside a clickable Box (no aria-label).
    // Use the MUI SVG icon's data-testid attribute.
    const moreIcon = doctorPage.locator('[data-testid="MoreHorizIcon"]').first();
    await expect(moreIcon).toBeVisible({ timeout: 10_000 });
    await moreIcon.click();

    // Assert the sheet opened with the danger action visible.
    const deleteRow = doctorPage.getByText("删除患者");
    await expect(deleteRow).toBeVisible();
    await deleteRow.click();

    // ConfirmDialog opens — uses MUI Dialog with role="dialog".
    await expect(doctorPage.getByText(/所有病历和任务将一并删除/)).toBeVisible();

    // Cancel via the grey button — ConfirmDialog uses AppButton (div, not button).
    // Scope to the dialog to avoid matching other elements.
    const dialog = doctorPage.locator('[role="dialog"]');
    await dialog.getByText("保留", { exact: true }).click();

    // Patient still visible after cancel — check URL stayed on patient detail.
    await expect(doctorPage).toHaveURL(new RegExp(`patients/${patient.patientId}`));
  });
});
