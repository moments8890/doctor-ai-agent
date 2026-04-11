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

test.describe("Workflow 09 — Draft reply send", () => {
  test("2-3. Open draft, edit, send confirmation sheet", async ({
    doctorPage,
    doctor,
    patient,
    request,
  }) => {
    // Seed context + patient message.
    await addKnowledgeText(
      request,
      doctor,
      "回访常规咨询时先确认血压记录再给建议",
      "常规回复规则",
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

    // 3.3 — confirm sheet should show edited text, not original draft
    await doctorPage.getByRole("button", { name: /发送|送出/ }).first().click();
    await expect(doctorPage.getByText("确认发送回复")).toBeVisible();
    await expect(doctorPage.getByText(edited)).toBeVisible();

    // 4.1-4.2 — attribution + button order
    await expect(doctorPage.getByText(/AI辅助生成/)).toBeVisible();
    const cancelBtn = doctorPage.getByRole("button", { name: "取消" }).last();
    const sendBtn = doctorPage.getByRole("button", { name: "发送" }).last();
    const cancelBox = await cancelBtn.boundingBox();
    const sendBox = await sendBtn.boundingBox();
    expect(cancelBox && sendBox && cancelBox.x < sendBox.x).toBeTruthy(); // cancel LEFT

    // 4.3 — send
    await sendBtn.click();

    // 5.1 — sent bubble appears
    await expect(doctorPage.getByText(edited)).toBeVisible();
    await expect(doctorPage.getByText(/AI辅助生成，经医生审核/)).toBeVisible();
  });

  test("1.3 — empty 待回复 tab for a fresh doctor", async ({ doctorPage }) => {
    // Fresh doctor = no seeded drafts, so empty state MUST render. Drop the
    // soft if-visible guard — if the copy drifts, the test should fail and we
    // update the regex, not silently skip.
    await doctorPage.goto("/doctor/review?tab=pending_reply");
    await expect(
      doctorPage.getByText(/暂无待回复|没有待回复|暂无消息|没有待处理/).first(),
    ).toBeVisible();
  });

  test("5.4 — patient portal receives the doctor reply", async ({
    browser,
    doctor,
    patient,
    request,
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
    // doctor's localStorage doesn't leak in. (doctorPage + patientPage share
    // a single Page by default in the shared fixture; opening a new context
    // here keeps the two sessions strictly separated for this test.)
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    try {
      const page = await ctx.newPage();
      // Hydrate patient session (mirrors authenticatePatientPage helper).
      await page.goto("/login");
      await page.evaluate(
        ({ p, dn }) => {
          localStorage.setItem("patient_portal_token", p.token);
          localStorage.setItem("patient_portal_name", p.name);
          localStorage.setItem("patient_portal_doctor_id", p.doctorId);
          localStorage.setItem("patient_portal_doctor_name", dn);
          localStorage.setItem("patient_portal_patient_id", p.patientId);
        },
        { p: patient, dn: doctor.name },
      );

      // Chat is the default tab on /patient.
      await page.goto("/patient");
      await expect(page.getByText(replyText)).toBeVisible({ timeout: 15_000 });
    } finally {
      await ctx.close();
    }
  });
});
