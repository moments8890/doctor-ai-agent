/**
 * Workflow 18 — Teaching loop round-trip (cross-workflow integration)
 *
 * Mirrors docs/qa/workflows/18-teaching-loop.md.
 *
 * This is the core product proof: "AI thinks like me." It verifies:
 *   1. Doctor edits a draft → edit saved as knowledge rule (workflows 09 → 05)
 *   2. Rule visible in knowledge list (workflow 05)
 *   3. Rule cited in the next diagnosis (workflow 08)
 *
 * Requires a LIVE LLM backend (NO_PROXY=* no_proxy=*). Draft generation
 * and diagnosis are async — the test uses waitForDraft / waitForSuggestions
 * to poll. Expect ~60-90 s total runtime.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  completePatientIntake,
  sendPatientMessage,
  waitForDraft,
  waitForSuggestions,
} from "./fixtures/seed";
import {
  API_BASE_URL,
  registerPatient,
  type TestDoctor,
  type TestPatient,
} from "./fixtures/doctor-auth";

// Skip: all tests in this spec require a live LLM backend for draft generation,
// teaching prompt detection, and diagnosis pipeline. Cannot be run in CI without
// a real LLM endpoint.
test.describe("工作流 18 — 教学闭环", () => {
  test.slow();

  test.skip("完整链路：编辑草稿→保存规则→下次诊断引用规则", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // ────────────────────────────────────────────────────────
    // Phase 1 — Seed data and generate a draft (workflow 09)
    // ────────────────────────────────────────────────────────

    // 1.1 — Seed a knowledge item so the AI has grounding context.
    await addKnowledgeText(
      request,
      doctor,
      "高血压患者建议优先使用ARB类降压药，避免未评估即用β受体阻滞剂",
    );

    // 1.2 — Complete a patient intake to establish medical context.
    await completePatientIntake(request, patient);

    // 1.3 — Patient sends a follow-up message to trigger draft generation.
    await sendPatientMessage(
      request,
      patient,
      "医生，最近血压控制不好，是否需要调整用药方案？",
    );

    // 1.4 — Wait for the async draft pipeline to produce a draft.
    await waitForDraft(request, doctor, patient.patientId, {
      timeoutMs: 45_000,
    });

    // ────────────────────────────────────────────────────────
    // Phase 2 — Edit the draft significantly (workflow 09)
    // ────────────────────────────────────────────────────────

    // 2.1 — Navigate to the pending reply queue.
    await doctorPage.goto("/doctor/review?tab=pending_reply");
    await expect(doctorPage.getByText(patient.name)).toBeVisible({
      timeout: 10_000,
    });

    await steps.capture(doctorPage, "待回复队列", "显示待回复患者列表");

    // 2.2 — Open the chat view for this patient.
    await doctorPage.getByText(patient.name).click();
    // After clicking, the app navigates to patient detail with ?view=chat
    await expect(doctorPage).toHaveURL(/view=chat/);
    await expect(
      doctorPage.getByText("AI起草回复 · 待你确认"),
    ).toBeVisible({ timeout: 10_000 });

    await steps.capture(doctorPage, "AI草稿页面", "显示AI起草的回复内容");

    // 2.3 — Enter edit mode.
    await doctorPage.getByText("修改").first().click();
    await expect(doctorPage.getByText("正在编辑AI草稿")).toBeVisible();

    // 2.4 — Replace with substantially different content (> 10 changed chars).
    const teachingEdit =
      "根据你的情况，我建议调整为ARB类药物（如缬沙坦80mg），每日一次，早晨空腹服用。同时建议每天早晚各测一次血压并记录。两周后复查。";
    const input = doctorPage.locator("textarea, input[type='text']").last();
    await input.fill(teachingEdit);

    // 2.5 — Tap send (AppButton = div, use getByText)
    await doctorPage
      .getByText(/发送|送出/, { exact: false })
      .first()
      .click();
    await expect(doctorPage.getByText("确认发送回复")).toBeVisible({
      timeout: 5_000,
    });

    // 2.6 — Confirm send inside dialog (ConfirmDialog uses AppButton = div)
    const sendDialog = doctorPage.locator("[role=dialog]");
    await sendDialog.getByText("发送", { exact: true }).click();

    // The teaching ConfirmDialog should appear.
    await expect(doctorPage.getByText("保存为知识规则")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      doctorPage.getByText(/你的修改有价值/),
    ).toBeVisible();

    await steps.capture(doctorPage, "教学提示弹窗", "显示保存为知识规则确认");

    // 2.7 — Verify button order: 跳过 LEFT, 保存 RIGHT.
    const skipBtn = doctorPage.locator("[role=dialog]").getByText("跳过", { exact: true });
    const saveBtn = doctorPage.locator("[role=dialog]").getByText("保存", { exact: true });
    const skipBox = await skipBtn.boundingBox();
    const saveBox = await saveBtn.boundingBox();
    expect(skipBox).toBeTruthy();
    expect(saveBox).toBeTruthy();
    expect(skipBox!.x).toBeLessThan(saveBox!.x); // cancel LEFT, primary RIGHT

    // ────────────────────────────────────────────────────────
    // Phase 3 — Save as rule (workflow 09 → 05)
    // ────────────────────────────────────────────────────────

    // 3.1 — Tap "保存" to create the knowledge rule from the edit.
    await saveBtn.click();
    // Dialog should close after save completes.
    await expect(doctorPage.getByText("保存为知识规则")).toBeHidden({
      timeout: 10_000,
    });

    // 3.2–3.3 — Navigate to knowledge list and verify the rule exists.
    await doctorPage.goto("/doctor/settings/knowledge");

    await expect(
      doctorPage.getByText(/ARB类药物/).first(),
    ).toBeVisible({ timeout: 10_000 });

    await steps.capture(doctorPage, "知识列表含新规则", "保存的ARB规则出现在知识列表中");

    // ────────────────────────────────────────────────────────
    // Phase 4 — Round-trip: rule cited in next diagnosis (workflow 08)
    // ────────────────────────────────────────────────────────

    // 4.1 — Register a second patient so we get a clean intake context.
    const patient2 = await registerPatient(request, doctor.doctorId, {
      name: "E2E回访患者",
    });

    // 4.2 — Complete an intake with ARB-related keywords.
    const { recordId } = await completePatientIntake(request, patient2, [
      "最近头晕发作，血压偏高到150/95，想了解ARB类降压药是否适合",
      "没有吃过降压药，之前一直没重视",
      "家里有血压计，可以每天测量",
    ]);

    // 4.3 — Wait for async diagnosis pipeline to generate suggestions.
    await waitForSuggestions(request, doctor, recordId, {
      timeoutMs: 45_000,
    });

    // 4.4 — Navigate to the review page for the new record.
    await doctorPage.goto(`/doctor/review/${recordId}`);
    await expect(doctorPage.getByText("诊断审核")).toBeVisible({
      timeout: 10_000,
    });

    // Verify the three standard sections are present.
    for (const section of ["鉴别诊断", "检查建议", "治疗方向"]) {
      await expect(
        doctorPage.getByText(section, { exact: true }),
      ).toBeVisible();
    }

    // 4.5 — Verify that the suggestion content references the teaching rule.
    const bodyText = await doctorPage.locator("body").innerText();
    expect(bodyText).toMatch(/ARB|缬沙坦|降压药/);

    // 4.6 — No raw [KB-N] citation markers in the rendered page.
    expect(bodyText).not.toMatch(/\[KB-\d+\]/);

    await steps.capture(doctorPage, "诊断引用教学规则", "新患者诊断中包含ARB相关内容且无原始引用标记");
  });

  // ──────────────────────────────────────────────────────────
  // Phase 5 — Minor edit does NOT trigger teaching prompt
  // ──────────────────────────────────────────────────────────

  // Skip: requires live LLM backend for draft generation.
  test.skip("小幅修改不触发教学提示", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // 5.1 — Seed and generate a draft.
    await addKnowledgeText(request, doctor, "常规回复知识");
    await completePatientIntake(request, patient);
    await sendPatientMessage(request, patient, "请问复查需要空腹吗？");
    await waitForDraft(request, doctor, patient.patientId, {
      timeoutMs: 45_000,
    });

    await doctorPage.goto("/doctor/review?tab=pending_reply");
    await expect(doctorPage.getByText(patient.name)).toBeVisible({
      timeout: 10_000,
    });
    await doctorPage.getByText(patient.name).click();
    await expect(doctorPage).toHaveURL(/view=chat/);

    // Enter edit mode.
    await doctorPage.getByText("修改").first().click();
    await expect(doctorPage.getByText("正在编辑AI草稿")).toBeVisible();

    // 5.2 — Make a trivial change: append a period.
    const textarea = doctorPage.locator("textarea, input[type='text']").last();
    const currentText = await textarea.inputValue();
    await textarea.fill(currentText + "。");

    // Send the edited draft (AppButton = div, use getByText).
    await doctorPage
      .getByText(/发送|送出/, { exact: false })
      .first()
      .click();
    await expect(doctorPage.getByText("确认发送回复")).toBeVisible({
      timeout: 5_000,
    });
    await doctorPage.locator("[role=dialog]").getByText("发送", { exact: true }).click();

    // 5.3 — Teaching dialog should NOT appear.
    await doctorPage.waitForTimeout(2_000);
    await expect(
      doctorPage.getByText("保存为知识规则"),
    ).toBeHidden();
  });

  // ──────────────────────────────────────────────────────────
  // Phase 6 — Skip does NOT create a rule
  // ──────────────────────────────────────────────────────────

  // Skip: requires live LLM backend for draft generation.
  test.skip("跳过教学提示不创建规则", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // 6.1 — Seed, generate draft, and edit significantly.
    await addKnowledgeText(request, doctor, "复查检验项目标准");
    await completePatientIntake(request, patient);
    await sendPatientMessage(request, patient, "复查结果出来了，帮我看一下");
    await waitForDraft(request, doctor, patient.patientId, {
      timeoutMs: 45_000,
    });

    // Check initial knowledge count via API for later comparison.
    const kbBefore = await request.get(
      `${API_BASE_URL}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctor.doctorId)}`,
      {
        headers: {
          Authorization: `Bearer ${doctor.token}`,
          "Content-Type": "application/json",
        },
      },
    );
    const kbCountBefore = (await kbBefore.json()).length;

    await doctorPage.goto("/doctor/review?tab=pending_reply");
    await expect(doctorPage.getByText(patient.name)).toBeVisible({
      timeout: 10_000,
    });
    await doctorPage.getByText(patient.name).click();
    await expect(doctorPage).toHaveURL(/view=chat/);

    // Edit with a substantially different reply.
    await doctorPage.getByText("修改").first().click();
    await expect(doctorPage.getByText("正在编辑AI草稿")).toBeVisible();

    const textarea = doctorPage.locator("textarea, input[type='text']").last();
    await textarea.fill(
      "完全不同的回复内容：建议做腰穿检查排除蛛网膜下腔出血的可能，同时监测生命体征，必要时转ICU。",
    );

    await doctorPage
      .getByText(/发送|送出/, { exact: false })
      .first()
      .click();
    await expect(doctorPage.getByText("确认发送回复")).toBeVisible({
      timeout: 5_000,
    });
    await doctorPage.locator("[role=dialog]").getByText("发送", { exact: true }).click();

    // Teaching dialog should appear.
    await expect(doctorPage.getByText("保存为知识规则")).toBeVisible({
      timeout: 10_000,
    });

    // 6.2 — Tap "跳过" to dismiss (inside dialog).
    await doctorPage.locator("[role=dialog]").getByText("跳过", { exact: true }).click();
    await expect(doctorPage.getByText("保存为知识规则")).toBeHidden();

    // 6.3 — Verify no new knowledge item was created.
    const kbAfter = await request.get(
      `${API_BASE_URL}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctor.doctorId)}`,
      {
        headers: {
          Authorization: `Bearer ${doctor.token}`,
          "Content-Type": "application/json",
        },
      },
    );
    const kbCountAfter = (await kbAfter.json()).length;
    expect(kbCountAfter).toBe(kbCountBefore);
  });
});
