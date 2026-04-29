/**
 * Workflow 10 — Tasks browse + complete
 *
 * Mirrors docs/qa/workflows/10-tasks.md. Uses seed.createPatientTask to
 * populate the followups tab deterministically instead of going through
 * review finalization.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { createPatientTask } from "./fixtures/seed";

test.describe.configure({ mode: "serial" });

// The standalone /doctor/tasks page was retired with the v2 single-page IA
// shift — tasks now surface inline on the MyAI homepage's 今日关注 cards.
// All workflow-10 assertions assume the old standalone page; the whole
// describe block is skipped pending a rewrite for the new IA. The tests
// inside still run only when this guard flips off.
test.describe.skip("工作流 10 — 任务管理", () => {
  test("1. 列表外壳渲染两个标签默认待完成", async ({
    doctorPage,
    steps,
  }) => {
    await doctorPage.goto("/doctor/tasks");
    await expect(doctorPage.getByText("任务").first()).toBeVisible();
    await steps.capture(doctorPage, "打开任务页面", "任务列表已加载");
    // Only 2 visible tabs in the FilterBar — "待完成" and "已完成".
    await expect(doctorPage.getByText("待完成", { exact: true }).first()).toBeVisible();
    await expect(doctorPage.getByText("已完成", { exact: true }).first()).toBeVisible();
    // Old 4-tab model should not render.
    await expect(doctorPage.getByText("已安排", { exact: true })).toBeHidden();
    await expect(doctorPage.getByText("已发送", { exact: true })).toBeHidden();
    // NewItemCard visible.
    await expect(doctorPage.getByText("新建任务").first()).toBeVisible();
    await steps.capture(doctorPage, "验证标签和新建按钮");
  });

  test("2. URL标签参数往返正确", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/tasks");
    // Default tab is followups — no explicit query needed.
    await doctorPage.getByText("已完成", { exact: true }).first().click();
    // URL gets updated via history.replaceState — read it back.
    await expect
      .poll(() => new URL(doctorPage.url()).searchParams.get("tab"))
      .toBe("completed");
    await steps.capture(doctorPage, "切换到已完成标签");

    // Explicit ?tab=followups restores to default view.
    await doctorPage.goto("/doctor/tasks?tab=followups");
    await expect(doctorPage.getByText("待完成", { exact: true }).first()).toBeVisible();
    await steps.capture(doctorPage, "URL参数恢复默认标签");
  });

  test("2.3 / 3. 点击任务行跳转详情", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    const { taskId } = await createPatientTask(request, doctor, patient.patientId, {
      title: "E2E 完成任务测试",
      content: "按时完成本次复查",
    });
    expect(taskId).toBeTruthy();

    await doctorPage.goto("/doctor/tasks");
    // Title rendered in merged followups list as "<patient> · <task>" OR
    // as a plain title depending on source — match either form.
    const titleLocator = doctorPage.getByText(/E2E 完成任务测试/);
    await expect(titleLocator).toBeVisible();
    await steps.capture(doctorPage, "任务列表显示新任务");

    // The row body tap navigates to detail (2.3 gate). Verify first.
    await titleLocator.click();
    await expect(doctorPage).toHaveURL(new RegExp(`/doctor/tasks/${taskId}`));
    await steps.capture(doctorPage, "进入任务详情页");
  });

  // Preseed creates demo tasks on registration, so the task list
  // is never empty for a fresh doctor. Skip until preseed is configurable.
  test.skip("5.1 新医生待完成为空", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/tasks");
    // FilterBar still present, but no task rows.
    await expect(doctorPage.getByText("待完成", { exact: true }).first()).toBeVisible();
    // EmptyState component copy is flexible — look for either the shared
    // component's title OR the "暂无" fallback used by the older empty view.
    await expect(
      doctorPage.getByText(/暂无|没有待完成|开始添加/).first(),
    ).toBeVisible();
  });

  test("6. 患者提交来源横幅显示", async ({
    doctorPage,
    steps,
  }) => {
    await doctorPage.goto("/doctor/tasks?origin=patient_submit");
    await expect(doctorPage.getByText("已创建审核任务")).toBeVisible();
    await steps.capture(doctorPage, "患者提交来源横幅");
  });

  test("6. 审核完成来源横幅显示", async ({
    doctorPage,
    steps,
  }) => {
    await doctorPage.goto("/doctor/tasks?origin=review_finalize");
    await expect(doctorPage.getByText("已生成随访任务")).toBeVisible();
    await steps.capture(doctorPage, "审核完成来源横幅");
  });
});
