/**
 * Workflow 07 — Patient detail + records
 *
 * Mirrors docs/qa/workflows/07-patient-detail.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  completePatientIntake,
  sendPatientMessage,
} from "./fixtures/seed";

test.describe("工作流 07 — 患者详情", () => {
  test("1-2. 基本信息头部和病历时间线", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    const { recordId } = await completePatientIntake(request, patient);

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

    await steps.capture(doctorPage, "患者详情页头部", "显示患者姓名和基本信息");

    // 2.1 — sub-tabs (use .first() — "全部" appears in both tab and filter)
    for (const label of ["全部", "病历", "问诊"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // 2.2 — record row with 预问诊 badge + 待审核 status
    await expect(doctorPage.getByText("预问诊").first()).toBeVisible();
    await expect(doctorPage.getByText("待审核").first()).toBeVisible();

    await steps.capture(doctorPage, "病历记录列表", "显示预问诊记录和待审核状态");

    // 2.3 — tap record → review page
    await doctorPage.getByText("预问诊").first().click();
    await expect(doctorPage).toHaveURL(new RegExp(`/doctor/review/${recordId}`));

    await steps.capture(doctorPage, "跳转审核页面", "点击记录后进入诊断审核页");
  });

  test("2.4 — 空病历状态", async ({ doctorPage, patient, steps }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    await expect(doctorPage.getByText("暂无病历")).toBeVisible();

    await steps.capture(doctorPage, "空病历状态", "无病历时显示暂无病历提示");
  });

  test("3. 有待审核记录时显示待处理横幅", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    await completePatientIntake(request, patient);
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    await expect(doctorPage.getByText(/需要你处理|⚡/)).toBeVisible();

    await steps.capture(doctorPage, "待处理横幅", "有待审核记录时显示处理提示");
  });

  test("4. 消息快捷入口跳转聊天视图", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    // Seed a message so the "患者消息" section is non-empty and the link
    // is guaranteed to render. Removes the old soft-assert guard.
    await sendPatientMessage(request, patient, "医生，复查结果出来了。");
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    await steps.capture(doctorPage, "患者详情含消息", "已发送消息的患者详情页");

    // "患者消息" appears multiple times (section header, link row).
    // Use .first() to avoid strict mode violation. May need scrolling on mobile.
    // On mobile, the first match is a hidden list card subtitle. The visible
    // one is further down — use .last() to get the detail page's chat link.
    const chatLink = doctorPage.getByText(/查看聊天记录/).last();
    await chatLink.scrollIntoViewIfNeeded();
    await expect(chatLink).toBeVisible({ timeout: 10_000 });
    await chatLink.click();
    await expect(doctorPage).toHaveURL(/view=chat/);

    await steps.capture(doctorPage, "进入聊天视图", "点击查看聊天记录后跳转");
  });

  test("5. 删除患者确认弹窗", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    // Seed a record so the patient page is fully populated — the overflow
    // menu is always visible once the page loads.
    await completePatientIntake(request, patient);
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // The overflow icon is MoreHorizIcon inside a clickable Box (no aria-label).
    // Use the MUI SVG icon's data-testid attribute.
    const moreIcon = doctorPage.locator('[data-testid="MoreHorizIcon"]').first();
    await expect(moreIcon).toBeVisible({ timeout: 10_000 });
    await moreIcon.click();

    // Assert the sheet opened with the danger action visible.
    const deleteRow = doctorPage.getByText("删除患者");
    await expect(deleteRow).toBeVisible();

    await steps.capture(doctorPage, "打开操作菜单", "显示删除患者选项");

    await deleteRow.click();

    // ConfirmDialog opens — uses MUI Dialog with role="dialog".
    await expect(doctorPage.getByText(/所有病历和任务将一并删除/)).toBeVisible();

    await steps.capture(doctorPage, "删除确认弹窗", "显示删除确认对话框");

    // Cancel via the grey button — ConfirmDialog uses AppButton (div, not button).
    // Scope to the dialog to avoid matching other elements.
    const dialog = doctorPage.locator('[role="dialog"]');
    await dialog.getByText("保留", { exact: true }).click();

    // Patient still visible after cancel — check URL stayed on patient detail.
    await expect(doctorPage).toHaveURL(new RegExp(`patients/${patient.patientId}`));

    await steps.capture(doctorPage, "取消删除后保留", "取消后仍停留在患者详情页");
  });
});
