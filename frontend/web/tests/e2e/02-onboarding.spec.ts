/**
 * Workflow 02 — Doctor onboarding wizard
 *
 * Mirrors docs/qa/workflows/02-onboarding.md. This is the new-doctor
 * activation path; if a step here breaks, new doctors silently fail.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("工作流 02 — 引导向导", () => {
  test.beforeEach(async ({ doctorPage, doctor }) => {
    // Clear any stored wizard state from previous runs. Real keys come from
    // frontend/web/src/pages/doctor/onboardingWizardState.js.
    await doctorPage.evaluate((id) => {
      localStorage.removeItem(`onboarding_wizard_progress:${id}`);
      localStorage.removeItem(`onboarding_wizard_done:${id}`);
    }, doctor.doctorId);
  });

  test("1. 向导外壳渲染步骤一", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    // 1.1 — header + progress + footer. AppButton renders as <Box> not
    // <button>, so check text presence instead of role.
    await expect(doctorPage.getByText("添加一条规则").first()).toBeVisible();
    await expect(doctorPage.getByText("步骤 1/3")).toBeVisible();
    await expect(doctorPage.getByText("下一步")).toBeVisible();

    await steps.capture(doctorPage, "引导步骤一页面", "显示添加规则引导");

    // 1.2 — context card
    await expect(doctorPage.getByText(/添加一条你的诊疗规则/)).toBeVisible();

    // 1.3 — three source rows
    for (const label of ["文件上传", "网址导入", "手动输入"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }

    await steps.capture(doctorPage, "验证三种来源入口", "文件上传、网址导入、手动输入可见");
  });

  test("2. 步骤一 — 保存文本规则解锁下一步", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    // 2.1 — tap manual input → routes to add-knowledge subpage
    await doctorPage.getByText("手动输入").click();
    await expect(doctorPage).toHaveURL(/settings\/knowledge\/add/);

    await steps.capture(doctorPage, "进入手动输入页面", "跳转到知识添加页");

    // 2.2 — AddKnowledgeSubpage has a single content textarea (no separate
    // title field). Wizard pre-fills it with example text. Just click "添加".
    const textbox = doctorPage.getByRole("textbox");
    await expect(textbox).toBeVisible();
    await textbox.clear();
    await textbox.fill("高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血");
    await doctorPage.getByText("添加", { exact: true }).click();

    // 2.3 — wizard auto-advances to step 2 after saving
    await expect(doctorPage).toHaveURL(/\/doctor\/onboarding/);
    await expect(doctorPage.getByText("步骤 2/3")).toBeVisible();

    await steps.capture(doctorPage, "保存后进入步骤二", "自动跳转到步骤2/3");
  });

  test("3. 完整向导流程 — 步骤1→2→3→完成", async ({
    doctorPage,
    steps,
  }) => {
    // ── Step 1: add a knowledge rule ──────────────────────────────────
    await doctorPage.goto("/doctor/onboarding?step=1");
    await expect(doctorPage.getByText("步骤 1/3")).toBeVisible();
    await expect(doctorPage.getByText(/添加一条你的诊疗规则/)).toBeVisible();

    await steps.capture(doctorPage, "引导步骤一", "步骤1/3页面");

    // Tap "手动输入" → add-knowledge subpage
    await doctorPage.getByText("手动输入").click();
    await expect(doctorPage).toHaveURL(/settings\/knowledge\/add/);

    // Fill content and save
    const textbox = doctorPage.getByRole("textbox");
    await expect(textbox).toBeVisible();
    await textbox.clear();
    await textbox.fill("高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血");
    await doctorPage.getByText("添加", { exact: true }).click();

    // ── Step 2: confirm diagnosis + send reply ────────────────────────
    // Wizard auto-advances after saving knowledge
    await expect(doctorPage).toHaveURL(/\/doctor\/onboarding/);
    await expect(doctorPage.getByText("步骤 2/3")).toBeVisible();

    // Rule echo card shows the saved rule
    await expect(doctorPage.getByText("你刚添加的规则")).toBeVisible();

    // Mock patient strip
    await expect(doctorPage.getByText("张秀兰 · 72岁")).toBeVisible();

    await steps.capture(doctorPage, "引导步骤二", "显示模拟患者和规则回显");

    // Click diagnosis row to confirm it
    await doctorPage.getByText("高血压脑病/高血压急症").click();

    // Click "确认发送 ›" on the AI draft reply
    await doctorPage.getByText("确认发送 ›").click();

    // Both actions done → advance to step 3
    await doctorPage.getByText("下一步").click();

    // ── Step 3: complete ──────────────────────────────────────────────
    await expect(doctorPage.getByText("步骤 3/3")).toBeVisible();
    await expect(doctorPage.getByText("设置完成")).toBeVisible();
    await expect(doctorPage.getByText(/AI 已学会你的规则/)).toBeVisible();

    await steps.capture(doctorPage, "引导完成页面", "步骤3/3设置完成");

    // Click "完成引导" → land on /doctor workbench
    await doctorPage.getByText("完成引导").click();
    await expect(doctorPage).toHaveURL(/\/doctor(\/|$|\?)/);

    // Verify wizard doesn't come back on reload
    await doctorPage.reload();
    await expect(doctorPage.getByText("添加一条规则")).toBeHidden();

    await steps.capture(doctorPage, "完成引导后工作台", "刷新后不再显示引导");
  });

  test("5. 跳过引导确认弹窗", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    await steps.capture(doctorPage, "引导页面初始状态", "步骤1页面");

    // AppButton renders as <Box>, use getByText.
    await doctorPage.getByText("跳过引导").click();

    // Cancel LEFT grey / confirm RIGHT green per dialog convention.
    // ConfirmDialog also uses AppButton (Box), not real <button>.
    await expect(doctorPage.getByText("跳过引导？")).toBeVisible();

    await steps.capture(doctorPage, "跳过确认弹窗", "显示跳过引导确认对话框");

    // Dialog has "取消" and "跳过" — click the confirm "跳过" inside the dialog.
    await doctorPage.locator("[role=dialog]").getByText("跳过", { exact: true }).click();

    await expect(doctorPage).toHaveURL(/\/doctor/);
    // Reload — wizard should not re-appear
    await doctorPage.reload();
    await expect(doctorPage.getByText("添加一条规则")).toBeHidden();

    await steps.capture(doctorPage, "跳过后工作台", "跳过引导后正常进入工作台");
  });
});
