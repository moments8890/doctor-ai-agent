/**
 * Smoke test — Inline AI suggestions review UI (Phase 1a+1b).
 *
 * Validates the new INLINE_SUGGESTIONS_V2 render path inside
 * `src/v2/pages/doctor/ReviewPage.jsx`. The flag is off at build time;
 * this spec opts in per-test via the `?inline_v2=1` URL query param.
 *
 * Scope: render + one accept interaction. Not a full Ship Gate coverage.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  completePatientIntake,
  waitForSuggestions,
} from "./fixtures/seed";

test.describe("工作流 18 — 内联 AI 建议（inline_v2）", () => {
  test("内联布局渲染并可采纳诊断建议", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // Seed a KB rule so suggestions cite something; not required but mirrors
    // production flow where the LLM grounds itself in the doctor's rules.
    await addKnowledgeText(
      request,
      doctor,
      "高血压患者头痛需排除高血压脑病与颅内出血",
    );

    // Complete a pre-intake so a reviewable record exists.
    const { recordId } = await completePatientIntake(request, patient);

    // Wait for the async suggestion pipeline to produce rows — otherwise the
    // inline branch will not render (gated on hasSuggestions).
    await waitForSuggestions(request, doctor, recordId);

    // Navigate with inline_v2=1 to opt into the new layout for this tab only.
    await doctorPage.goto(`/doctor/review/${recordId}?inline_v2=1`);

    // Wait for the page header before asserting on inline-specific elements.
    await expect(doctorPage.getByText("诊断审核")).toBeVisible();

    await steps.capture(
      doctorPage,
      "内联审核页面初始渲染",
      "URL 参数 ?inline_v2=1 已启用，页面显示诊断审核标题",
    );

    // 1. Patient name visible (inline banner renders patient_name).
    await expect(
      doctorPage.getByText(patient.name).or(doctorPage.getByText("张秀兰")).first(),
    ).toBeVisible();

    // 2. Three FieldWithAI section labels — note that "诊断" is substring-safe
    //    when paired with { exact: true }. The legacy layout instead uses
    //    "鉴别诊断/检查建议/治疗方向" as SectionHeader texts; the inline
    //    FieldWithAI labels are "诊断/检查建议/治疗方向".
    await expect(doctorPage.getByText("诊断", { exact: true }).first()).toBeVisible();
    await expect(doctorPage.getByText("检查建议", { exact: true }).first()).toBeVisible();
    await expect(doctorPage.getByText("治疗方向", { exact: true }).first()).toBeVisible();

    // 3. At least one 采纳 button — FieldWithAI uses plain <button> for the
    //    AI row action, so getByRole("button") works here (unlike AppButton).
    const acceptBtn = doctorPage.getByRole("button", { name: "采纳" }).first();
    await expect(acceptBtn).toBeVisible();

    // 4. Bottom "完成审核" Button — antd-mobile Button renders a real <button>.
    const finishBtn = doctorPage.getByRole("button", { name: /完成审核/ });
    await expect(finishBtn).toBeVisible();
    // Counter text — "N 条未处理" should be present alongside the label.
    await expect(doctorPage.getByText(/\d+\s*条未处理/).first()).toBeVisible();

    await steps.capture(
      doctorPage,
      "验证内联布局",
      "三个 FieldWithAI 区域（诊断/检查建议/治疗方向）、采纳按钮与“完成审核 · N 条未处理”底部栏均可见",
    );

    // 5. Accept the top pending 诊断 suggestion. The 诊断 FieldWithAI is the
    //    first section, so the first 采纳 button on the page belongs to it.
    await acceptBtn.click();

    // After accept, the row should collapse into an AcceptedRow that shows
    // "已采纳" as a label. The previously visible 采纳 button for this row
    // is gone (pending list empties since 诊断 does not allow cycle and had
    // one pending).
    await expect(doctorPage.getByText(/已采纳/).first()).toBeVisible({
      timeout: 5_000,
    });

    await steps.capture(
      doctorPage,
      "采纳诊断建议",
      "点击采纳后，AI 行折叠为 ✓ 已采纳 行",
    );
  });
});
