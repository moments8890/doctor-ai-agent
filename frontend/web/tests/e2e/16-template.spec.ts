/**
 * Workflow 16 — Template management
 *
 * Mirrors docs/qa/workflows/16-template.md.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("Workflow 16 — Template management", () => {
  test("1. Shell renders with no template (default state)", async ({
    doctorPage,
  }) => {
    await doctorPage.goto("/doctor/settings/template");

    // 1.1 — page header (may appear in both header and settings list; use .first())
    // Allow extra time for settings subpage to render after navigation.
    // On mobile, .first() picks the hidden settings list row. Use .last()
    // to get the visible page header on the template subpage.
    await expect(doctorPage.getByText("报告模板", { exact: true }).last()).toBeVisible({ timeout: 10_000 });

    // 1.2 — section labels
    await expect(doctorPage.getByText("当前模板", { exact: true })).toBeVisible();
    await expect(doctorPage.getByText("操作", { exact: true })).toBeVisible();

    // 1.3 — status card shows default template info
    await expect(doctorPage.getByText("门诊病历报告模板")).toBeVisible();
    await expect(
      doctorPage.getByText("使用国家卫生部 2010 年标准格式 ›"),
    ).toBeVisible();

    // 1.5 — upload action visible, no delete action
    await expect(doctorPage.getByText("上传模板文件")).toBeVisible();
    await expect(doctorPage.getByText("删除模板，恢复默认")).toBeHidden();

    // 1.6 — format hint
    await expect(
      doctorPage.getByText(/支持格式：PDF、DOCX、DOC、TXT、JPG、PNG/),
    ).toBeVisible();
  });

  test("2. Standard format preview dialog", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/template");

    // 2.1 — tap the standard format link
    await doctorPage
      .getByText("使用国家卫生部 2010 年标准格式 ›")
      .click();

    // 2.1 — dialog opens
    await expect(
      doctorPage.getByText("门诊病历标准格式", { exact: true }),
    ).toBeVisible();
    await expect(
      doctorPage.getByText(/卫医政发〔2010〕11号/),
    ).toBeVisible();

    // 2.2 — verify a sample of the 14 standard fields
    for (const field of ["1. 科别", "5. 过敏史", "12. 初步诊断", "14. 医嘱及随访"]) {
      await expect(doctorPage.getByText(field)).toBeVisible();
    }

    // 2.3 — dismiss (ConfirmDialog uses AppButton = div, use getByText inside dialog)
    await doctorPage.locator("[role=dialog]").getByText("知道了", { exact: true }).click();
    await expect(
      doctorPage.getByText("门诊病历标准格式", { exact: true }),
    ).toBeHidden();
  });

  // Upload requires a real file and triggers a native file picker which
  // Playwright cannot drive via click alone. A full test would use
  // page.setInputFiles() on the hidden <input>, but that needs a fixture
  // file and backend support. Marking as skip until a test fixture file
  // is added to the repo (e.g. tests/e2e/fixtures/test-template.txt).
  test.skip("3. Upload, replace, and delete template", async ({
    doctorPage,
  }) => {
    await doctorPage.goto("/doctor/settings/template");

    // 3.1 — upload via setInputFiles on the hidden input
    const fileInput = doctorPage.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "test-template.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("科别：\n主诉：\n现病史："),
    });

    // 3.2 — success alert
    await expect(doctorPage.getByText(/模板已上传/)).toBeVisible();

    // 3.3 — status card updated
    await expect(doctorPage.getByText("已自定义")).toBeVisible();
    await expect(doctorPage.getByText(/已上传自定义模板/)).toBeVisible();

    // 3.4 — delete row now visible
    await expect(doctorPage.getByText("替换模板文件")).toBeVisible();
    await expect(doctorPage.getByText("删除模板，恢复默认")).toBeVisible();

    // 5.1 — delete flow
    await doctorPage.getByText("删除模板，恢复默认").click();
    await expect(doctorPage.getByText("删除模板", { exact: true })).toBeVisible();
    await expect(
      doctorPage.getByText("删除后将恢复国家卫生部 2010 年标准格式。"),
    ).toBeVisible();

    // 5.2 — cancel (保留) — inside dialog
    await doctorPage.locator("[role=dialog]").getByText("保留", { exact: true }).click();
    await expect(doctorPage.getByText("已自定义")).toBeVisible();

    // 5.3 — confirm delete — inside dialog
    await doctorPage.getByText("删除模板，恢复默认").click();
    await doctorPage.locator("[role=dialog]").getByText("确认删除", { exact: true }).click();
    await expect(doctorPage.getByText(/模板已删除/)).toBeVisible();

    // 5.4 — reverted to default
    await expect(doctorPage.getByText("已自定义")).toBeHidden();
    await expect(
      doctorPage.getByText("使用国家卫生部 2010 年标准格式 ›"),
    ).toBeVisible();
  });
});
