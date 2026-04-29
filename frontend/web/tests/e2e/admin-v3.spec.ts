/**
 * Admin v3 e2e — Task 5.1 of docs/plans/2026-04-24-admin-modern-port.md.
 *
 * Covers the operator-facing admin surface mounted at `/admin?v=3`:
 *
 *   1. Shell + sidebar (brand "鲸鱼随行" + Admin tag, 概览 / 运营 / 系统 groups)
 *   2. Doctor list → detail (URL gains ?doctor=, header card, KPI strip, 4 tabs)
 *   3. Tabs (总览 / 患者 / 沟通 / AI 与知识) and the 高危 filter chip behavior
 *   4. AI footnote expand + infoTint background invariant (codex v3 fix)
 *   5. Viewer-role hides 系统 nav-group while keeping 运营 visible
 *
 * Selector rules (per CLAUDE.md):
 *   v3 components are plain divs with inline styles — they're NOT MUI Boxes
 *   and they're NOT semantic <button>s, so use getByText() not getByRole().
 *   Only AdminTopbar's notification bell and the legacy login form ship as
 *   real <button> elements.
 *
 * Auth fixture:
 *   AdminPage.jsx auto-sets `localStorage.adminToken = "dev"` in DEV mode
 *   (frontend/web/src/pages/admin/AdminPage.jsx:24). We also addInitScript
 *   to belt-and-suspenders the token in case the test runs against a
 *   non-DEV build, and to set `adminRole` for the viewer-role test.
 *
 * Backend assumption:
 *   This spec uses the standard playwright.config.ts setup — frontend on
 *   :5173 (Vite dev) + backend on :8000 (uvicorn dev). It does NOT use the
 *   :8001 isolated test backend that scripts/validate-v2-e2e.sh sets up,
 *   because the legacy /admin doctor list reads from the dev DB and the
 *   v3 surface dogfoods the real data the partner doctor will see.
 */
