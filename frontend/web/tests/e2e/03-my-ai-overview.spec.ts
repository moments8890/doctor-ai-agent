/**
 * Workflow 03 — My AI tab overview
 *
 * Mirrors docs/qa/workflows/03-my-ai-overview.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  addPersonaRule,
  completePatientInterview,
} from "./fixtures/seed";

test.describe("Workflow 03 — My AI overview", () => {
  test("populated doctor — all sections render", async ({
    doctorPage,
    doctor,
    patient,
    request,
  }) => {
    // Seed: 2 knowledge items, 1 persona rule, 1 completed interview.
    await addKnowledgeText(request, doctor, "高血压头痛需先排除高血压脑病", "高血压头痛鉴别");
    await addKnowledgeText(request, doctor, "回访48小时血压记录", "高血压随访要点");
    await addPersonaRule(request, doctor, "reply_style", "口语化回复，像微信聊天");
    await completePatientInterview(request, patient);

    await doctorPage.goto("/doctor/my-ai");

    // 1.1 — shell
    await expect(doctorPage.getByText("我的AI").first()).toBeVisible();
    await expect(doctorPage.getByText("本服务为AI生成内容，结果仅供参考")).toBeVisible();

    // 2.2 — hero AI name: "XXX 的 AI" — no duplicate 医生
    const aiNameLocator = doctorPage.getByText(new RegExp(`${doctor.name}.*AI`));
    await expect(aiNameLocator).toBeVisible();
    const aiNameText = await aiNameLocator.textContent();
    expect(aiNameText).not.toContain("医生医生");

    // 2.3 — knowledge subtitle
    await expect(doctorPage.getByText(/已学会 \d+ 条知识/)).toBeVisible();

    // 2.5 — 3 stat columns
    for (const label of ["7天引用", "待确认", "今日处理"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }

    // 3.1 — CTA row
    await expect(doctorPage.getByRole("button", { name: "编辑人设" })).toBeVisible();
    await expect(doctorPage.getByRole("button", { name: "添加知识" })).toBeVisible();

    // 4 — quick actions
    await expect(doctorPage.getByText("快捷入口")).toBeVisible();
    await expect(doctorPage.getByText("新建病历")).toBeVisible();
    await expect(doctorPage.getByText("患者预问诊码")).toBeVisible();

    // 5 — persona card
    await expect(doctorPage.getByText("我的AI人设")).toBeVisible();
    await expect(doctorPage.getByText(/口语化回复/)).toBeVisible();

    // 6 — knowledge preview
    await expect(doctorPage.getByText("我的知识库")).toBeVisible();
    await expect(doctorPage.getByText("高血压头痛鉴别")).toBeVisible();
    await expect(doctorPage.getByText(/全部 \d+ 条/)).toBeVisible();

    // 6.4 — relative date must NOT be "-1天前" (BUG-01 gate)
    const bodyText = await doctorPage.locator("body").innerText();
    expect(bodyText).not.toMatch(/-1天前/);

    // 7 — activity section
    await expect(doctorPage.getByText("最近由AI处理")).toBeVisible();
  });

  test("fresh doctor — empty states render CTAs", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/my-ai");

    // 2.3 — zero knowledge subtitle
    await expect(doctorPage.getByText("尚未添加知识")).toBeVisible();

    // 6.7 — knowledge empty CTAs
    await expect(doctorPage.getByText("上传指南")).toBeVisible();
    await expect(doctorPage.getByText("粘贴常用回复")).toBeVisible();

    // 5.3 — persona empty hint
    await expect(doctorPage.getByText("尚未设置，点击编辑开始配置")).toBeVisible();

    // 7.2 — activity empty state
    await expect(doctorPage.getByText("暂无AI处理记录")).toBeVisible();
  });

  test("navigation — CTAs route to correct subpages", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/my-ai");

    await doctorPage.getByRole("button", { name: "编辑人设" }).click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/persona/);
    await doctorPage.goBack();

    await doctorPage.getByRole("button", { name: "添加知识" }).click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge\/add/);
  });
});
