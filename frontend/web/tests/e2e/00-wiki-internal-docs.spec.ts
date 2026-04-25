/**
 * Smoke test for wiki.* internal docs.
 *
 * The wiki-internal.html template renders source .md files via marked.js.
 * This spec catches the failure modes that would silently break /wiki
 * for users:
 *   - slug → file mapping in wiki-internal.html points at a missing path
 *   - sync-internal-wiki-docs.sh failed to copy a source file
 *   - marked.js CDN not loading / parse error
 *   - HTML structure regressed (no <h1>, error block visible)
 *
 * The test runs against the dev server (:5173). The npm `predev` hook
 * syncs the internal-docs/ directory before vite serves them, so a
 * fresh checkout is enough.
 *
 * Why no auth: wiki.* is public. We hit it like any user would.
 */
import { test, expect, type Page } from "@playwright/test";

// One entry per slug exposed by wiki-internal.html DOCS map. If you add
// a new doc to the wiki sidebar, add it here too — the spec is the
// regression boundary.
const DOCS = [
  // 系统架构 / 产品
  { slug: "architecture",            expectInTitle: "架构" },
  { slug: "product-strategy",        expectInTitle: "策略" },
  { slug: "north-star",              expectInTitle: "" },     // tiny doc, no specific keyword guarantee
  { slug: "roadmap",                 expectInTitle: "" },
  // 部署运维
  { slug: "services",                expectInTitle: "服务" },
  { slug: "runbook-subdomain-split", expectInTitle: "子域名" },
  { slug: "tencent-resources",       expectInTitle: "资源" },
  { slug: "glitchtip",               expectInTitle: "GlitchTip" },
  { slug: "dbgate",                  expectInTitle: "DBGate" },
  { slug: "mysql-restore",           expectInTitle: "MySQL" },
  // 开发指南
  { slug: "repo-rules",              expectInTitle: "" },
  { slug: "dev-onboarding",          expectInTitle: "" },
  { slug: "ui-design",               expectInTitle: "" },
  { slug: "e2e-guide",               expectInTitle: "" },
  { slug: "changelog",               expectInTitle: "" },
];

async function visitDoc(page: Page, slug: string) {
  await page.goto(`/wiki/wiki-internal.html?doc=${slug}`);
  // Wait for marked.js to fetch + render — the placeholder "加载中..." goes away
  // when the script replaces innerHTML with rendered content.
  await expect(page.locator(".loading")).toHaveCount(0, { timeout: 10_000 });
}

test.describe("wiki internal docs render", () => {
  for (const doc of DOCS) {
    test(`renders ${doc.slug}`, async ({ page }) => {
      await visitDoc(page, doc.slug);

      // No "加载失败" error block — confirms the source .md was fetched + parsed.
      await expect(page.locator(".err")).toHaveCount(0);

      // The renderer always emits a top-level <h1> (every source .md starts
      // with one). If marked.js silently failed, there'd be no h1.
      const h1Count = await page.locator("#content h1").count();
      expect(h1Count, `${doc.slug}: expected at least one <h1> in rendered content`).toBeGreaterThan(0);

      // Title check — the doc has SOMETHING about its topic, not just the
      // wrapper chrome. We accept the slug appearing in any heading.
      // Skipped for short docs (north-star, roadmap, repo-rules, etc.) where
      // a specific keyword in headings isn't a stable contract.
      if (doc.expectInTitle) {
        const headingTexts = await page.locator("#content h1, #content h2, #content h3").allInnerTexts();
        const joined = headingTexts.join(" ").toLowerCase();
        expect(
          joined.includes(doc.expectInTitle.toLowerCase()),
          `${doc.slug}: expected "${doc.expectInTitle}" somewhere in headings, got: ${joined.slice(0, 200)}`,
        ).toBeTruthy();
      }

      // Page <title> updates from the JS — confirms the script ran past the
      // DOCS lookup. (If the slug were unknown we'd see the "未知文档 slug" error.)
      const docTitle = await page.title();
      expect(docTitle, `${doc.slug}: page title should reflect the doc, not the bare default`).toMatch(/内部文档/);
    });
  }

  test("unknown slug returns a friendly error, not a blank page", async ({ page }) => {
    await page.goto("/wiki/wiki-internal.html?doc=this-doc-does-not-exist");
    await expect(page.locator(".err")).toBeVisible();
    await expect(page.locator(".err")).toContainText("未知文档");
  });
});