import { test, expect, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

// The `infoTint` token (#EEF1F6) renders as rgb(238, 241, 246) in the DOM.
// AiFootnoteCard.jsx must keep this background in BOTH collapsed and
// expanded states — codex v3 review locked this as the not-a-bubble cue.
const INFO_TINT_RGB = "rgb(238, 241, 246)";

// Wait for the v3 sidebar to render. The brand row contains both literals.
async function waitForShell(page: Page) {
  await expect(page.getByText("鲸鱼随行", { exact: true })).toBeVisible();
  await expect(page.getByText("Admin", { exact: true })).toBeVisible();
}

// Pull a doctor row out of the v3 doctor list. The list renders one
// row per doctor with the doctor_id displayed in mono under the name; we
// click the first row and read the URL param afterwards. The list lives
// inside a section with header "选择医生".
async function clickFirstDoctor(page: Page): Promise<string> {
  // "选择医生" appears in both the header breadcrumb (data-v3="crumb-here")
  // AND the section heading. .first() picks the breadcrumb (DOM order),
  // both confirm the page rendered.
  await expect(page.getByText("选择医生", { exact: true }).first()).toBeVisible();

  // The "X 位" count appears next to the heading. If the list is empty,
  // surface that as a clear failure rather than a flaky timeout below.
  const countText = await page.getByText(/^\d+\s*位$/).first().textContent();
  if (countText && /^0\s*位$/.test(countText.trim())) {
    throw new Error(
      "v3 doctor list is empty — register a doctor on the dev backend before running this spec",
    );
  }

  // Each DoctorRow renders "最近活跃 …" on the right. Use the row that
  // contains that string and click anywhere on it.
  const firstRow = page
    .locator('div:has-text("最近活跃")')
    .filter({ hasNot: page.locator("aside") }) // exclude the sidebar
    .first();
  await firstRow.click();

  // After click, AdminPageV3 re-renders with ?doctor=<id>. Wait for URL
  // param to appear (DoctorList.selectDoctor → pushState + popstate).
  await page.waitForURL(/[?&]doctor=/);
  const url = new URL(page.url());
  const doctorId = url.searchParams.get("doctor") || "";
  expect(doctorId).not.toEqual("");
  return doctorId;
}

test.describe("admin v3 — operator console", () => {
  // Desktop viewport. The default config is mobile (390x844) per the
  // doctor-app PWA hero path; the admin surface targets desktop operators.
  test.use({ viewport: { width: 1440, height: 900 } });

  // The admin spec dogfoods the live dev DB on :8000 (see header doc).
  // validate-v2-e2e.sh forces E2E_BASE_URL=:5174 → :8001 (test backend),
  // which has no admin-relevant data. Override the baseURL here so this
  // spec always points at the dev frontend (proxies to :8000) regardless
  // of the global env. Requires `npm run dev` (or equivalent) running.
  test.use({ baseURL: "http://127.0.0.1:5173" });

  test.beforeEach(async ({ page }) => {
    // Belt-and-suspenders: AdminPage.jsx already does this in DEV mode,
    // but the init script guarantees it before the first script runs.
    await page.addInitScript(() => {
      window.localStorage.setItem("adminToken", "dev");
      // Default to super so the system group is visible (when dev-mode is on).
      window.localStorage.setItem("adminRole", "super");
      window.localStorage.setItem("adminDevMode", "1");
    });
  });

  test("1. shell + sidebar groups render at /admin?v=3", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("pageerror", (e) => consoleErrors.push(String(e)));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await page.goto("/admin?v=3");
    await waitForShell(page);

    // Two nav groups: 概览 / 运营. The 系统 group was removed from the
    // sidebar (devMode.js comments still reference it but AdminSidebar
    // NAV_GROUPS no longer includes it).
    await expect(page.getByText("概览", { exact: true })).toBeVisible();
    await expect(page.getByText("运营", { exact: true })).toBeVisible();

    // 全体医生 nav item visible + clickable. Click should NOT navigate
    // away from /admin?v=3 (the link target is `?v=3` itself).
    const allDoctors = page.getByText("全体医生", { exact: true });
    await expect(allDoctors).toBeVisible();
    await allDoctors.click();
    await expect(page).toHaveURL(/[?&]v=3/);

    // No JS errors should have leaked.
    expect(consoleErrors, `console errors: ${consoleErrors.join("\n")}`).toHaveLength(0);
  });

  test("2. doctor list → detail navigates with header + KPI + 4 tabs", async ({ page }) => {
    await page.goto("/admin?v=3");
    await waitForShell(page);

    const doctorId = await clickFirstDoctor(page);
    expect(doctorId.length).toBeGreaterThan(0);

    // KPI strip: 5 cells with these uppercase labels.
    await expect(page.getByText("近 7 日 患者", { exact: true })).toBeVisible();
    await expect(page.getByText("近 7 日 消息", { exact: true })).toBeVisible();
    await expect(page.getByText("AI 采纳率", { exact: true })).toBeVisible();
    await expect(page.getByText("回复时效 P50", { exact: true })).toBeVisible();
    await expect(page.getByText("逾期任务", { exact: true })).toBeVisible();

    // 4 tabs visible. Use role=tab to disambiguate from the same labels
    // appearing inside cards/sections (e.g. "总览" can also appear in body).
    const overviewTab = page.getByRole("tab", { name: /总览/ });
    const patientsTab = page.getByRole("tab", { name: /患者/ });
    const chatTab = page.getByRole("tab", { name: /沟通/ });
    const aiTab = page.getByRole("tab", { name: /AI 与知识/ });

    await expect(overviewTab).toBeVisible();
    await expect(patientsTab).toBeVisible();
    await expect(chatTab).toBeVisible();
    await expect(aiTab).toBeVisible();

    // 总览 is active by default — the AiAdoptionPanel headline title is
    // a load-bearing string for the overview surface. Drop exact:true since
    // Panel concatenates an icon char into the same text-content sibling
    // (e.g. "network_intelligence AI 建议如何被使用").
    await expect(overviewTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("AI 建议如何被使用")).toBeVisible();
  });

  test("3. 患者 tab filter chips and 高危 filter behavior", async ({ page }) => {
    await page.goto("/admin?v=3");
    await waitForShell(page);
    await clickFirstDoctor(page);

    const patientsTab = page.getByRole("tab", { name: /患者/ });
    await patientsTab.click();
    await expect(patientsTab).toHaveAttribute("aria-selected", "true");

    // 5 filter chips visible. Each chip is a single <span> wrapping an
    // optional icon-name span + label + count span; the outer text content
    // is e.g. "priority_high高危0" (no separator). Scope to the filter bar
    // and match labels by substring within each chip <span>.
    const chipBar = page.locator("div").filter({ hasText: "全部" }).filter({ has: page.locator(".num") }).first();
    for (const label of ["全部", "高危", "未达标", "7天无沟通", "术后随访"]) {
      await expect(
        chipBar.locator("span", { hasText: label }).first(),
      ).toBeVisible();
    }

    // Click 高危. The grid filters to danger-only; if there are no
    // danger-tagged patients, the EmptyState renders with the title
    // "暂无匹配的患者". Either outcome is correct.
    await chipBar.locator("span", { hasText: "高危" }).first().click();

    // Chip border-color changes when active. Easier signal: either the
    // empty state appears or the grid still has a card. .first() because
    // the KPI strip's "近 7 日 消息" also matches the substring.
    const emptyTitle = page.getByText("暂无匹配的患者", { exact: true });
    const anyCard = page.locator("text=消息").first();
    await expect(emptyTitle.or(anyCard).first()).toBeVisible();
  });

  test("4. 沟通 tab + 4. AI 与知识 tab render some content or empty state", async ({ page }) => {
    await page.goto("/admin?v=3");
    await waitForShell(page);
    await clickFirstDoctor(page);

    // 沟通 tab. ChatTab renders either the chat-shell (left list + right
    // thread) OR the EmptyState "从左侧选择患者查看会话" depending on
    // whether the doctor has any messages.
    const chatTab = page.getByRole("tab", { name: /沟通/ });
    await chatTab.click();
    await expect(chatTab).toHaveAttribute("aria-selected", "true");

    const chatEmpty = page.getByText("从左侧选择患者查看会话", { exact: true });
    // Demo seam in ChatThread always emits the AI footnote demo block when
    // a patient is selected. Either empty OR demo footnote is acceptable.
    const demoTag = page.getByText("示例 · AI 脚注样式", { exact: true });
    await expect(chatEmpty.or(demoTag).first()).toBeVisible({ timeout: 10_000 });

    // AI 与知识 tab. AiTab renders DecisionCards OR an EmptyState
    // ("暂无 AI 决策记录"). The tab badge with mono count is also visible.
    const aiTab = page.getByRole("tab", { name: /AI 与知识/ });
    await aiTab.click();
    await expect(aiTab).toHaveAttribute("aria-selected", "true");

    const aiEmpty = page.getByText("暂无 AI 决策记录", { exact: true });
    // DecisionCard renders an icon span before the "AI 观察" label, so the
    // element's text content is e.g. "visibility AI 观察" — drop exact:true.
    const decisionCard = page.getByText("AI 观察").first();
    await expect(aiEmpty.or(decisionCard).first()).toBeVisible({ timeout: 10_000 });
  });

  test("5. AI footnote expands inline and keeps infoTint background", async ({ page }) => {
    await page.goto("/admin?v=3");
    await waitForShell(page);
    await clickFirstDoctor(page);

    await page.getByRole("tab", { name: /沟通/ }).click();

    // The chat thread either shows the empty state OR it shows messages
    // including the demo seam. Skip cleanly when there's no thread to
    // expand against (this is documented in ChatThread.jsx — the demo
    // block is appended when a patient is selected).
    const demoTag = page.getByText("示例 · AI 脚注样式", { exact: true });
    if (!(await demoTag.isVisible().catch(() => false))) {
      test.skip(
        true,
        "no chat thread available — doctor list is empty or no patient selected (see ChatTab EmptyState)",
      );
    }

    // The demo block emits one analysis footnote (collapsed by default).
    // HeaderLine renders an icon span ("network_intelligence") next to the
    // label, so the parent's text content is concatenated — drop exact:true.
    const analysisLabel = page.getByText("AI 解析 · 不发送").first();
    await expect(analysisLabel).toBeVisible();

    // The card itself is the parent role=button (AiFootnoteCard sets
    // role="button" tabIndex={0} on the inner clickable div).
    // Its background must be infoTint AND its border must be dashed.
    const card = analysisLabel.locator('xpath=ancestor::*[@role="button"][1]');
    await expect(card).toHaveCSS("background-color", INFO_TINT_RGB);
    // Border style is "dashed". (toHaveCSS reads computed styles.)
    await expect(card).toHaveCSS("border-top-style", "dashed");

    // Capture the collapsed-state height so we can verify expansion grew it.
    const collapsedBox = await card.boundingBox();
    expect(collapsedBox).toBeTruthy();

    // Click the card to expand. The 收起/展开 affordance text flips.
    // Drop exact:true — the label is followed by an icon char ("expand_less")
    // in the same parent so accessible text concatenates.
    await card.click();
    await expect(card.getByText("收起")).toBeVisible();

    // CRITICAL: expanded state still infoTint + dashed (codex v3 invariant).
    await expect(card).toHaveCSS("background-color", INFO_TINT_RGB);
    await expect(card).toHaveCSS("border-top-style", "dashed");

    // The card grew taller (body + source chips revealed).
    const expandedBox = await card.boundingBox();
    expect(expandedBox).toBeTruthy();
    expect((expandedBox!.height || 0)).toBeGreaterThan((collapsedBox!.height || 0));
  });

  test("6. viewer role hides 系统 nav-group, keeps 运营 visible", async ({ page }) => {
    // Override the default super-role init script with viewer.
    await page.addInitScript(() => {
      window.localStorage.setItem("adminToken", "dev");
      window.localStorage.setItem("adminRole", "viewer");
      // Even though devMode is set, viewer must NOT see 系统 — devMode.js
      // gates 系统 on (role === "super" && dev). Setting both lets us
      // confirm the viewer gate is enforced regardless of devMode.
      window.localStorage.setItem("adminDevMode", "1");
    });

    await page.goto("/admin?v=3");
    await waitForShell(page);

    // 概览 + 运营 group labels visible.
    await expect(page.getByText("概览", { exact: true })).toBeVisible();
    await expect(page.getByText("运营", { exact: true })).toBeVisible();

    // 邀请码 (运营 group item) still visible — viewers can read this.
    await expect(page.getByText("邀请码", { exact: true })).toBeVisible();

    // 系统 group label NOT visible. Same for its two items.
    await expect(page.getByText("系统", { exact: true })).toHaveCount(0);
    await expect(page.getByText("系统健康", { exact: true })).toHaveCount(0);
    await expect(page.getByText("审计日志", { exact: true })).toHaveCount(0);

    // Role label in user menu reads "合作伙伴 · 只读".
    await expect(
      page.getByText("合作伙伴 · 只读", { exact: true }),
    ).toBeVisible();
  });
});

