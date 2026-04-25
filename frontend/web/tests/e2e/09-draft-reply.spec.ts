/**
 * Workflow 09 — Draft reply send
 *
 * Mirrors docs/qa/workflows/09-draft-reply.md. Draft generation is async —
 * `waitForDraft` polls `/api/manage/drafts?doctor_id=…&patient_id=…` (the
 * real endpoint, not the imaginary `/api/doctor/review/queue?tab=pending_reply`)
 * until a draft exists.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  completePatientInterview,
  sendPatientMessage,
  sendDoctorReply,
  addKnowledgeText,
  waitForDraft,
} from "./fixtures/seed";

test.describe("工作流 09 — 草稿回复", () => {
  // Skip: requires LLM to generate draft
  test.skip("2-3. 打开草稿、编辑、发送确认", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // Seed context + patient message.
    // category must be enum: custom|diagnosis|followup|medication (default "custom")
    await addKnowledgeText(
      request,
      doctor,
      "回访常规咨询时先确认血压记录再给建议",
    );
    await completePatientInterview(request, patient);
    await sendPatientMessage(request, patient, "医生，我今天血压还是有点高，怎么办？");
    await waitForDraft(request, doctor, patient.patientId);

    // 1.1 — tap 待回复 tab
    await doctorPage.goto("/doctor/review?tab=pending_reply");
    await expect(doctorPage.getByText(patient.name)).toBeVisible();

    // 2.1 — open draft
    await doctorPage.getByText(patient.name).click();
    await expect(doctorPage).toHaveURL(/view=chat/);

    // 2.2 — draft bubble header
    await expect(doctorPage.getByText("AI起草回复 · 待你确认")).toBeVisible();

    // 2.3 — no raw [KB-N]
    const draftBody = await doctorPage.locator("body").innerText();
    expect(draftBody).not.toMatch(/\[KB-\d+\]/);

    // 3.1 — tap 修改
    await doctorPage.getByText("修改").first().click();
    await expect(doctorPage.getByText("正在编辑AI草稿")).toBeVisible();

    // 3.2 — append text and send
    const input = doctorPage.locator("textarea, input").last();
    const edited = "（已审核）建议继续监测血压并记录读数。";
    await input.fill(edited);

    // 3.3 — confirm sheet should show edited text, not original draft.
    // The send button is an AppButton (div), use getByText instead of getByRole.
    await doctorPage.getByText("发送", { exact: true }).first().click();
    await expect(doctorPage.getByText("确认发送回复")).toBeVisible();
    await expect(doctorPage.getByText(edited)).toBeVisible();

    // 4.1-4.2 — attribution + button order
    await expect(doctorPage.getByText(/AI辅助生成/)).toBeVisible();

    // The confirm dialog uses DialogFooter with AppButton (divs, not buttons).
    // Scope to the dialog/sheet and find text elements.
    const cancelEl = doctorPage.getByText("取消", { exact: true }).last();
    const sendEl = doctorPage.getByText("发送", { exact: true }).last();
    const cancelBox = await cancelEl.boundingBox();
    const sendBox = await sendEl.boundingBox();
    expect(cancelBox && sendBox && cancelBox.x < sendBox.x).toBeTruthy(); // cancel LEFT

    // 4.3 — send
    await sendEl.click();

    // 5.1 — sent bubble appears
    await expect(doctorPage.getByText(edited)).toBeVisible();
    await expect(doctorPage.getByText(/AI辅助生成，经医生审核/)).toBeVisible();
  });

  // Preseed creates a demo interview + draft on registration, so the 待回复
  // tab is never empty for a fresh doctor. Skip until preseed is configurable.
  test.skip("1.3 — 新医生待回复标签为空", async ({ doctorPage, steps }) => {
    // Fresh doctor = no seeded drafts, so empty state MUST render. Drop the
    // soft if-visible guard — if the copy drifts, the test should fail and we
    // update the regex, not silently skip.
    await doctorPage.goto("/doctor/review?tab=pending_reply");
    // Ensure we're on the 待回复 tab
    await doctorPage.getByText("待回复", { exact: true }).first().click();
    // Actual empty state text: "暂无待回复消息"
    await expect(
      doctorPage.getByText(/暂无待回复消息|暂无待回复|没有待回复|暂无消息|没有待处理/).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("5.4 — 患者端收到医生回复", async ({
    browser,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // This test verifies the "doctor sends → patient sees" half of §5.
    // We skip the UI-driven send (covered in the first test) and use the
    // seed.sendDoctorReply helper to push a message via the real backend
    // reply endpoint. Then we authenticate a fresh patient Page via the
    // patientPage fixture and assert the bubble arrives in ChatTab.
    const replyText =
      "（E2E测试）请继续监测血压并记录读数，有任何变化随时告诉我。";

    // Seed a completed interview so the patient has a non-empty portal state.
    await completePatientInterview(request, patient);

    // Fire the reply as the doctor — hits POST /api/manage/patients/{id}/reply.
    await sendDoctorReply(request, doctor, patient.patientId, replyText);

    // Spin up an isolated browser context for the patient portal so the
    // doctor's localStorage doesn't leak in.
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    try {
      const page = await ctx.newPage();
      // Login as the patient through the real login form (same approach as
      // the authenticatePatientPage fixture — avoids the localStorage
      // injection hydration race that caused tests to stick on /login).
      await page.goto("/login");
      await page.getByRole("tab", { name: "患者" }).click();
      await page.getByPlaceholder("请输入昵称").fill(patient.nickname);
      await page.getByPlaceholder("请输入数字口令").fill(patient.passcode);
      await page.getByRole("button", { name: "登录" }).click();
      await page.waitForURL(/\/patient/, { timeout: 15_000 });

      await steps.capture(page, "患者端登录成功", "患者登录后进入患者首页");

      // Chat is the default tab on /patient — assert the doctor's reply.
      await expect(page.getByText(replyText)).toBeVisible({ timeout: 15_000 });

      await steps.capture(page, "患者收到医生回复", "聊天中显示医生发送的回复内容");
    } finally {
      await ctx.close();
    }
  });
});
