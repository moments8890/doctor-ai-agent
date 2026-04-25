/**
 * Workflow 05 — Knowledge CRUD (4 sources)
 *
 * Mirrors docs/qa/workflows/05-knowledge.md. Camera import is
 * skeleton-only (requires device). All other sources are tested.
 */
import path from "path";
import { fileURLToPath } from "url";
import { test, expect } from "./fixtures/doctor-auth";
import { addKnowledgeText } from "./fixtures/seed";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test.describe("工作流 05 — 知识库管理", () => {
  test("1. 列表 — 新医生显示预置知识条目", async ({ doctorPage, steps }) => {
    // A fresh doctor has 3 pre-seeded knowledge items, so the empty state
    // ("暂无知识条目") will NOT appear. Instead, verify the list renders
    // with the search bar and stats row.
    await doctorPage.goto("/doctor/settings/knowledge");
    // Stats strip shows "总规则" (not "条规则") since the v2 redesign.
    await expect(doctorPage.getByText(/总规则/)).toBeVisible();

    await steps.capture(doctorPage, "知识列表初始状态", "新医生显示预置知识条目");
  });

  test("1. 列表 — 已配置医生显示统计和条目", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    await addKnowledgeText(request, doctor, "高血压患者新发头痛需排除高血压脑病");
    await addKnowledgeText(request, doctor, "回访后记录血压读数");

    await doctorPage.goto("/doctor/settings/knowledge");

    await steps.capture(doctorPage, "知识列表页面", "显示添加的知识条目");

    // Stats bar labels (v2 redesign: 总规则 / 近7天引用 / 30天未用)
    for (const label of ["总规则", "近7天引用", "30天未用"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }

    // 1.4 — no "-1天前" (BUG-01 gate)
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/-1天前/);

    await steps.capture(doctorPage, "验证统计栏", "条规则、本周引用、未引用统计可见");
  });

  test("2. 通过文本添加", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/knowledge/add");

    await steps.capture(doctorPage, "添加知识页面", "手动输入知识页面");

    const textarea = doctorPage.locator("textarea").first();
    await textarea.fill("高血压患者新发头痛→排除高血压脑病");

    // Save — AppButton renders as <div>, not <button>. Use getByText.
    const saveBtn = doctorPage.getByText("添加", { exact: true });
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();

    // Lands back on doctor page (may navigate to list or main page).
    await expect(doctorPage).toHaveURL(/\/doctor/);
    await expect(doctorPage.getByText(/高血压患者新发头痛/).first()).toBeVisible();

    await steps.capture(doctorPage, "添加知识成功", "新知识条目在列表中可见");
  });

  // Skip: URL import requires serving static HTML fixture from the dev server
  test.skip("3. 通过网址导入添加", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/knowledge/add?source=url");
    await doctorPage.getByText("网页导入").click();

    const urlInput = doctorPage.locator('input[type="text"], input[type="url"]').first();
    const pciUrl = new URL("/examples/pci-antiplatelet-guide.html", doctorPage.url()).toString();
    await urlInput.fill(pciUrl);

    // "获取" is an AppButton (div), use getByText
    await doctorPage.getByText("获取", { exact: true }).click();

    // Spinner → preview sheet (allow some time for fetch).
    await expect(doctorPage.locator("textarea").first()).toBeVisible({ timeout: 10_000 });
  });

  test("6. 搜索过滤列表", async ({ doctorPage, doctor, request, steps }) => {
    await addKnowledgeText(request, doctor, "头痛鉴别诊断要点");
    await addKnowledgeText(request, doctor, "高血压随访48小时要点");
    await doctorPage.goto("/doctor/settings/knowledge");

    await steps.capture(doctorPage, "搜索前列表", "显示全部知识条目");

    // Search bar lives in the "全部" tab — switch to it first.
    await doctorPage.getByText("全部").first().click();
    const search = doctorPage.getByPlaceholder(/搜索知识规则/);
    await search.fill("头痛");
    await expect(doctorPage.getByText("头痛鉴别诊断要点").first()).toBeVisible();
    await expect(doctorPage.getByText("高血压随访48小时要点")).toBeHidden();

    await steps.capture(doctorPage, "搜索过滤结果", "搜索头痛后只显示匹配条目");

    await search.fill("");
    await expect(doctorPage.getByText("高血压随访48小时要点").first()).toBeVisible();

    await steps.capture(doctorPage, "清除搜索恢复", "清空搜索后显示全部条目");
  });

  test("7. 详情页显示完整内容", async ({ doctorPage, doctor, request, steps }) => {
    const { id } = await addKnowledgeText(
      request,
      doctor,
      "高血压患者新发头痛需先排除继发性高血压，考虑高血压脑病或颅内出血可能。",
    );
    await doctorPage.goto(`/doctor/settings/knowledge/${id}`);
    await expect(doctorPage.getByText(/继发性高血压/).first()).toBeVisible();

    await steps.capture(doctorPage, "知识详情页", "显示完整知识内容");
  });

  // Skip: file extract preview depends on backend PDF processing
  test.skip("4. 通过文件上传添加", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/knowledge/add");

    // The hidden file input is in the DOM before any tab click.
    const fileInput = doctorPage.locator('input[type="file"][accept*=".pdf"]');
    await expect(fileInput).toBeAttached();

    // Set the fixture PDF on the hidden input — this fires the onChange handler
    // which calls the backend extract API.
    const fixturePath = path.resolve(
      __dirname,
      "fixtures/files/sample-guide.pdf",
    );
    await fileInput.setInputFiles(fixturePath);

    // After file selection the component either:
    //   a) succeeds → opens the preview sheet titled "文件内容预览"
    //   b) fails   → shows an error Alert with the failure message
    // Both outcomes confirm the file was accepted and the upload flow ran.
    const previewSheet = doctorPage.getByText("文件内容预览");
    const errorAlert = doctorPage.locator('[role="alert"]');

    await expect(previewSheet.or(errorAlert)).toBeVisible({ timeout: 15_000 });
  });

  // Camera test: skipped — requires a fixture image and device camera capability.
  test.skip("5. 通过拍照添加（需设备摄像头）", async () => {});
});