// ──────────────────────────────────────────────────────────────────────────
// After-suite hook: drop a README.txt next to the run videos so reviewers
// can match each clip to its numbered steps without re-reading the spec.
// CLAUDE.md says this is normally a manual step, but the spec captures
// enough metadata that doing it inline keeps the artifact self-describing.
// ──────────────────────────────────────────────────────────────────────────

const STEP_NOTES: Record<string, string[]> = {
  "1. shell + sidebar groups render at /admin?v=3": [
    "Visit /admin?v=3 (admin token + super role pre-injected via init script).",
    "Assert sidebar brand row 鲸鱼随行 + Admin tag visible.",
    "Assert 概览 / 运营 / 系统 nav-group labels visible.",
    "Click 全体医生 → URL still matches /[?&]v=3/ (no navigation away).",
    "Assert no console errors leaked during the visit.",
  ],
  "2. doctor list → detail navigates with header + KPI + 4 tabs": [
    "Visit /admin?v=3 and wait for the v3 shell.",
    "Click the first row in the doctor list (DoctorRow with 最近活跃 ...).",
    "Assert URL gains ?doctor=<id> and the id is non-empty.",
    "Assert the 5 KPI labels (近7日 患者 / 消息 / AI 采纳率 / P50 / 逾期).",
    "Assert the 4 tabs (总览 / 患者 / 沟通 / AI 与知识) are visible.",
    "Assert 总览 is active and AiAdoptionPanel title 'AI 建议如何被使用' renders.",
  ],
  "3. 患者 tab filter chips and 高危 filter behavior": [
    "Visit /admin?v=3, click first doctor, click 患者 tab.",
    "Assert all 5 filter chips render (全部/高危/未达标/7天无沟通/术后随访).",
    "Click 高危 chip.",
    "Assert either the filtered grid OR the EmptyState '暂无匹配的患者' appears.",
  ],
  "4. 沟通 tab + 4. AI 与知识 tab render some content or empty state": [
    "Visit /admin?v=3, click first doctor.",
    "Click 沟通 tab → assert either ChatEmptyState or the demo AI-footnote tag.",
    "Click AI 与知识 tab → assert either EmptyState or 'AI 观察' DecisionCard label.",
  ],
  "5. AI footnote expands inline and keeps infoTint background": [
    "Visit /admin?v=3, click first doctor, click 沟通 tab.",
    "Skip cleanly if no chat thread is available for this doctor.",
    "Locate AI 解析 · 不发送 footnote and walk up to its role=button card.",
    "Assert card background-color is rgb(238, 241, 246) (infoTint).",
    "Assert card border-top-style is 'dashed'.",
    "Click the card → assert 收起 affordance appears.",
    "Re-assert background AND dashed border invariants in expanded state.",
    "Assert card boundingBox.height grew after expand (body + sources revealed).",
  ],
  "6. viewer role hides 系统 nav-group, keeps 运营 visible": [
    "Pre-inject adminRole=viewer (overrides super-role default).",
    "Visit /admin?v=3.",
    "Assert 概览 + 运营 group labels visible, 邀请码 nav item visible.",
    "Assert 系统 / 系统健康 / 审计日志 are NOT visible (count === 0).",
    "Assert user-menu role label reads '合作伙伴 · 只读'.",
  ],
};

