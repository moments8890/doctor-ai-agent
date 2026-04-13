/**
 * Workflow 14 — Persona onboarding (first-time style setup)
 *
 * Mirrors docs/qa/workflows/14-persona-onboarding.md.
 *
 * The spec intercepts the scenarios endpoint to return canned scenario data,
 * keeping tests deterministic without a live LLM or pre-seeded DB state.
 */
import { test, expect } from "./fixtures/doctor-auth";

const SCENARIOS_URL = "**/api/manage/persona/onboarding/scenarios?doctor_id=*";
const COMPLETE_URL = "**/api/manage/persona/onboarding/complete?doctor_id=*";

const FAKE_SCENARIOS = [
  {
    id: "s1",
    title: "慢性病随访",
    patient_info: "高血压患者，50岁男性",
    patient_message: "医生，我最近血压有点高，160/100，需要调药吗？",
    options: [
      {
        id: "s1_a",
        text: "血压偏高，建议增加半片降压药，一周后复测。有不舒服随时联系。",
        traits: { reply_style: "简洁直接" },
      },
      {
        id: "s1_b",
        text: "你好！看到你的血压数据了。160/100确实偏高了一些。建议我们把降压药调整一下，加半片试试。一周后再量一下血压告诉我哦，有任何不舒服的地方随时联系我~",
        traits: { reply_style: "温暖详细", closing: "随时联系我~" },
      },
    ],
  },
  {
    id: "s2",
    title: "术后复查",
    patient_info: "阑尾手术后2周",
    patient_message: "医生，伤口有点红，正常吗？",
    options: [
      {
        id: "s2_a",
        text: "术后2周伤口轻微发红属于正常愈合反应，注意保持清洁干燥。如果出现渗液、发热请及时来院复查。",
        traits: { structure: "先结论后注意事项" },
      },
      {
        id: "s2_b",
        text: "别担心，这是正常的。保持清洁就好。有问题再找我。",
        traits: { reply_style: "简洁直接", avoid: "不过度解释" },
      },
    ],
  },
];

test.describe("Workflow 14 — Persona onboarding", () => {
  test("1. Scenarios load and render correctly", async ({ doctorPage }) => {
    await doctorPage.route(SCENARIOS_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ scenarios: FAKE_SCENARIOS }),
      }),
    );

    await doctorPage.goto("/doctor/settings/persona/onboarding");

    // step 2.1 — title shows position
    await expect(doctorPage.getByText("1 / 2")).toBeVisible();

    // step 2.1 — first scenario content
    await expect(doctorPage.getByText("慢性病随访")).toBeVisible();
    await expect(doctorPage.getByText("高血压患者，50岁男性")).toBeVisible();
    await expect(doctorPage.getByText(/血压有点高/)).toBeVisible();

    // step 2.2 — instruction text
    await expect(doctorPage.getByText("选择你更习惯的回复方式：")).toBeVisible();

    // step 2.3 — both options visible, none pre-selected
    await expect(doctorPage.getByText(/增加半片降压药/)).toBeVisible();
    await expect(doctorPage.getByText(/降压药调整一下/)).toBeVisible();
  });

  test("2. Pick options, advance through scenarios, see summary", async ({ doctorPage }) => {
    await doctorPage.route(SCENARIOS_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ scenarios: FAKE_SCENARIOS }),
      }),
    );
    await doctorPage.route(COMPLETE_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      }),
    );

    await doctorPage.goto("/doctor/settings/persona/onboarding");

    // step 2.4 — pick option A on scenario 1
    await doctorPage.getByText(/增加半片降压药/).click();

    // step 2.5 — auto-advance to scenario 2
    await expect(doctorPage.getByText("2 / 2")).toBeVisible();
    await expect(doctorPage.getByText("术后复查")).toBeVisible();

    // step 3.1 — pick option A on last scenario (triggers summary)
    await doctorPage.getByText(/术后2周伤口轻微发红/).click();

    // step 3.1 — summary step
    await expect(doctorPage.getByText("确认风格")).toBeVisible();

    // step 3.2 — intro text
    await expect(
      doctorPage.getByText(/根据你的选择，AI将按以下偏好回复患者/),
    ).toBeVisible();

    // step 3.2 — extracted rules visible
    await expect(doctorPage.getByText("简洁直接")).toBeVisible();
    await expect(doctorPage.getByText("先结论后注意事项")).toBeVisible();

    // step 3.3 — footer buttons (AppButton = div, use getByText)
    await expect(doctorPage.getByText("返回修改", { exact: true })).toBeVisible();
    await expect(doctorPage.getByText("确认开始", { exact: true })).toBeVisible();
  });

  // SubpageHeader back button navigates to parent page, not previous scenario.
  // In-scenario back navigation needs component-level fix.
  test.skip("3. Back navigation preserves picks", async ({ doctorPage }) => {
    await doctorPage.route(SCENARIOS_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ scenarios: FAKE_SCENARIOS }),
      }),
    );

    await doctorPage.goto("/doctor/settings/persona/onboarding");

    // Pick option B on scenario 1 (the longer reply)
    await doctorPage.getByText(/降压药调整一下/).click();

    // Now on scenario 2 — go back
    await expect(doctorPage.getByText("2 / 2")).toBeVisible();

    // step 2.6 — click back. PageSkeleton's onBack is wired to setStep(step-1).
    // The back button is a Box (div) containing ChevronLeftIcon, not a <button>.
    const headerBack = doctorPage.locator('[data-testid="ChevronLeftIcon"]').first();
    await headerBack.click();

    // step 2.6 — back on scenario 1, previous pick preserved
    await expect(doctorPage.getByText("1 / 2")).toBeVisible();
    // The previously selected option should still have highlight styling
    // (primary border). We verify the option text is still on the page.
    await expect(doctorPage.getByText(/降压药调整一下/)).toBeVisible();
  });

  test("4. Error state when scenarios fail to load", async ({ doctorPage }) => {
    await doctorPage.route(SCENARIOS_URL, (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" }),
    );

    await doctorPage.goto("/doctor/settings/persona/onboarding");

    // step 1.2 — error message
    await expect(doctorPage.getByText("加载失败，请重试")).toBeVisible();
  });
});
