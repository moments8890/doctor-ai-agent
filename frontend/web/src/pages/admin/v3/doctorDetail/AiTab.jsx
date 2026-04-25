// AiTab — admin v3 doctor detail "AI 与知识" tab.
// Spec: docs/plans/2026-04-24-admin-modern-port.md — Task 2.5.
// Mockup: docs/specs/2026-04-24-admin-modern-mockup-v3.html `.deck` block
//         (lines ~1849-1983).
//
// Wire-up:
//   - Receives `related` (the full /api/admin/doctors/{id}/related response).
//   - Pulls `related.suggestions?.items || []` and runs toDecisionCards().
//   - Empty → inline empty-state (Task 4.3 ships shared <EmptyState>; we
//     match the convention of sibling tabs like AlertList / PatientsTab).
//   - Non-empty → 2-col `.deck` grid of <DecisionCard>s.
//
// Props:
//   related — raw /related payload. Optional.
//   suggestions — alternative: pass items[] directly (used in tests/storybook).

import { toDecisionCards } from "./decisionCardData";
import DecisionCard from "./DecisionCard";
import EmptyState from "../components/EmptyState";

export default function AiTab({ related, suggestions }) {
  const rawItems =
    suggestions ?? related?.suggestions?.items ?? [];
  const cards = toDecisionCards(rawItems, related);

  if (cards.length === 0) {
    return (
      <div style={{ marginTop: 16 }}>
        <EmptyState
          icon="inbox"
          title="暂无 AI 决策记录"
          desc="该医生最近还没有产生 AI 起草或风险信号。"
        />
      </div>
    );
  }

  return (
    <div
      className="deck"
      data-v3="row-2"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 14,
        paddingTop: 16,
      }}
    >
      {cards.map((c) => (
        <DecisionCard key={c.id ?? `${c.patient?.name}-${c.time}`} card={c} />
      ))}
    </div>
  );
}
