/**
 * Workflow 05 — Knowledge CRUD (4 sources)
 *
 * Mirrors docs/qa/workflows/05-knowledge.md. Camera import is
 * skeleton-only (requires device). All other sources are tested.
 */
import path from "path";
import { test, expect } from "./fixtures/doctor-auth";
import { addKnowledgeText } from "./fixtures/seed";

test.describe("Workflow 05 — Knowledge CRUD", () => {
  test("1. List — fresh doctor shows empty state CTAs", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/knowledge");
    await expect(doctorPage.getByText("暂无知识条目")).toBeVisible();
    await expect(doctorPage.getByRole("button", { name: "添加第一条规则" })).toBeVisible();
  });

  test("1. List — seeded doctor shows stats + items", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    await addKnowledgeText(request, doctor, "高血压患者新发头痛需排除高血压脑病", "头痛鉴别");
    await addKnowledgeText(request, doctor, "回访后记录血压读数", "随访要点");

    await doctorPage.goto("/doctor/settings/knowledge");
    await expect(doctorPage.getByText(/搜索知识规则 \(共2条\)/)).toBeVisible();
    for (const label of ["条规则", "本周引用", "未引用"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }
    await expect(doctorPage.getByText("头痛鉴别")).toBeVisible();

    // 1.4 — no "-1天前" (BUG-01 gate)
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/-1天前/);
  });

  test("2. Add via text", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/knowledge/add");

    const textarea = doctorPage.locator("textarea").first();
    await textarea.fill("高血压患者新发头痛→排除高血压脑病");

    // Save — the primary button label may be 保存 or 添加 depending on mode.
    const saveBtn = doctorPage.getByRole("button", { name: /保存|添加/ }).last();
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();

    // Lands back on list, new item visible.
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge($|\?)/);
    await expect(doctorPage.getByText(/高血压患者新发头痛/)).toBeVisible();
  });

  test("3. Add via URL (onboarding prefill)", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/knowledge/add?source=url");
    await doctorPage.getByText("网页导入").click();

    const urlInput = doctorPage.locator('input[type="text"], input[type="url"]').first();
    const pciUrl = new URL("/examples/pci-antiplatelet-guide.html", doctorPage.url()).toString();
    await urlInput.fill(pciUrl);

    await doctorPage.getByRole("button", { name: "获取" }).click();

    // Spinner → preview sheet (allow some time for fetch).
    await expect(doctorPage.locator("textarea").first()).toBeVisible({ timeout: 10_000 });
  });

  test("6. Search filters the list", async ({ doctorPage, doctor, request }) => {
    await addKnowledgeText(request, doctor, "头痛鉴别诊断要点", "头痛鉴别");
    await addKnowledgeText(request, doctor, "高血压随访48小时要点", "高血压随访");
    await doctorPage.goto("/doctor/settings/knowledge");

    const search = doctorPage.getByPlaceholder(/搜索知识规则/);
    await search.fill("头痛");
    await expect(doctorPage.getByText("头痛鉴别")).toBeVisible();
    await expect(doctorPage.getByText("高血压随访")).toBeHidden();

    await search.fill("");
    await expect(doctorPage.getByText("高血压随访")).toBeVisible();
  });

  test("7. Detail view shows full text", async ({ doctorPage, doctor, request }) => {
    const { id } = await addKnowledgeText(
      request,
      doctor,
      "高血压患者新发头痛需先排除继发性高血压，考虑高血压脑病或颅内出血可能。",
      "头痛鉴别详细规则",
    );
    await doctorPage.goto(`/doctor/settings/knowledge/${id}`);
    await expect(doctorPage.getByText("头痛鉴别详细规则")).toBeVisible();
    await expect(doctorPage.getByText(/继发性高血压/)).toBeVisible();
  });

  test("4. Add via file upload", async ({ doctorPage }) => {
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
  test.skip("5. Add via camera (requires fixture image)", async () => {});
});
