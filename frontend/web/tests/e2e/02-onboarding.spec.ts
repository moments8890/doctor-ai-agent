/**
 * Workflow 02 — Doctor onboarding wizard
 *
 * Mirrors docs/qa/workflows/02-onboarding.md. This is the new-doctor
 * activation path; if a step here breaks, new doctors silently fail.
 *
 * Pilot: UI actions go through the OnboardingPage + KnowledgeAddPage page
 * modules (see tests/e2e/pages/). Assertions, URL checks, and step capture
 * stay in the spec — the page modules only own selectors and page-local
 * waits.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { OnboardingPage } from "./pages/onboarding";
import { KnowledgeAddPage } from "./pages/knowledge-add";

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
    const onboarding = new OnboardingPage(doctorPage);
    await onboarding.goto(1);

    // 1.1 — header + progress + footer. AppButton renders as <Box> not
    // <button>, so check text presence instead of role.
    await expect(onboarding.wizardTitle).toBeVisible();
    await expect(onboarding.stepHeading(1)).toBeVisible();
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
    const onboarding = new OnboardingPage(doctorPage);
    const knowledge = new KnowledgeAddPage(doctorPage);

    await onboarding.goto(1);

    // 2.1 — tap manual input → routes to add-knowledge subpage
    await onboarding.clickManualInput();
    await expect(doctorPage).toHaveURL(/settings\/knowledge\/add/);

    await steps.capture(doctorPage, "进入手动输入页面", "跳转到知识添加页");

    // 2.2 — AddKnowledgeSubpage has a single content textarea (no separate
    // title field). Wizard pre-fills it with example text. Just click "添加".
    await knowledge.expectReady();
    await expect(knowledge.contentTextbox).toBeVisible();
    await knowledge.fillContent("高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血");
    await knowledge.submit();

    // 2.3 — wizard returns to step 1 with the source marked done; "下一步"
    // is now enabled. Clicking it advances to step 2.
    await expect(doctorPage).toHaveURL(/\/doctor\/onboarding/);
    await onboarding.expectOnStep(1);
    await onboarding.clickNext();
    await expect(onboarding.stepHeading(2)).toBeVisible();

    await steps.capture(doctorPage, "保存后进入步骤二", "下一步进入步骤2/3");
  });

  test("3. 完整向导流程 — 步骤1→2→3→完成", async ({
    doctorPage,
    steps,
  }) => {
    const onboarding = new OnboardingPage(doctorPage);
    const knowledge = new KnowledgeAddPage(doctorPage);

    // ── Step 1: add a knowledge rule ──────────────────────────────────
    await onboarding.goto(1);
    await expect(onboarding.stepHeading(1)).toBeVisible();
    await expect(doctorPage.getByText(/添加一条你的诊疗规则/)).toBeVisible();

    await steps.capture(doctorPage, "引导步骤一", "步骤1/3页面");

    // Tap "手动输入" → add-knowledge subpage
    await onboarding.clickManualInput();
    await expect(doctorPage).toHaveURL(/settings\/knowledge\/add/);

    // Fill content and save
    await knowledge.expectReady();
    await expect(knowledge.contentTextbox).toBeVisible();
    await knowledge.fillContent("高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血");
    await knowledge.submit();

    // ── Step 2: confirm diagnosis + send reply ────────────────────────
    // Save returns to step 1 with the source marked done. Click "下一步"
    // to advance to step 2.
    await expect(doctorPage).toHaveURL(/\/doctor\/onboarding/);
    await onboarding.expectOnStep(1);
    await onboarding.clickNext();
    await expect(onboarding.stepHeading(2)).toBeVisible();

    // Rule echo card shows the saved rule
    await expect(onboarding.ruleEchoCard).toBeVisible();

    // Mock patient strip
    await expect(onboarding.mockPatientStrip).toBeVisible();

    await steps.capture(doctorPage, "引导步骤二", "显示模拟患者和规则回显");

    // Click diagnosis row to confirm it
    await onboarding.clickDiagnosis("高血压脑病/高血压急症");

    // Click "确认发送 ›" on the AI draft reply
    await onboarding.confirmSendDraft();

    // Both actions done → advance to step 3
    await onboarding.clickNext();

    // ── Step 3: complete ──────────────────────────────────────────────
    await expect(onboarding.stepHeading(3)).toBeVisible();
    await expect(doctorPage.getByText("设置完成")).toBeVisible();
    await expect(doctorPage.getByText(/AI 已学会你的规则/)).toBeVisible();

    await steps.capture(doctorPage, "引导完成页面", "步骤3/3设置完成");

    // Click "完成引导" → land on /doctor workbench
    await onboarding.clickFinish();
    await expect(doctorPage).toHaveURL(/\/doctor(\/|$|\?)/);

    // Verify wizard doesn't come back on reload
    await doctorPage.reload();
    await expect(doctorPage.getByText("添加一条规则")).toBeHidden();

    await steps.capture(doctorPage, "完成引导后工作台", "刷新后不再显示引导");
  });

  test("5. 跳过引导确认弹窗", async ({ doctorPage, steps }) => {
    const onboarding = new OnboardingPage(doctorPage);
    await onboarding.goto(1);

    await steps.capture(doctorPage, "引导页面初始状态", "步骤1页面");

    // AppButton renders as <Box>, use getByText.
    await onboarding.clickSkip();

    // Cancel LEFT grey / confirm RIGHT green per dialog convention.
    // ConfirmDialog also uses AppButton (Box), not real <button>.
    await expect(doctorPage.getByText("跳过引导？")).toBeVisible();

    await steps.capture(doctorPage, "跳过确认弹窗", "显示跳过引导确认对话框");

    // Dialog has "取消" and "跳过" — click the confirm "跳过" inside the dialog.
    await onboarding.confirmSkipInDialog();

    await expect(doctorPage).toHaveURL(/\/doctor/);
    // Reload — wizard should not re-appear
    await doctorPage.reload();
    await expect(doctorPage.getByText("添加一条规则")).toBeHidden();

    await steps.capture(doctorPage, "跳过后工作台", "跳过引导后正常进入工作台");
  });
});
