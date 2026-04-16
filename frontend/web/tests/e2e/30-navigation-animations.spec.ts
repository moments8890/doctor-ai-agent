/**
 * Navigation animation test — exercises key navigation paths
 * and records video for human review of transitions.
 *
 * Run:  cd frontend/web && npx playwright test 30-navigation-animations
 * View: look for video.webm in test-results/runs/latest/
 */
import { test as baseTest, expect } from "./fixtures/doctor-auth";

// Override slowMo to 0 — we want real animation speed, not artificial delays
const test = baseTest.extend({});
test.use({ launchOptions: { slowMo: 0 } });

// Wait long enough for the 2s debug animation + buffer
const SLIDE = 2800;
const INSTANT = 800;

test("navigation animations — all key transitions", async ({ doctorPage, patient, steps }) => {
  const page = doctorPage;

  // Dismiss release notes dialog if present
  const dismissBtn = page.getByText("知道了", { exact: true }).first();
  await dismissBtn.waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
  if (await dismissBtn.isVisible()) {
    await dismissBtn.click({ force: true });
    await page.waitForTimeout(1000);
  }

  // ── Tab switches (INSTANT) ──
  await steps.capture(page, "Start: 我的AI tab");

  await page.getByText("患者", { exact: true }).last().click();
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Tab → 患者 (instant)");

  await page.getByText("审核", { exact: true }).last().click();
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Tab → 审核 (instant)");

  await page.getByText("任务", { exact: true }).last().click();
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Tab → 任务 (instant)");

  await page.getByText("我的AI", { exact: true }).last().click();
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Tab → 我的AI (instant)");

  // ── Patient list → detail (SLIDE) ──
  await page.getByText("患者", { exact: true }).last().click();
  await page.waitForTimeout(INSTANT);

  const hasPatient = await page.getByText(patient.name).first().isVisible({ timeout: 3000 }).catch(() => false);
  if (hasPatient) {
    await page.getByText(patient.name).first().click();
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Patient detail (slide in)");

    // Detail → chat (SLIDE) — use URL nav to avoid overlay click interception
    await page.goto(`/doctor/patients/${patient.patientId}?view=chat`);
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Chat view (slide in)");

    // Chat → back
    await page.goBack();
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Back from chat (slide out)");

    // Back to list
    await page.goBack();
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Back to patient list (slide out)");
  }

  // ── Settings deep nav (SLIDE → SLIDE) ──
  await page.goto("/doctor/settings");
  await page.waitForTimeout(SLIDE);

  const kb = page.getByText("知识库").first();
  if (await kb.isVisible({ timeout: 3000 }).catch(() => false)) {
    await kb.click();
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Settings → Knowledge (slide)");

    await page.goBack();
    await page.waitForTimeout(SLIDE);
    await steps.capture(page, "Knowledge → back (slide out)");
  }

  // ── Deep links (INSTANT — no animation) ──
  await page.goto("/doctor/settings/knowledge");
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Deep link knowledge (instant)");

  await page.goto(`/doctor/patients/${patient.patientId}`);
  await page.waitForTimeout(INSTANT);
  await steps.capture(page, "Deep link patient (instant)");

  await steps.capture(page, "Done — review video");
});
