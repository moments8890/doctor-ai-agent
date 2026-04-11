/**
 * Workflow 11 — Settings (font / about / logout)
 *
 * Mirrors docs/qa/workflows/11-settings.md.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("Workflow 11 — Settings", () => {
  test("1. Shell renders account + tools + general sections", async ({
    doctorPage,
  }) => {
    await doctorPage.goto("/doctor/settings");

    for (const label of ["账户", "工具", "通用", "账户操作"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
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
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }
  });

  test("2. Font scale picker changes level + persists", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings");

    // 2.1 — default sublabel is 标准
    const fontRow = doctorPage.getByText("字体大小").locator("..");
    await expect(fontRow).toContainText("标准");

    // 2.2 — open picker
    await doctorPage.getByText("字体大小").click();
    await expect(doctorPage.getByRole("dialog").getByText("字体大小")).toBeVisible();
    for (const label of ["标准", "大字", "超大"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }

    // 2.4 — tap 大字
    await doctorPage.getByText("大字", { exact: true }).click();
    await expect(doctorPage.getByRole("dialog")).toBeHidden();
    await expect(fontRow).toContainText("大字");

    // 2.6 — localStorage updated
    const persisted = await doctorPage.evaluate(() =>
      localStorage.getItem("doctor-font-scale"),
    );
    expect(persisted).toContain('"fontScale":"large"');

    // 2.7 — revert
    await doctorPage.getByText("字体大小").click();
    await doctorPage.getByText("标准", { exact: true }).click();
    await expect(fontRow).toContainText("标准");
  });

  test("3. Tool row navigation", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings");

    await doctorPage.getByText("知识库", { exact: true }).click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge/);
  });

  test("5. About navigation", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings");
    await doctorPage.getByText("关于", { exact: true }).click();
    await expect(doctorPage.getByText(/版本/)).toBeVisible();
  });

  // Logout test is covered in 01-auth.spec.ts §3.
});
