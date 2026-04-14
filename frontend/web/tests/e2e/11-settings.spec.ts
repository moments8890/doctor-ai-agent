/**
 * Workflow 11 — Settings (font / about / logout)
 *
 * Mirrors docs/qa/workflows/11-settings.md.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("工作流 11 — 设置", () => {
  test("1. 外壳渲染账户、工具、通用区域", async ({
    doctorPage,
    steps,
  }) => {
    await doctorPage.goto("/doctor/settings");
    await steps.capture(doctorPage, "打开设置页面");

    for (const label of ["账户", "工具", "通用", "账户操作"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }

    for (const label of [
      "报告模板",
      "知识库",
      "我的二维码",
      "字体大小",
      "关于",
      "隐私政策",
      "退出登录",
    ]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await steps.capture(doctorPage, "验证所有设置项可见");
  });

  test("2. 字体大小选择器切换并持久化", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");

    // 2.1 — default sublabel is 标准
    const fontRow = doctorPage.getByText("字体大小").first().locator("..");
    await expect(fontRow).toContainText("标准");

    // 2.2 — open picker
    await doctorPage.getByText("字体大小").first().click();
    await expect(doctorPage.getByRole("dialog").getByText("字体大小")).toBeVisible();
    for (const label of ["标准", "大字", "超大"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await steps.capture(doctorPage, "打开字体选择器");

    // 2.4 — tap 大字
    await doctorPage.getByRole("dialog").getByText("大字", { exact: true }).click();
    await expect(doctorPage.getByRole("dialog")).toBeHidden();
    await expect(fontRow).toContainText("大字");
    await steps.capture(doctorPage, "选择大字字体");

    // 2.6 — localStorage updated
    const persisted = await doctorPage.evaluate(() =>
      localStorage.getItem("doctor-font-scale"),
    );
    expect(persisted).toContain('"fontScale":"large"');

    // 2.7 — revert
    await doctorPage.getByText("字体大小").first().click();
    await doctorPage.getByRole("dialog").getByText("标准", { exact: true }).click();
    await expect(fontRow).toContainText("标准");
    await steps.capture(doctorPage, "恢复标准字体");
  });

  test("3. 工具行导航跳转", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");

    await doctorPage.getByText("知识库", { exact: true }).first().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge/);
    await steps.capture(doctorPage, "导航到知识库子页面");
  });

  test("5. 关于页面导航", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");
    await doctorPage.getByText("关于", { exact: true }).first().click();
    // "版本信息" sublabel in settings list is hidden on about page.
    // "版本 1.0.0" is visible. Use last() to pick the about page text.
    await expect(doctorPage.getByText(/版本/).last()).toBeVisible();
    await steps.capture(doctorPage, "打开关于页面");
  });

  // Logout test is covered in 01-auth.spec.ts §3.
});
