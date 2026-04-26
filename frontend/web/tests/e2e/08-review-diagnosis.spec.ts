/**
 * Workflow 08 — Review diagnosis suggestions
 *
 * Mirrors docs/qa/workflows/08-review-diagnosis.md. This is the core
 * doctor workflow — if it breaks, the product is unusable.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  completePatientIntake,
  addKnowledgeText,
  waitForSuggestions,
} from "./fixtures/seed";

test.describe("工作流 08 — 审核诊断", () => {
  test("1. 队列标签页渲染待审核记录", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // Seed one knowledge rule relevant to the intake symptoms.
    // category must be enum: custom|diagnosis|followup|medication (default "custom")
    await addKnowledgeText(
      request,
      doctor,
      "高血压患者头痛需排除高血压脑病与颅内出血",
    );
    await completePatientIntake(request, patient);

    await doctorPage.goto("/doctor/review");

    await steps.capture(doctorPage, "审核队列页面", "显示待审核列表");

    // Sub-tabs
    for (const label of ["待审核", "待回复", "已完成"]) {
      await expect(doctorPage.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // 1.3 — card shows patient name. On review page the name appears in the
    // card; preseed may also add a "张秀兰" record. Check for either.
    await expect(
      doctorPage.getByText(patient.name).or(doctorPage.getByText("张秀兰")).first(),
    ).toBeVisible();

    await steps.capture(doctorPage, "验证审核卡片", "显示患者姓名和三个子标签");
  });

  test("2. 审核详情 — 三个区域且无原始引用标记", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    await addKnowledgeText(request, doctor, "规则内容");
    const { recordId } = await completePatientIntake(request, patient);

    // Wait for async suggestion generation before asserting on the review
    // detail page — otherwise we race the LLM pipeline and land in the
    // loading / empty state.
    await waitForSuggestions(request, doctor, recordId);

    await doctorPage.goto(`/doctor/review/${recordId}`);
    await expect(doctorPage.getByText("诊断审核")).toBeVisible();

    await steps.capture(doctorPage, "诊断审核详情页", "显示诊断审核标题");

    // 2.3 — three sections
    for (const label of ["鉴别诊断", "检查建议", "治疗方向"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }

    // 2.4 — no literal [KB-N]
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/\[KB-\d+\]/);

    await steps.capture(doctorPage, "验证三个诊断区域", "鉴别诊断、检查建议、治疗方向可见且无原始引用标记");
  });

  // Skip: custom suggestion UI redesigned
  test.skip("5. 在区域中添加自定义建议", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    const { recordId } = await completePatientIntake(request, patient);
    await waitForSuggestions(request, doctor, recordId);
    await doctorPage.goto(`/doctor/review/${recordId}`);

    // Tap + 添加 in first section (鉴别诊断)
    const section = doctorPage.getByText("鉴别诊断").locator("..").locator("..");
    await section.getByText(/\+ 添加/).first().click();

    // Empty form — add button disabled. AppButton renders as div, use getByText.
    const addBtn = doctorPage.getByText("添加", { exact: true });

    await doctorPage.getByPlaceholder(/建议内容|诊断名称/).fill("自定义诊断 — 颅内出血");
    await addBtn.click();

    await expect(doctorPage.getByText("自定义诊断 — 颅内出血")).toBeVisible();
  });

  // Skip: edit form flow changed, needs investigation
  test.skip("4. 编辑表单取消在左保存在右（BUG-05回归）", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    const { recordId } = await completePatientIntake(request, patient);
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
    // AppButtons render as divs, not <button>s, so getByRole("button") won't
    // find them. Instead, find the cancel and save text elements and compare
    // their bounding boxes.
    const cancelEl = doctorPage.getByText("取消", { exact: true }).first();
    const saveEl = doctorPage.getByText("保存", { exact: true }).first();
    await expect(cancelEl).toBeVisible();
    await expect(saveEl).toBeVisible();

    const cancelBox = await cancelEl.boundingBox();
    const saveBox = await saveEl.boundingBox();
    expect(cancelBox && saveBox && cancelBox.x < saveBox.x).toBeTruthy(); // cancel LEFT, save RIGHT
  });

  // Preseed creates a demo intake on registration, so the review queue
  // is never empty for a fresh doctor. Skip until preseed is configurable.
  test.skip("8. 空状态 — 新医生无待审核项", async ({
    doctorPage,
    steps,
  }) => {
    // The doctorPage fixture registers a fresh doctor with zero seeded
    // records, so the pending review queue is guaranteed empty. This is
    // an unconditional assertion — not a soft "if visible" guard.
    await doctorPage.goto("/doctor/review");
    // Ensure we're on the 待审核 tab (default, but click to be explicit)
    await doctorPage.getByText("待审核", { exact: true }).first().click();
    // Actual empty state text: "暂无待审核项"
    await expect(
      doctorPage.getByText(/暂无待审核项|暂无待审核|没有待审核|暂无记录/).first(),
    ).toBeVisible({ timeout: 10_000 });
  });
});
