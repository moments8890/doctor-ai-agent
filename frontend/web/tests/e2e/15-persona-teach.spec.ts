/**
 * Workflow 15 — Persona teach-by-example
 *
 * Mirrors docs/qa/workflows/15-persona-teach.md.
 *
 * The spec intercepts the teach API endpoint to return canned results,
 * keeping tests deterministic without a live LLM.
 */
import { test, expect } from "./fixtures/doctor-auth";

const TEACH_URL = "**/api/manage/persona/teach?doctor_id=*";

const SAMPLE_REPLY = "你好，根据你描述的症状和检查结果来看，目前血压控制得还不错。建议继续目前的药物方案，同时注意低盐饮食和适当运动。下次复诊我们再看看需不需要调整用药。有任何不舒服随时联系我哦~";

const FAKE_EXTRACTED = [
  { field: "reply_style", text: "温暖亲切，使用语气词" },
  { field: "structure", text: "先肯定现状，再给建议，最后安排复诊" },
  { field: "closing", text: "有任何不舒服随时联系我" },
];

test.describe("Workflow 15 — Persona teach-by-example", () => {
  test("1. Page shell renders correctly", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona/teach");

    // step 1.1 — header
    await expect(doctorPage.getByText("教AI新偏好")).toBeVisible();

    // step 1.2 — instructional text
    await expect(
      doctorPage.getByText(/粘贴一段你满意的回复.*风格偏好.*待确认队列/),
    ).toBeVisible();

    // step 1.3 — textarea placeholder
    await expect(
      doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…"),
    ).toBeVisible();

    // step 1.4 — character counter
    await expect(doctorPage.getByText("0 / 2000")).toBeVisible();

    // step 1.5 — submit button visible but disabled (AppButton = div with opacity: 0.5)
    const submitBtn = doctorPage.getByText("开始分析", { exact: true });
    await expect(submitBtn).toBeVisible();
    // AppButton uses opacity: 0.5 when disabled — check CSS
    await expect(submitBtn).toHaveCSS("opacity", "0.5");
  });

  test("2. Input validation enables/disables submit button", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/persona/teach");

    const textarea = doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…");
    const submitBtn = doctorPage.getByText("开始分析", { exact: true });

    // step 2.1 — spaces only keeps button disabled (opacity 0.5)
    await textarea.fill("   ");
    await expect(submitBtn).toHaveCSS("opacity", "0.5");

    // step 2.2 — real text enables button (opacity 1)
    await textarea.fill("你好，这是一段测试回复");
    await expect(submitBtn).toHaveCSS("opacity", "1");

    // step 2.2 — counter updates (character count depends on exact text length)
    await expect(doctorPage.getByText(/\d+ \/ 2000/).first()).toBeVisible();

    // step 2.3 — clear text re-disables (opacity 0.5)
    await textarea.fill("");
    await expect(submitBtn).toHaveCSS("opacity", "0.5");
    await expect(doctorPage.getByText("0 / 2000")).toBeVisible();
  });

  test("3. Successful analysis shows extracted rules", async ({ doctorPage }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ extracted: FAKE_EXTRACTED, count: 3 }),
      }),
    );

    await doctorPage.goto("/doctor/settings/persona/teach");

    const textarea = doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…");
    await textarea.fill(SAMPLE_REPLY);

    const submitBtn = doctorPage.getByText("开始分析", { exact: true });
    await submitBtn.click();

    // step 3.2 — results appear
    await expect(doctorPage.getByText(/发现 3 条偏好.*待确认队列/)).toBeVisible();

    // Each extracted rule visible
    await expect(doctorPage.getByText("温暖亲切，使用语气词")).toBeVisible();
    await expect(doctorPage.getByText("先肯定现状，再给建议，最后安排复诊")).toBeVisible();
    await expect(doctorPage.getByText("有任何不舒服随时联系我").first()).toBeVisible();

    // Field labels visible
    await expect(doctorPage.getByText("回复风格")).toBeVisible();
    await expect(doctorPage.getByText("回复结构")).toBeVisible();
    await expect(doctorPage.getByText("常用结尾语")).toBeVisible();
  });

  test("4. No rules found shows fallback message", async ({ doctorPage }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ extracted: [], count: 0 }),
      }),
    );

    await doctorPage.goto("/doctor/settings/persona/teach");

    await doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…").fill("你好");
    await doctorPage.getByText("开始分析", { exact: true }).click();

    // step 4.1 — empty result message
    await expect(
      doctorPage.getByText("未发现明显的风格偏好，请尝试粘贴更完整的回复"),
    ).toBeVisible();
  });

  test("5. API error shows error message", async ({ doctorPage }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" }),
    );

    await doctorPage.goto("/doctor/settings/persona/teach");

    await doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…").fill(SAMPLE_REPLY);
    await doctorPage.getByText("开始分析", { exact: true }).click();

    // step 5.1 — error message
    await expect(doctorPage.getByText("分析失败，请重试")).toBeVisible();

    // step 5.1 — textarea re-enabled
    await expect(
      doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…"),
    ).toBeEnabled();
    // Button re-enabled (opacity 1)
    await expect(
      doctorPage.getByText("开始分析", { exact: true }),
    ).toHaveCSS("opacity", "1");
  });
});
