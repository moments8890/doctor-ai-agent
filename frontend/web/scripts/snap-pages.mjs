// One-off screenshot pass for UI review.
// Logs in as the seeded `test` doctor and captures each main route.
// Output: frontend/web/docs/ux/screenshots/snap-<timestamp>/
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";

const BASE = "http://localhost:5173";
const VIEWPORT = { width: 390, height: 844 };
const OUT_BASE = "/Volumes/ORICO/Code/doctor-ai-agent/docs/ux/screenshots";
const STAMP = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
const OUT = join(OUT_BASE, `snap-${STAMP}`);

const ROUTES = [
  { path: "/doctor/my-ai",                    name: "01-my-ai" },
  { path: "/doctor/patients",                 name: "02-patients" },
  { path: "/doctor/review",                   name: "03-review" },
  { path: "/doctor/tasks",                    name: "04-tasks" },
  { path: "/doctor/settings",                 name: "05-settings" },
  { path: "/doctor/settings/persona",         name: "06-settings-persona" },
  { path: "/doctor/settings/knowledge",       name: "07-settings-knowledge" },
];

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    hasTouch: true,
    isMobile: true,
    reducedMotion: "reduce",
  });
  const page = await ctx.newPage();

  // Login
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState("networkidle");
  await page.getByPlaceholder("请输入昵称").fill("test");
  await page.getByPlaceholder("请输入数字口令").fill("123456");
  await page.getByText("登录", { exact: true }).click();
  await page.waitForURL(/\/doctor/, { timeout: 15000 });
  await page.waitForTimeout(800);

  console.log("Logged in. Capturing routes…");

  for (const r of ROUTES) {
    await page.goto(`${BASE}${r.path}`);
    await page.waitForLoadState("networkidle");
    // Let React Query settle + list animations finish
    await page.waitForTimeout(1200);
    const outPath = join(OUT, `${r.name}.png`);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`  ${r.name}.png`);
  }

  // Bonus: the first patient's detail page, if any patient exists
  try {
    await page.goto(`${BASE}/doctor/patients`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    const firstPatient = page.locator(".adm-list-item").first();
    if (await firstPatient.count()) {
      await firstPatient.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: join(OUT, "08-patient-detail.png") });
      console.log("  08-patient-detail.png");

      // Open overflow menu
      const overflow = page.locator('[aria-label="更多操作"]');
      if (await overflow.count()) {
        await overflow.click();
        await page.waitForTimeout(600);
        await page.screenshot({ path: join(OUT, "08b-overflow-menu.png") });
        console.log("  08b-overflow-menu.png");

        // Tap the QR item
        const qrItem = page.getByText("患者二维码", { exact: true });
        if (await qrItem.count()) {
          await qrItem.click();
          // Wait for QR to load
          await page.waitForTimeout(2500);
          await page.screenshot({ path: join(OUT, "08c-qr-sheet.png") });
          console.log("  08c-qr-sheet.png");
        }
      }
    }
  } catch (e) {
    console.log("  (skipped patient detail —", e.message, ")");
  }

  await browser.close();
  console.log(`\nDone → ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
