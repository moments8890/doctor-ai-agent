# Workflow NN — &lt;Workflow Name&gt;

&lt;One-paragraph summary: what user journey this covers and why it matters.&gt;

**Area:** &lt;which code the workflow touches, e.g. `MyAIPage.jsx` + `MyAIPage API`&gt;
**Spec:** `frontend/web/tests/e2e/NN-&lt;slug&gt;.spec.ts`
**Estimated runtime:** ~X min manual / ~Y s automated

---

## Scope

**In scope**

- &lt;specific user action&gt;
- &lt;specific user action&gt;

**Out of scope**

- &lt;explicitly excluded — point at the workflow that does cover it&gt;

---

## Pre-flight

Shared pre-flight lives in [`README.md`](README.md#shared-pre-flight). This
workflow additionally needs:

- &lt;any extra seed data, e.g. "a knowledge rule containing '高血压'"&gt;
- &lt;any extra env state&gt;

If the Playwright spec owns its own seeding, list the fixture helpers used
(e.g. `seed.addKnowledgeText`, `seed.completePatientIntake`).

---

## Steps

| # | Action | Verify |
|---|--------|--------|
| 1.1 | &lt;do X&gt; | &lt;assertion&gt; |
| 1.2 | &lt;do Y&gt; | &lt;assertion&gt; |
| 2.1 | &lt;do Z&gt; | &lt;assertion&gt; |

---

## Edge cases

- &lt;case&gt; — &lt;expected behavior&gt;
- &lt;case&gt; — &lt;expected behavior&gt;

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues. Bugs specifically
affecting this workflow:

- BUG-NN — &lt;description + status&gt;

---

## Failure modes & debug tips

- If step X.Y fails, first check &lt;likely root cause&gt;.
- If the spec times out on &lt;thing&gt;, it usually means &lt;cause&gt;.