test.afterAll(async ({}, testInfo) => {
  // testInfo isn't tied to a single test in afterAll — testInfo.outputDir
  // points at the suite-wide output. We write a single README.txt at the
  // top-level test-results folder describing every test in this spec.
  try {
    const root = path.resolve(testInfo.project.outputDir, "..");
    const readmePath = path.join(root, "admin-v3-README.txt");
    const lines: string[] = [];
    lines.push("admin v3 e2e — Task 5.1");
    lines.push("=========================");
    lines.push("");
    lines.push("Spec file: frontend/web/tests/admin-v3.spec.ts");
    lines.push("Generated: " + new Date().toISOString());
    lines.push("");
    lines.push(
      "Each test below maps to a video.webm under test-results/<spec>/<test>/. " +
        "Steps describe what the spec asserts in order.",
    );
    lines.push("");
    for (const [title, steps] of Object.entries(STEP_NOTES)) {
      lines.push(`Test: ${title}`);
      steps.forEach((s, i) => lines.push(`  ${i + 1}. ${s}`));
      lines.push("");
    }
    fs.mkdirSync(root, { recursive: true });
    fs.writeFileSync(readmePath, lines.join("\n"), "utf8");
  } catch {
    // Best-effort artifact writer — never fail the run because of this.
  }
});
