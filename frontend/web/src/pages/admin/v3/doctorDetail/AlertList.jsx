// AlertList — right tile in the 总览 row-3-1 grid.
// Mirrors the `panel.rail-danger` "需要关注" block in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~1430-1469).
//
// Three card rows:
//   high-risk → dangerTint bg + 高危 pill
//   warn      → warningTint bg
//   neutral   → bgCardAlt with subtle border
//
// Data: derives `flaggedPatients` client-side from `related.patients.items`.
// The /related endpoint does not yet expose risk markers, so this is a
// permissive placeholder — fall back to the empty state when nothing matches.

import Panel from "./Panel";
import { COLOR, FONT, RADIUS } from "../tokens";
import EmptyState from "../components/EmptyState";

function HighRiskRow({ name, detail, when }) {
  return (
    <div
      style={{
        padding: "11px 13px",
        borderRadius: RADIUS.md,
        background: COLOR.dangerTint,
      }}
    >
      <div
        style={{
          fontWeight: 600,
          fontSize: FONT.body,
          display: "flex",
          alignItems: "center",
          gap: 8,
          color: COLOR.text1,
        }}
      >
        {name}
        <span
          style={{
            fontSize: 9.5,
            fontWeight: 700,
            padding: "1px 7px",
            borderRadius: 999,
            background: COLOR.danger,
            color: "#fff",
            letterSpacing: "0.06em",
          }}
        >
          高危
        </span>
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: COLOR.text2,
          marginTop: 4,
        }}
      >
        {detail}
        {when && (
          <span style={{ color: COLOR.text3 }}>（{when}）</span>
        )}
      </div>
    </div>
  );
}

function WarnRow({ name, detail, hint }) {
  return (
    <div
      style={{
        padding: "11px 13px",
        borderRadius: RADIUS.md,
        background: COLOR.warningTint,
      }}
    >
      <div style={{ fontWeight: 600, fontSize: FONT.body, color: COLOR.text1 }}>
        {name}
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: COLOR.text2,
          marginTop: 4,
        }}
      >
        {detail}
        {hint && <span style={{ color: COLOR.text3 }}> {hint}</span>}
      </div>
    </div>
  );
}

function NeutralRow({ name, detail }) {
  return (
    <div
      style={{
        padding: "11px 13px",
        borderRadius: RADIUS.md,
        background: COLOR.bgCardAlt,
        border: `1px solid ${COLOR.borderSubtle}`,
      }}
    >
      <div style={{ fontWeight: 600, fontSize: FONT.body, color: COLOR.text1 }}>
        {name}
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: COLOR.text2,
          marginTop: 4,
        }}
      >
        {detail}
      </div>
    </div>
  );
}

// ViewAllLink removed — it had `cursor: pointer` but no destination.
// When the cross-doctor 全体患者 page gains a danger/warn filter, the
// natural target is `?v=3&section=overview/patients&filter=danger`,
// at which point this link comes back wired.

function deriveFlagged(patients) {
  // Heuristic: until /related exposes proper risk markers, treat any
  // patient with an explicit `risk` field as flagged. For dev databases
  // this returns nothing → empty state shows.
  if (!Array.isArray(patients)) return [];
  return patients
    .filter((p) => p && (p.risk === "danger" || p.risk === "warn"))
    .slice(0, 3);
}

export default function AlertList({ related }) {
  const items = deriveFlagged(related?.patients?.items);
  const totalFlagged = items.length;

  return (
    <Panel
      title="需要关注"
      icon="priority_high"
      rail="danger"
      aside={totalFlagged > 0 ? `${totalFlagged} 位` : ""}
      bodyPad={0}
    >
      {items.length === 0 ? (
        <div style={{ padding: "10px 12px" }}>
          <EmptyState icon="inbox" title="暂无标记患者" />
        </div>
      ) : (
        <div
          style={{
            padding: "10px 12px",
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          {items.map((p, idx) => {
            const key = p.id || p.patient_id || idx;
            if (p.risk === "danger") {
              return (
                <HighRiskRow
                  key={key}
                  name={p.name}
                  detail={p.risk_detail || "需复核"}
                  when={p.risk_when}
                />
              );
            }
            if (p.risk === "warn") {
              return (
                <WarnRow
                  key={key}
                  name={p.name}
                  detail={p.risk_detail || "未达标"}
                  hint={p.risk_hint}
                />
              );
            }
            return (
              <NeutralRow
                key={key}
                name={p.name}
                detail={p.risk_detail || "近期需关注"}
              />
            );
          })}
          {/* ViewAllLink removed — no wired destination yet. See note above. */}
        </div>
      )}
    </Panel>
  );
}
