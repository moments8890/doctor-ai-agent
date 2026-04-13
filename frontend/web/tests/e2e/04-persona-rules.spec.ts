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

test.describe("Workflow 04 — Persona rules", () => {
  test("1. Page shell renders with correct title and empty state", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona");

    // PageSkeleton title is "AI 风格"
    await expect(doctorPage.getByText("AI 风格").first()).toBeVisible();
    // Empty state CTA
    await expect(doctorPage.getByText("还没有AI风格描述")).toBeVisible();
    // Two buttons: 直接写 and 引导生成
    await expect(doctorPage.getByText("直接写", { exact: true })).toBeVisible();
  });

  test("2. Edit and save persona summary", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona");

    // Tap "直接写" to enter edit mode
    await doctorPage.getByText("直接写", { exact: true }).click();

    // Save button should exist (AppButton renders as div)
    const saveButton = doctorPage.getByText("保存", { exact: true }).first();

    // Fill the editor
    await doctorPage.locator("textarea").first().fill("### 沟通风格\n口语化，像朋友聊天");
    await saveButton.click();

    // After save, content should be visible in read mode
    await expect(doctorPage.getByText("口语化，像朋友聊天")).toBeVisible();
  });

  test("3. Edit an existing persona via seeded rules", async ({ doctorPage, doctor, request }) => {
    await addPersonaRule(request, doctor, "closing", "有问题随时联系我");
    await doctorPage.goto("/doctor/settings/persona");

    // The fallback from rules should show the closing text
    await expect(doctorPage.getByText(/有问题随时联系我/)).toBeVisible();

    // Tap edit to enter edit mode
    await doctorPage.getByText("编辑", { exact: true }).click();

    const textArea = doctorPage.locator("textarea").first();
    await textArea.fill("### 结尾习惯\n有问题随时联系我，微信也可以");
    await doctorPage.getByText("保存", { exact: true }).first().click();

    await expect(doctorPage.getByText("有问题随时联系我，微信也可以")).toBeVisible();
  });

  test("4. Cancel editing discards changes", async ({ doctorPage, doctor, request }) => {
    await addPersonaRule(request, doctor, "avoid", "不主动展开罕见风险");
    await doctorPage.goto("/doctor/settings/persona");

    await expect(doctorPage.getByText(/不主动展开罕见风险/)).toBeVisible();

    // Enter edit mode
    await doctorPage.getByText("编辑", { exact: true }).click();

    const textArea = doctorPage.locator("textarea").first();
    await textArea.fill("完全不同的内容");

    // Cancel
    await doctorPage.getByText("取消", { exact: true }).first().click();

    // Original content should still be visible
    await expect(doctorPage.getByText(/不主动展开罕见风险/)).toBeVisible();
    await expect(doctorPage.getByText("完全不同的内容")).toBeHidden();
  });

  test("5. Multiple seeded rules show in fallback display", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    await addPersonaRule(request, doctor, "reply_style", "直接给结论");
    await addPersonaRule(request, doctor, "closing", "祝早日康复");
    await addPersonaRule(request, doctor, "structure", "先结论后解释");

    await doctorPage.goto("/doctor/settings/persona");

    // All rules should appear in the fallback text
    await expect(doctorPage.getByText(/直接给结论/)).toBeVisible();
    await expect(doctorPage.getByText(/祝早日康复/)).toBeVisible();
    await expect(doctorPage.getByText(/先结论后解释/)).toBeVisible();
  });
});
