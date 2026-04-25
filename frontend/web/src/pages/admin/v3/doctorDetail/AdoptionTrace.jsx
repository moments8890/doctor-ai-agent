// AdoptionTrace — single right-aligned line that follows a doctor reply
// which consumed an AI draft.
//
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.adoption-trace`, `.adoption-trace .pill.edit`, `.pill.ok`
//
// Visual: small pill (border-only) + sentence describing the diff summary.
// The pill color encodes the adoption mode:
//   ok   → 直接采纳 (border + text in brand)
//   edit → 医生修改后发送 (border + text in info)
//   neutral fallback for 改写 / unknown.
//
// Props:
//   mode:    "ok" | "edit" | "rewrite"  (defaults "edit")
//   pill:    string — override the pill label (otherwise defaults by mode)
//   summary: string — sentence after the pill (e.g. "采纳 ≈ 70% · 加入了…")

import { COLOR } from "../tokens";

const PILL_DEFAULT = {
  ok:      { label: "直接采纳",     border: COLOR.brand, color: COLOR.brand },
  edit:    { label: "医生修改后发送", border: COLOR.info,  color: COLOR.info  },
  rewrite: { label: "改写",         border: COLOR.borderDefault, color: COLOR.text2 },
};

export default function AdoptionTrace({ mode = "edit", pill, summary }) {
  const conf = PILL_DEFAULT[mode] || PILL_DEFAULT.edit;
  const label = pill || conf.label;

  return (
    <div
      style={{
        alignSelf: "flex-end",
        maxWidth: "64%",
        fontSize: 11.5,
        color: COLOR.text2,
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginTop: -4,
      }}
    >
      <span
        style={{
          fontSize: 10.5,
          border: `1px solid ${conf.border}`,
          color: conf.color,
          borderRadius: 999,
          padding: "1px 8px",
          background: COLOR.bgCard,
          fontWeight: 500,
        }}
      >
        {label}
      </span>
      {summary && <span>{summary}</span>}
    </div>
  );
}
