/**
 * Workflow 11 — Settings (font / about / logout)
 *
 * Mirrors docs/qa/workflows/11-settings.md.
 */
import { test, expect } from "./fixtures/doctor-auth";

// SettingsPage v2 IA (current source: SettingsPage.jsx):
//   Profile card (name + role)
//   • AI 助手 section: AI 人设 / 知识库 / 回复模板
//   • 通用设置 section: 大字模式 (toggle, no longer a picker) / 关于
//   • 退出登录 button (full-width danger outline)
//
// What changed from the legacy spec:
//   - Section names: 账户/工具/通用/账户操作 → AI 助手 / 通用设置
//   - 报告模板 → 回复模板
//   - 我的二维码 — moved out of settings
//   - 字体大小 picker → 大字模式 toggle (Switch, two states only)
//   - 隐私政策 — folded into 关于 subtitle, not its own row
test.describe("工作流 11 — 设置", () => {
  test("1. 外壳渲染 AI 助手 / 通用设置 / 退出登录", async ({
    doctorPage,
    steps,
  }) => {
    await doctorPage.goto("/doctor/settings");
    await steps.capture(doctorPage, "打开设置页面");

    // Section headers — scope to .first() to dodge the homepage card behind
    // the subpage overlay, which also surfaces some of these labels.
    for (const label of ["AI 助手", "通用设置"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }

    for (const label of [
      "AI 人设",
      "知识库",
      "回复模板",
      "大字模式",
      "关于",
      "退出登录",
    ]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await steps.capture(doctorPage, "验证所有设置项可见");
  });

  test("2. 大字模式开关切换并持久化", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");

    // The font row carries an antd-mobile <Switch>. Tap via the role so we
    // don't accidentally hit the row body. The reset endpoint doesn't wipe
    // browser localStorage, so the toggle's initial state can be either
    // direction across runs — flip it to OFF first to start from a known
    // baseline.
    const fontSwitch = doctorPage.getByRole("switch").first();
    await expect(fontSwitch).toBeVisible();
    if (await fontSwitch.getAttribute("aria-checked") === "true") {
      await fontSwitch.click();
      await expect(fontSwitch).not.toBeChecked();
    }

    // 2.1 — toggle on → fontScale="large"
    await fontSwitch.click();
    await expect(fontSwitch).toBeChecked();
    await steps.capture(doctorPage, "开启大字模式");

    const persistedOn = await doctorPage.evaluate(() =>
      localStorage.getItem("doctor-font-scale"),
    );
    expect(persistedOn).toContain('"fontScale":"large"');

    // 2.2 — toggle off → fontScale="standard"
    await fontSwitch.click();
    await expect(fontSwitch).not.toBeChecked();
    await steps.capture(doctorPage, "关闭大字模式");

    const persistedOff = await doctorPage.evaluate(() =>
      localStorage.getItem("doctor-font-scale"),
    );
    expect(persistedOff).toContain('"fontScale":"standard"');
  });

  test("3. 知识库行导航跳转", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");

    // The MyAI homepage behind the subpage overlay also renders a "知识库"
    // tile. Settings page renders 知识库 later in DOM, so .last() picks the
    // visible settings row.
    await doctorPage.getByText("知识库", { exact: true }).last().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge/);
    await steps.capture(doctorPage, "导航到知识库子页面");
  });

  test("5. 关于页面导航", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");
    await doctorPage.getByText("关于", { exact: true }).first().click();
    // The about page renders a "版本" string somewhere; .last() avoids the
    // settings list row's own "关于 — 版本信息..." subtitle.
    await expect(doctorPage.getByText(/版本/).last()).toBeVisible();
    await steps.capture(doctorPage, "打开关于页面");
  });

  // Logout test is covered in 01-auth.spec.ts §3.
});
