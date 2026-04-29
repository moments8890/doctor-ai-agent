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

// PatientDetail v2 IA (current source — JumboTabs at line 1198):
//   • Bio header (above tabs): name + 男/女 + 门诊N次 + 最近MM-DD + "+ 新建门诊"
//   • Tabs: 总览 / 病历 / 聊天 — pending counts append " (N)" to the title
//   • 总览 tab default: AI 摘要 card + 临床资料 + chat link "查看聊天记录"
//   • 病历 tab: list of records, or "暂无病历" empty state
//   • Pending banner ("N 条问诊病历需要你审核") shows on 总览 when count > 0
//   • Overflow menu trigger: <button aria-label="更多操作"> — opens the action sheet
test.describe("工作流 07 — 患者详情", () => {
  test("1-2. 基本信息头部和病历时间线", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    const { recordId } = await completePatientIntake(request, patient);

    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // Bio chip line ("男/女 · 门诊N次 · 最近MM-DD") is unique to PatientDetail —
    // uses it as the page-rendered gate, then assert patient.name is on page.
    // Note: the test patient name is "test", which appears in many places
    // (greeting "test的助手", recent activity card, etc.), so a strict-mode
    // assert on the name alone would fail. .first() is fine here as a presence
    // check given we already gated on the bio chip.
    await expect(doctorPage.getByText(/门诊\d+次/).first()).toBeVisible({ timeout: 10_000 });
    await expect(doctorPage.getByText(patient.name).first()).toBeVisible();

    await steps.capture(doctorPage, "患者详情页头部", "显示患者姓名和基本信息");

    // Tab bar — JumboTabs (.adm-jumbo-tabs) renders 总览 / 病历 / 聊天.
    // Counts may suffix tab titles (e.g. "病历 (1)") when there are pending
    // items. Scope to the tab container — the MyAI homepage behind the
    // overlay also renders patient cards labelled "病历" which would
    // otherwise collide.
    const tabBar = doctorPage.locator(".adm-jumbo-tabs");
    await expect(tabBar.getByText("总览", { exact: true })).toBeVisible();
    await expect(tabBar.getByText(/^病历(\s*\(\d+\))?$/)).toBeVisible();
    await expect(tabBar.getByText(/^聊天(\s*\(\d+\))?$/)).toBeVisible();

    // Switch to 病历 tab to see the record list.
    await tabBar.getByText(/^病历(\s*\(\d+\))?$/).click();

    // Record card shows status badge "待审核" (recordStatusBadge in source).
    // Use exact:true so we don't collide with the home page MyAI 最近使用
    // card which renders "test 头痛3天，待审核" as a substring.
    await expect(doctorPage.getByText("待审核", { exact: true }).first()).toBeVisible();

    await steps.capture(doctorPage, "病历记录列表", "显示预问诊记录和待审核状态");

    // Tap "查看完整详情" link inside the auto-expanded record panel → review page.
    await doctorPage.getByText("查看完整详情").first().click();
    await expect(doctorPage).toHaveURL(new RegExp(`/doctor/review/${recordId}`));

    await steps.capture(doctorPage, "跳转审核页面", "点击记录后进入诊断审核页");
  });

  test("2.4 — 空病历状态", async ({ doctorPage, patient, steps }) => {
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);
    // Empty state lives on the 病历 tab (default tab is 总览). Scope the
    // tab click to .adm-jumbo-tabs so we don't pick up the homepage
    // patient card's "病历" label rendered behind the subpage overlay.
    const tabBar = doctorPage.locator(".adm-jumbo-tabs");
    await tabBar.getByText(/^病历(\s*\(\d+\))?$/).click();
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
    // Banner copy: "${pendingReviewCount} 条问诊病历需要你审核".
    await expect(doctorPage.getByText(/需要你审核/)).toBeVisible();

    await steps.capture(doctorPage, "待处理横幅", "有待审核记录时显示处理提示");
  });

  test("4. 消息快捷入口跳转聊天视图", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    // Seed a patient message so the chat surface has content.
    await sendPatientMessage(request, patient, "医生，复查结果出来了。");
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // Wait for PatientDetail to render.
    await expect(doctorPage.getByText(/门诊\d+次/).first()).toBeVisible({ timeout: 10_000 });

    await steps.capture(doctorPage, "患者详情含消息", "已发送消息的患者详情页");

    // The 聊天 tab is the primary entry to the chat subpage (?view=chat).
    // Scope to .adm-jumbo-tabs to avoid colliding with the homepage card
    // labelled "聊天" rendered behind the overlay.
    const tabBar = doctorPage.locator(".adm-jumbo-tabs");
    await tabBar.getByText(/^聊天(\s*\(\d+\))?$/).click();
    await expect(doctorPage).toHaveURL(/view=chat/);

    await steps.capture(doctorPage, "进入聊天视图", "点击查看聊天记录后跳转");
  });

  test("5. 删除患者确认弹窗", async ({
    doctorPage,
    patient,
    request,
    steps,
  }) => {
    // Seed a record so the page is fully populated — the overflow trigger
    // is rendered as soon as the patient loads regardless, but the seed
    // matches the workflow we want to assert on.
    await completePatientIntake(request, patient);
    await doctorPage.goto(`/doctor/patients/${patient.patientId}`);

    // Wait for PatientDetail to render before hunting the overflow trigger.
    await expect(doctorPage.getByText(/门诊\d+次/).first()).toBeVisible({ timeout: 10_000 });

    // Overflow trigger has aria-label="更多操作". It's a clickable <div>, not
    // a <button>, so getByLabel is more reliable than getByRole("button").
    const moreButton = doctorPage.getByLabel("更多操作").first();
    await expect(moreButton).toBeVisible({ timeout: 10_000 });
    await moreButton.click();

    // Action sheet opened — danger action visible.
    const deleteRow = doctorPage.getByText("删除患者");
    await expect(deleteRow).toBeVisible();

    await steps.capture(doctorPage, "打开操作菜单", "显示删除患者选项");

    await deleteRow.click();

    // ConfirmDialog opens — copy: "所有病历和任务将一并删除".
    // ConfirmDialog renders the message twice (modal body + announcer); use
    // .first() to avoid strict-mode collision.
    await expect(doctorPage.getByText(/所有病历和任务将一并删除/).first()).toBeVisible();

    await steps.capture(doctorPage, "删除确认弹窗", "显示删除确认对话框");

    // Cancel via the grey 保留 button — ConfirmDialog renders the action
    // strip twice (the off-screen first copy + the visible modal body).
    // .last() targets the interactive one.
    const dialog = doctorPage.locator('[role="dialog"]');
    await dialog.getByText("保留", { exact: true }).last().click();

    // URL stayed on patient detail.
    await expect(doctorPage).toHaveURL(new RegExp(`patients/${patient.patientId}`));

    await steps.capture(doctorPage, "取消删除后保留", "取消后仍停留在患者详情页");
  });
});
