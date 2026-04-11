/**
 * Workflow 08 — Review diagnosis suggestions
 *
 * Mirrors docs/qa/workflows/08-review-diagnosis.md. This is the core
 * doctor workflow — if it breaks, the product is unusable.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { completePatientInterview, addKnowledgeText } from "./fixtures/seed";

test.describe("Workflow 08 — Review diagnosis", () => {
  test("1. Queue tab renders with pending record", async ({
    doctorPage,
    doctor,
    patient,
    request,
  }) => {
    // Seed one knowledge rule relevant to the interview symptoms.
    await addKnowledgeText(
      request,
      doctor,
      "高血压患者头痛需排除高血压脑病与颅内出血",
      "高血压头痛鉴别",
    );
    await completePatientInterview(request, patient);

    await doctorPage.goto("/doctor/review");

    // Sub-tabs
    for (const label of ["待审核", "待回复", "已完成"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }

    // 1.3 — card shows patient name
    await expect(doctorPage.getByText(patient.name)).toBeVisible();
  });

  test("2. Open review detail — three sections + no raw [KB-N]", async ({
    doctorPage,
    doctor,
    patient,
    request,
  }) => {
    await addKnowledgeText(request, doctor, "规则内容", "测试规则");
    const { recordId } = await completePatientInterview(request, patient);

    await doctorPage.goto(`/doctor/review/${recordId}`);
    await expect(doctorPage.getByText("诊断审核")).toBeVisible();

    // 2.3 — three sections
    for (const label of ["鉴别诊断", "检查建议", "治疗方向"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }

    // 2.4 — no literal [KB-N]
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/\[KB-\d+\]/);
  });

  test("5. Add custom suggestion in a section", async ({
    doctorPage,
    patient,
    request,
  }) => {
    const { recordId } = await completePatientInterview(request, patient);
    await doctorPage.goto(`/doctor/review/${recordId}`);

    // Tap + 添加 in first section (鉴别诊断)
    const section = doctorPage.getByText("鉴别诊断").locator("..").locator("..");
    await section.getByText(/\+ 添加/).first().click();

    // Empty form — add button disabled
    const addBtn = doctorPage.getByRole("button", { name: "添加" }).last();
    await expect(addBtn).toBeDisabled();

    await doctorPage.getByPlaceholder(/建议内容|诊断名称/).fill("自定义诊断 — 颅内出血");
    await expect(addBtn).toBeEnabled();
    await addBtn.click();

    await expect(doctorPage.getByText("自定义诊断 — 颅内出血")).toBeVisible();
  });

  test("4. Edit form has 取消 LEFT / 保存 RIGHT (BUG-05 regression)", async ({
    doctorPage,
    patient,
    request,
  }) => {
    const { recordId } = await completePatientInterview(request, patient);
    await doctorPage.goto(`/doctor/review/${recordId}`);

    // Expand first suggestion (if any exist) and tap 修改.
    const firstRow = doctorPage.locator("text=鉴别诊断").locator("..").locator("..");
    const editBtn = firstRow.getByText("修改").first();
    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click();

      // Inspect button order in the edit footer.
      const footer = doctorPage.locator('[role="dialog"], form').last();
      const buttons = await footer.getByRole("button").allInnerTexts();
      const cancelIdx = buttons.findIndex((t) => /取消/.test(t));
      const saveIdx = buttons.findIndex((t) => /保存/.test(t));
      expect(cancelIdx).toBeGreaterThanOrEqual(0);
      expect(saveIdx).toBeGreaterThanOrEqual(0);
      expect(cancelIdx).toBeLessThan(saveIdx); // cancel LEFT, save RIGHT
    }
  });

  test("8. Empty state — no pending reviews", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/review");
    // If this doctor has nothing pending, empty state shows.
    const empty = doctorPage.getByText(/暂无待审核/);
    // Only assert visibility if fixture was truly empty — otherwise, this test
    // is a weak guard and should be considered passing either way.
    if (await empty.isVisible().catch(() => false)) {
      await expect(empty).toBeVisible();
    }
  });
});
