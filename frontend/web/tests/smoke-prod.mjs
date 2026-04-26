// Smoke capture against PRODUCTION (Tencent) — logs in as test/123456.
// Focus: citations + knowledge in conjunction.
// Run from frontend/web/ with:  node tests/smoke-prod.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve("tests/smoke-prod-shots");
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const BASE = "https://api.doctoragentai.cn";

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  console.log(`  📸  ${name}.png`);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  try {
    console.log("login …");
    await page.goto(`${BASE}/login`);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByPlaceholder(/请输入昵称/).fill("test");
    await page.getByPlaceholder(/请输入数字口令/).fill("123456");
    await page.getByRole("button", { name: "登录" }).click();
    await page.waitForURL(/\/doctor/, { timeout: 15000 });
    await page.waitForTimeout(2000);

    await shot(page, "01-myai");

    console.log("全部患者 → 王大华 (has citation draft)");
    // Single-tab IA: no TabBar; navigate via the 全部患者 quick-action tile
    // (or directly via URL — URL is faster and more reliable in smoke).
    await page.goto("/doctor/patients");
    await page.waitForTimeout(1200);
    await shot(page, "02-patients");

    // Click the first patient name that appears
    const wang = page.locator(".adm-list-item").filter({ hasText: "王大华" }).first();
    if (await wang.count()) {
      await wang.click();
      await page.waitForTimeout(1200);
      await shot(page, "03-patient-overview");

      // Jump to 聊天 tab
      await page.getByText(/^聊天/).click().catch(() => {});
      await page.waitForTimeout(1500);
      await shot(page, "04-chat-with-citations");

      // Tap the first 依据 row to show the citation popup
      const evidenceRow = page.locator("text=高血压急症处理").first();
      if (await evidenceRow.count()) {
        await evidenceRow.click({ trial: true }).catch(() => {});
        await evidenceRow.click().catch(() => {});
        await page.waitForTimeout(800);
        await shot(page, "05-citation-popup");
        await page.keyboard.press("Escape");
        await page.waitForTimeout(400);
      }
    }

    console.log("知识库 subpage");
    await page.goto(`${BASE}/doctor/settings/knowledge`);
    await page.waitForTimeout(1500);
    await shot(page, "06-knowledge-list");

    // Tap one of the demo KB entries → detail
    const kb = page.getByText(/高血压急症处理/).first();
    if (await kb.count()) {
      await kb.click();
      await page.waitForTimeout(1200);
      await shot(page, "07-knowledge-detail");
    }

    console.log("审核 tab");
    await page.goto(`${BASE}/doctor/review`);
    await page.waitForTimeout(1500);
    await shot(page, "08-review-queue");

    console.log("✅ prod smoke complete");
  } catch (e) {
    await shot(page, "99-failure");
    console.error(e.message);
    throw e;
  } finally {
    await browser.close();
  }
})();
