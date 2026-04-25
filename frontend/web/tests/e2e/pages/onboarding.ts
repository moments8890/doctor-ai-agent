/**
 * OnboardingPage — thin page module for /doctor/onboarding.
 *
 * Rules (mirrored from the pilot brief):
 *   - Page methods own selectors + page-local waits ONLY.
 *   - Assertions live in the spec, not here.
 *   - One method = one user action + one hard postcondition wait. No
 *     multi-step "completeOnboarding()" god methods.
 *   - No fail-soft helpers. If the selector is not present, the call throws.
 *   - Step recording (`steps.capture`) stays in the spec.
 */
import type { Locator, Page } from "@playwright/test";

export class OnboardingPage {
  constructor(private readonly page: Page) {}

  // ── Navigation ────────────────────────────────────────────────────────
  async goto(step: 1 | 2 | 3): Promise<void> {
    await this.page.goto(`/doctor/onboarding?step=${step}`);
    await this.stepHeading(step).waitFor();
  }

  // ── Locators the spec needs to assert on ──────────────────────────────
  /**
   * The wizard NavBar title for each step (v2 OnboardingWizard):
   *   1 → "添加一条规则"
   *   2 → "看AI怎么用它"
   *   3 → "确认并开始"
   * The old "步骤 N/3" text no longer exists; the antd-mobile Steps component
   * renders an icon-based progress bar without that literal string.
   */
  private static readonly STEP_TITLES: Record<number, string> = {
    1: "添加一条规则",
    2: "看AI怎么用它",
    3: "确认并开始",
  };

  stepHeading(n: number): Locator {
    return this.page.getByText(OnboardingPage.STEP_TITLES[n] || `步骤 ${n}`).first();
  }

  get ruleEchoCard(): Locator {
    return this.page.getByText("你刚添加的规则");
  }

  get mockPatientStrip(): Locator {
    return this.page.getByText("张秀兰 · 72岁");
  }

  get wizardTitle(): Locator {
    // Used as the "wizard not present" assertion on reload. `.first()` to
    // disambiguate against potential duplicates in the DOM.
    return this.page.getByText("添加一条规则").first();
  }

  // ── Page-local waits (NOT expect()) ───────────────────────────────────
  /**
   * Wait for the wizard to reach step N. Uses Playwright's built-in wait —
   * no polling loop, no expect(). The spec still runs its own expect() for
   * the visible assertion.
   */
  async expectOnStep(n: number): Promise<void> {
    await this.stepHeading(n).waitFor();
  }

  // ── Step 1 actions ────────────────────────────────────────────────────
  async clickManualInput(): Promise<void> {
    const row = this.page.getByText("手动输入");
    await row.click();
    // Postcondition: add-knowledge subpage is now the URL.
    await this.page.waitForURL(/settings\/knowledge\/add/);
  }

  // ── Step 2 actions ────────────────────────────────────────────────────
  async clickDiagnosis(label: string): Promise<void> {
    await this.page.getByText(label).click();
  }

  async confirmSendDraft(): Promise<void> {
    await this.page.getByText("确认发送 ›").click();
  }

  // ── Footer navigation ─────────────────────────────────────────────────
  async clickNext(): Promise<void> {
    const current = await this.currentStep();
    await this.page.getByText("下一步").click();
    // Postcondition: wizard moved to the next step.
    await this.stepHeading(current + 1).waitFor();
  }

  async clickSkip(): Promise<void> {
    await this.page.getByText("跳过引导").click();
    // Postcondition: confirm dialog is now on screen.
    await this.page.getByText("跳过引导？").waitFor();
  }

  async confirmSkipInDialog(): Promise<void> {
    await this.page
      .locator("[role=dialog]")
      .getByText("跳过", { exact: true })
      .click();
    // Postcondition: navigated away from onboarding to the doctor workbench.
    await this.page.waitForURL(/\/doctor/);
  }

  async clickFinish(): Promise<void> {
    await this.page.getByText("完成引导").click();
    // Postcondition: landed on the doctor workbench (not /onboarding).
    await this.page.waitForURL(/\/doctor(\/|$|\?)/);
  }

  // ── Helper ────────────────────────────────────────────────────────────
  /** Read the current step number from the "步骤 N/3" heading. Throws if absent. */
  private async currentStep(): Promise<number> {
    for (const n of [1, 2, 3]) {
      if (await this.stepHeading(n).isVisible()) return n;
    }
    throw new Error("OnboardingPage.currentStep: no 步骤 N/3 heading visible");
  }
}
