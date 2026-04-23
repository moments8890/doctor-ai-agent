// Smoke test for the v2 redesign. Logs in as the existing `test`/`123456`
// doctor, navigates through all redesigned pages + subpages, takes screenshots.
// Run from frontend/web/ with:  node tests/smoke-redesign.mjs
//
// Output: tests/smoke-redesign-shots/*.png
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve("tests/smoke-redesign-shots");
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const FRONTEND = "http://localhost:5173";
const CREDS = { phone: "test", yob: "123456" };

async function shot(page, name) {
  const p = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  console.log(`  📸  ${name}.png`);
}

async function goto(page, url, name, wait = 900) {
  await page.goto(`${FRONTEND}${url}`);
  await page.waitForTimeout(wait);
  await shot(page, name);
}

async function run() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
  });

  try {
    console.log("── Auth ──");
    await page.goto(`${FRONTEND}/login`);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByPlaceholder(/请输入昵称/).fill(CREDS.phone);
    await page.getByPlaceholder(/请输入数字口令/).fill(CREDS.yob);
    await page.getByRole("button", { name: "登录" }).click();
    await page.waitForURL(/\/doctor/, { timeout: 10000 });
    await page.waitForTimeout(1500);

    console.log("── Main tabs ──");
    await shot(page, "01-my-ai-tab");

    // AI summary popup — click the banner div directly
    console.log("AI summary popup");
    const heroBanner = page.locator("text=您的专属医疗AI助手").locator("xpath=ancestor::div[contains(@style,'linear-gradient')][1]").first();
    await heroBanner.click({ force: true }).catch(() => {});
    await page.waitForTimeout(500);
    await shot(page, "02-summary-popup");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    // Close any mask that's still open
    await page.locator(".adm-mask").first().click({ force: true }).catch(() => {});
    await page.waitForTimeout(400);

    await goto(page, "/doctor/patients", "03-patients-tab", 1200);

    console.log("Patient detail (first patient in list)");
    const firstPatient = page.locator(".adm-list-item").first();
    if (await firstPatient.count()) {
      await firstPatient.click();
      await page.waitForTimeout(1200);
      await shot(page, "04-patient-detail-overview");
      await page.getByText("病历", { exact: true }).click().catch(() => {});
      await page.waitForTimeout(800);
      await shot(page, "05-patient-detail-records");
      await page.getByText(/^聊天/).click().catch(() => {});
      await page.waitForTimeout(800);
      await shot(page, "05b-patient-detail-chat");
    }

    await goto(page, "/doctor/review", "06-review-tab", 1200);
    await goto(page, "/doctor/review?tab=completed", "06b-review-completed", 1000);

    console.log("── Settings (top-level + subpages) ──");
    await goto(page, "/doctor/settings", "07-settings");

    // Tier A + B subpages
    await goto(page, "/doctor/settings/persona", "08-persona");
    await goto(page, "/doctor/settings/knowledge", "09-knowledge", 1200);
    await goto(page, "/doctor/settings/template", "10-template");
    await goto(page, "/doctor/settings/about", "11-about", 700);

    // Niche subpages — every route wired in DoctorPage.jsx
    console.log("── Niche subpages ──");
    await goto(page, "/doctor/settings/knowledge/add", "12-knowledge-add", 1000);
    await goto(page, "/doctor/settings/knowledge/102", "13-knowledge-detail", 1200);
    await goto(page, "/doctor/settings/persona/teach", "14-teach-by-example", 800);
    await goto(page, "/doctor/settings/persona/onboarding", "15-persona-onboarding", 1000);
    await goto(page, "/doctor/settings/persona/pending", "16-pending-review", 800);
    await goto(page, "/doctor/settings/review", "17-review-subpage", 800);
    await goto(page, "/doctor/settings/preferences", "18-preferences", 800);
    await goto(page, "/doctor/settings/qr", "19-qr", 800);

    console.log("\n✅ Smoke complete");
    if (errors.length > 0) {
      console.log(`\n⚠️  ${errors.length} console/page errors (showing first 12):`);
      errors.slice(0, 12).forEach((e) => console.log(`  ${e}`));
    } else {
      console.log("✅ No page errors captured");
    }
  } catch (err) {
    console.error(`\n❌  Failed: ${err.message}`);
    await shot(page, "99-failure");
    throw err;
  } finally {
    await browser.close();
  }
}

run();
