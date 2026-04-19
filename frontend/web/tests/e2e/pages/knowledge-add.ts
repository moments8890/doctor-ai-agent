/**
 * KnowledgeAddPage — thin page module for /doctor/settings/knowledge/add.
 *
 * Rules (mirrored from the pilot brief):
 *   - Page methods own selectors + page-local waits ONLY.
 *   - Assertions live in the spec, not here.
 *   - No fail-soft helpers; missing selectors throw.
 *   - Used by the onboarding wizard (step 1 → manual input) and also
 *     standalone from settings. This module only covers the wizard path.
 */
import type { Locator, Page } from "@playwright/test";

export class KnowledgeAddPage {
  constructor(private readonly page: Page) {}

  // ── Locators ──────────────────────────────────────────────────────────
  /**
   * Single content textarea. AddKnowledgeSubpage has no separate title
   * field — the backend extracts the title from the first line of content.
   */
  get contentTextbox(): Locator {
    return this.page.getByRole("textbox");
  }

  // ── Waits ─────────────────────────────────────────────────────────────
  /** Page-local wait: content textbox is rendered and interactive. */
  async expectReady(): Promise<void> {
    await this.contentTextbox.waitFor();
  }

  // ── Actions ───────────────────────────────────────────────────────────
  /** Replace the textarea contents. Fails if the textbox is absent. */
  async fillContent(text: string): Promise<void> {
    await this.contentTextbox.clear();
    await this.contentTextbox.fill(text);
  }

  /**
   * Click "添加" to save the knowledge item. The wizard auto-advances to
   * step 2 on success; the spec should assert that separately.
   */
  async submit(): Promise<void> {
    await this.page.getByText("添加", { exact: true }).click();
  }
}
