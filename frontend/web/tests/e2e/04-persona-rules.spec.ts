/**
 * Workflow 04 — Persona rules CRUD
 *
 * Mirrors docs/qa/workflows/04-persona-rules.md.
 *
 * NOTE: The PersonaSubpage has been redesigned as a free-text bio editor.
 * The old 5-field sections (回复风格, 常用结尾语, etc.) no longer exist.
 * Tests below verify the current "AI 风格" page with its summary_text editor.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { addPersonaRule } from "./fixtures/seed";

test.describe("工作流 04 — AI风格规则", () => {
  test("1. 页面外壳标题和空状态正确", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/persona");

    // NavBar title is "AI风格" (no space — antd-mobile NavBar renders it without)
    await expect(doctorPage.getByText("AI风格").first()).toBeVisible();
    // Empty state CTA
    await expect(doctorPage.getByText("选择一个沟通风格开始")).toBeVisible();
    // Two buttons: 直接写 and 引导生成
    await expect(doctorPage.getByText("直接写", { exact: true })).toBeVisible();

    await steps.capture(doctorPage, "AI风格空状态", "显示模板选择和直接写入口");
  });

  test("2. 编辑并保存AI风格描述", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/persona");

    // Tap "直接写" to enter edit mode
    await doctorPage.getByText("直接写", { exact: true }).click();

    await steps.capture(doctorPage, "进入编辑模式", "点击直接写后显示编辑器");

    // Save button should exist (AppButton renders as div)
    const saveButton = doctorPage.getByText("保存", { exact: true }).first();

    // Fill the editor
    await doctorPage.locator("textarea").first().fill("### 沟通风格\n口语化，像朋友聊天");
    await saveButton.click();

    // After save, content should be visible in read mode
    await expect(doctorPage.getByText("口语化，像朋友聊天")).toBeVisible();

    await steps.capture(doctorPage, "保存成功", "保存后显示风格内容");
  });

  test("3. 编辑已有风格（预设规则）", async ({ doctorPage, doctor, request, steps }) => {
    await addPersonaRule(request, doctor, "closing", "有问题随时联系我");
    await doctorPage.goto("/doctor/settings/persona");

    // The fallback from rules should show the closing text.
    // Scope the regex with the section label so it matches the persona page only.
    // The MyAI home page (rendered behind the subpage overlay) shows
    // `AI风格：有问题随时联系我` as a short summary card and would otherwise
    // collide with the persona body's `结尾方式：有问题随时联系我`.
    await expect(doctorPage.getByText(/结尾方式：有问题随时联系我/)).toBeVisible();

    await steps.capture(doctorPage, "已有风格内容", "显示已配置的结尾语");

    // Tap edit to enter edit mode
    await doctorPage.getByText("编辑", { exact: true }).click();

    const textArea = doctorPage.locator("textarea").first();
    await textArea.fill("### 结尾习惯\n有问题随时联系我，微信也可以");
    await doctorPage.getByText("保存", { exact: true }).first().click();

    await expect(doctorPage.getByText("有问题随时联系我，微信也可以")).toBeVisible();

    await steps.capture(doctorPage, "编辑保存成功", "更新后的结尾语可见");
  });

  test("4. 取消编辑丢弃修改", async ({ doctorPage, doctor, request, steps }) => {
    await addPersonaRule(request, doctor, "avoid", "不主动展开罕见风险");
    await doctorPage.goto("/doctor/settings/persona");

    // Scope to persona section label — the MyAI home behind the overlay shows
    // the same rule text under an `AI风格：…` summary card.
    await expect(doctorPage.getByText(/回避内容：不主动展开罕见风险/)).toBeVisible();

    await steps.capture(doctorPage, "编辑前状态", "显示原有风格内容");

    // Enter edit mode
    await doctorPage.getByText("编辑", { exact: true }).click();

    const textArea = doctorPage.locator("textarea").first();
    await textArea.fill("完全不同的内容");

    // Cancel
    await doctorPage.getByText("取消", { exact: true }).first().click();

    // Original content should still be visible
    await expect(doctorPage.getByText(/回避内容：不主动展开罕见风险/)).toBeVisible();
    await expect(doctorPage.getByText("完全不同的内容")).toBeHidden();

    await steps.capture(doctorPage, "取消编辑后恢复", "原有内容未被修改");
  });

  test("5. 多条预设规则正常显示", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    await addPersonaRule(request, doctor, "reply_style", "直接给结论");
    await addPersonaRule(request, doctor, "closing", "祝早日康复");
    await addPersonaRule(request, doctor, "structure", "先结论后解释");

    await doctorPage.goto("/doctor/settings/persona");

    // All rules should appear in the persona page fallback text.
    // Scope to the section label so the MyAI home preview (rendered behind
    // the overlay as `AI风格：直接给结论 · 祝早日康复 · 先结论后解释`)
    // doesn't collide with the persona body under strict-mode.
    await expect(doctorPage.getByText(/沟通风格：直接给结论/)).toBeVisible();
    await expect(doctorPage.getByText(/结尾方式：祝早日康复/)).toBeVisible();
    await expect(doctorPage.getByText(/回复结构：先结论后解释/)).toBeVisible();

    await steps.capture(doctorPage, "多条规则展示", "三条风格规则全部可见");
  });
});
