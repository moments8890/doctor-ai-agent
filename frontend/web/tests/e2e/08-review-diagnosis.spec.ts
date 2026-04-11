/**
 * Workflow 08 — Review diagnosis suggestions
 *
 * Mirrors docs/qa/workflows/08-review-diagnosis.md. This is the core
 * doctor workflow — if it breaks, the product is unusable.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  completePatientInterview,
  addKnowledgeText,
  waitForSuggestions,
} from "./fixtures/seed";

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
    await addKnowledgeText(request, doctor, "规则内容");
    const { recordId } = await completePatientInterview(request, patient);

    // Wait for async suggestion generation before asserting on the review
    // detail page — otherwise we race the LLM pipeline and land in the
    // loading / empty state.
    await waitForSuggestions(request, doctor, recordId);

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
    doctor,
    patient,
    request,
  }) => {
    const { recordId } = await completePatientInterview(request, patient);
    await waitForSuggestions(request, doctor, recordId);
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
    doctor,
    patient,
    request,
  }) => {
    const { recordId } = await completePatientInterview(request, patient);
    await waitForSuggestions(request, doctor, recordId);
    await doctorPage.goto(`/doctor/review/${recordId}`);

    // waitForSuggestions already confirmed suggestions exist, so the 修改
    // button MUST be visible once a suggestion row is expanded. Remove the
    // old soft guard — if this fails, suggestions didn't generate or the
    // expand UI changed.
    //
    // Expand the first suggestion row (tap to toggle). Then assert 修改.
    const firstSuggestion = doctorPage
      .getByText("鉴别诊断")
      .locator("..")
      .locator("..")
      .locator("[role=button], [style*=cursor]")
      .first();
    await firstSuggestion.click();

    const editBtn = doctorPage.getByText("修改").first();
    await expect(editBtn).toBeVisible();
    await editBtn.click();

    // Inspect button order in the edit footer: cancel LEFT, save RIGHT.
    const footer = doctorPage.locator('[role="dialog"], form').last();
    const buttons = await footer.getByRole("button").allInnerTexts();
    const cancelIdx = buttons.findIndex((t) => /取消/.test(t));
    const saveIdx = buttons.findIndex((t) => /保存/.test(t));
    expect(cancelIdx).toBeGreaterThanOrEqual(0);
    expect(saveIdx).toBeGreaterThanOrEqual(0);
    expect(cancelIdx).toBeLessThan(saveIdx); // cancel LEFT, save RIGHT
  });

  test("8. Empty state — no pending reviews for fresh doctor", async ({
    doctorPage,
  }) => {
    // The doctorPage fixture registers a fresh doctor with zero seeded
    // records, so the pending review queue is guaranteed empty. This is
    // an unconditional assertion — not a soft "if visible" guard.
    await doctorPage.goto("/doctor/review");
    await expect(
      doctorPage.getByText(/暂无待审核|没有待审核|暂无记录/).first(),
    ).toBeVisible();
  });
});
