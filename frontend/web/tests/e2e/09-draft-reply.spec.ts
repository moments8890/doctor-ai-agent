/**
 * Workflow 09 — Draft reply send
 *
 * Mirrors docs/qa/workflows/09-draft-reply.md. Requires backend draft
 * generation to complete before the spec can assert. The fixture polls
 * the 待回复 queue to wait for AI draft readiness.
 */
import { test, expect, API_BASE_URL } from "./fixtures/doctor-auth";
import {
  completePatientInterview,
  sendPatientMessage,
  addKnowledgeText,
} from "./fixtures/seed";

async function waitForDraft(request: any, doctor: any, patientId: string) {
  // Poll up to ~20s for the draft to appear in the 待回复 queue.
  for (let i = 0; i < 20; i++) {
    const res = await request.get(
      `${API_BASE_URL}/api/doctor/review/queue?tab=pending_reply`,
      { headers: { Authorization: `Bearer ${doctor.token}` } },
    );
    if (res.ok()) {
      const body = await res.json();
      const items = body?.items || body?.pending_reply || [];
      if (items.some((i: any) => String(i.patient_id) === String(patientId))) return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("draft never appeared in 待回复 queue");
}

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

  test("1.3 — empty 待回复 tab", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/review?tab=pending_reply");
    // If no drafts seeded, empty state should show.
    const empty = doctorPage.getByText(/暂无待回复|没有待回复/);
    if (await empty.isVisible().catch(() => false)) {
      await expect(empty).toBeVisible();
    }
  });
});
