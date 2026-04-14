/**
 * StepRecorder — capture named screenshots + metadata during E2E tests.
 *
 * Usage (via the `steps` fixture exported from doctor-auth.ts):
 *
 *   test("renders the page", async ({ doctorPage, steps }) => {
 *     await doctorPage.goto("/doctor/settings");
 *     await steps.capture(doctorPage, "进入设置页面", "导航到 /doctor/settings");
 *     // ...
 *   });
 *
 * After the test, `result.json` is written to `testInfo.outputDir` automatically
 * by the fixture teardown. Each screenshot lands in the same directory so video
 * + screenshots + result.json form a self-contained evidence bundle.
 */
import * as path from "node:path";
import type { Page, TestInfo } from "@playwright/test";

export interface Step {
  name: string;
  pass: boolean;
  detail?: string;
  screenshot: string;
}

export interface TestResult {
  suite: string;
  test: string;
  timestamp: string;
  passed: boolean;
  steps: Step[];
}

/**
 * Slugify a step name for use as a filename component.
 * Keeps Chinese characters, letters, and digits. Replaces spaces and special
 * chars with hyphens, collapses consecutive hyphens, and trims leading/trailing
 * hyphens.
 */
function slugify(text: string): string {
  return text
    .replace(/[\s/\\:*?"<>|]+/g, "-")   // whitespace + filesystem-unsafe → dash
    .replace(/[^\p{L}\p{N}\-]/gu, "-")  // anything that isn't letter/number/dash → dash
    .replace(/-{2,}/g, "-")             // collapse runs of dashes
    .replace(/^-|-$/g, "");             // trim leading/trailing dashes
}

export class StepRecorder {
  private counter = 0;
  private steps: Step[] = [];
  private testInfo: TestInfo;

  constructor(testInfo: TestInfo) {
    this.testInfo = testInfo;
  }

  /**
   * Capture a named step: takes a screenshot and records metadata.
   *
   * @param page     The Playwright page to screenshot
   * @param name     Human-readable step name (Chinese OK)
   * @param detail   Optional extra context for the result.json entry
   */
  async capture(page: Page, name: string, detail?: string): Promise<void> {
    this.counter++;
    const prefix = String(this.counter).padStart(2, "0");
    const slug = slugify(name);
    const filename = `${prefix}-${slug}.png`;
    const filepath = path.join(this.testInfo.outputDir, filename);

    await page.screenshot({ path: filepath });

    const step: Step = { name, pass: true, screenshot: filename };
    if (detail !== undefined) {
      step.detail = detail;
    }
    this.steps.push(step);
  }

  /** Return all steps recorded so far. */
  getSteps(): Step[] {
    return [...this.steps];
  }

  /**
   * Write `result.json` to testInfo.outputDir summarising the test run.
   * Called automatically by the fixture teardown — tests don't need to call
   * this directly.
   */
  async writeResult(suiteName: string, testName: string): Promise<void> {
    const result: TestResult = {
      suite: suiteName,
      test: testName,
      timestamp: new Date().toISOString(),
      passed: this.testInfo.status === "passed",
      steps: this.steps,
    };

    const fs = await import("node:fs/promises");
    await fs.mkdir(this.testInfo.outputDir, { recursive: true });
    const filepath = path.join(this.testInfo.outputDir, "result.json");
    await fs.writeFile(filepath, JSON.stringify(result, null, 2) + "\n", "utf-8");
  }
}
