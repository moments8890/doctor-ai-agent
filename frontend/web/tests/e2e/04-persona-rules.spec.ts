/**
 * Workflow 04 — Persona rules CRUD
 *
 * Mirrors docs/qa/workflows/04-persona-rules.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { addPersonaRule } from "./fixtures/seed";

const FIELD_LABELS = ["回复风格", "常用结尾语", "回复结构", "回避内容", "常见修改"];

test.describe("Workflow 04 — Persona rules", () => {
  test("1. Page shell renders 5 field sections", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona");

    await expect(doctorPage.getByText("AI 人设")).toBeVisible();
    for (const label of FIELD_LABELS) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }
    // Empty hint for 回复风格
    await expect(doctorPage.getByText(/口语化回复/)).toBeVisible();
    // Stats section
    await expect(doctorPage.getByText("统计")).toBeVisible();
    await expect(doctorPage.getByText("规则总数")).toBeVisible();
    await expect(doctorPage.getByText("学习获得")).toBeVisible();
  });

  test("2. Add rule to 回复风格", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona");

    // Tap + on 回复风格 row — the first AddCircleOutlineIcon.
    const replyStyleHeader = doctorPage.getByText("回复风格", { exact: true }).locator("..");
    await replyStyleHeader.locator("button").click();

    // Dialog opens
    await expect(doctorPage.getByText("添加回复风格")).toBeVisible();
    const addButton = doctorPage.getByRole("button", { name: "添加" });
    await expect(addButton).toBeDisabled();

    // Fill and submit
    await doctorPage.getByPlaceholder(/口语化回复/).fill("口语化，像朋友聊天");
    await expect(addButton).toBeEnabled();
    await addButton.click();

    // Sheet closes, rule visible with 手动 badge
    await expect(doctorPage.getByText("添加回复风格")).toBeHidden();
    await expect(doctorPage.getByText("口语化，像朋友聊天")).toBeVisible();
    await expect(doctorPage.getByText("手动").first()).toBeVisible();
  });

  test("3. Edit an existing rule", async ({ doctorPage, doctor, request }) => {
    await addPersonaRule(request, doctor, "closing", "有问题随时联系我");
    await doctorPage.goto("/doctor/settings/persona");

    const rule = doctorPage.getByText("有问题随时联系我");
    await expect(rule).toBeVisible();

    // Click edit icon (EditOutlinedIcon) — the first icon-button in the row.
    const row = rule.locator("..").locator("..");
    await row.locator("button").first().click();

    await expect(doctorPage.getByText("编辑规则")).toBeVisible();
    const textArea = doctorPage.locator("textarea").first();
    await textArea.fill("有问题随时联系我，微信也可以");
    await doctorPage.getByRole("button", { name: "保存" }).click();

    await expect(doctorPage.getByText("有问题随时联系我，微信也可以")).toBeVisible();
  });

  test("4. Delete rule with confirm dialog", async ({ doctorPage, doctor, request }) => {
    await addPersonaRule(request, doctor, "avoid", "不主动展开罕见风险");
    await doctorPage.goto("/doctor/settings/persona");

    const rule = doctorPage.getByText("不主动展开罕见风险");
    const row = rule.locator("..").locator("..");

    // Trash icon is the second button in the row.
    await row.locator("button").nth(1).click();

    // ConfirmDialog — cancel LEFT "保留" / confirm RIGHT "删除"
    await expect(doctorPage.getByText("确认删除")).toBeVisible();
    await expect(doctorPage.getByRole("button", { name: "保留" })).toBeVisible();
    await doctorPage.getByRole("button", { name: "删除" }).click();

    await expect(doctorPage.getByText("不主动展开罕见风险")).toBeHidden();
  });

  test("5. Stats count seeded rules correctly", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    await addPersonaRule(request, doctor, "reply_style", "直接给结论");
    await addPersonaRule(request, doctor, "closing", "祝早日康复");
    await addPersonaRule(request, doctor, "structure", "先结论后解释");

    await doctorPage.goto("/doctor/settings/persona");
    // 规则总数 should read 3.
    const totalCard = doctorPage.getByText("规则总数").locator("..");
    await expect(totalCard).toContainText("3");
  });
});
