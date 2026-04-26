// DoctorHeader — top card on the doctor detail surface.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html `.dh` block.
//
// Layout: portrait | meta | actions (44px portrait + name/title/sub | 3 buttons).
// Color rules (codex v3 polish):
//   - Portrait is info-tinted (NOT brand) — green is reserved for the dept chip
//     and the primary CTA only.
//   - Dept chip is the only place green appears in the header meta.

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 10);
  return `${d.getFullYear()}·${String(d.getMonth() + 1).padStart(2, "0")}·${String(d.getDate()).padStart(2, "0")}`;
}

function fmtRelative(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 16);
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return fmtDate(ts);
}

function firstChar(name) {
  if (!name) return "医";
  const trimmed = String(name).trim();
  return trimmed ? trimmed.charAt(0) : "医";
}

export default function DoctorHeader({ doctor }) {
  if (!doctor) return null;
  const name = doctor.name || doctor.doctor_id || "—";
  const title = doctor.title || doctor.role || "";
  const dept = doctor.department || doctor.specialty || "";
  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        padding: 16,
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 16,
        alignItems: "center",
        boxShadow: "0 1px 1px rgba(15,23,28,0.04)",
      }}
    >
      {/* Portrait */}
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          background: COLOR.infoTint,
          color: COLOR.info,
          display: "grid",
          placeItems: "center",
          fontSize: FONT.lg,
          fontWeight: 600,
          border: `1px solid ${COLOR.infoTint}`,
        }}
      >
        {firstChar(name)}
      </div>

      {/* Meta */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span
            style={{
              fontSize: FONT.lg,
              fontWeight: 600,
              color: COLOR.text1,
              letterSpacing: "-0.005em",
            }}
          >
            {name}
          </span>
          {title && (
            <span style={{ fontSize: FONT.base, color: COLOR.text2 }}>{title}</span>
          )}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: FONT.sm,
            color: COLOR.text2,
            flexWrap: "wrap",
          }}
        >
          {dept && (
            <span
              style={{
                background: COLOR.brandTint,
                color: COLOR.brand,
                padding: "2px 9px",
                borderRadius: RADIUS.pill,
                fontWeight: 500,
                fontSize: 11.5,
              }}
            >
              {dept}
            </span>
          )}
          <span>注册于 {fmtDate(doctor.created_at)}</span>
          <span
            style={{
              width: 3,
              height: 3,
              background: COLOR.text4,
              borderRadius: "50%",
              display: "inline-block",
            }}
          />
          <span>最近活跃 {fmtRelative(doctor.last_active)}</span>
          <span
            style={{
              width: 3,
              height: 3,
              background: COLOR.text4,
              borderRadius: "50%",
              display: "inline-block",
            }}
          />
          <span
            style={{
              fontFamily: FONT_STACK.mono,
              fontSize: FONT.xs,
              color: COLOR.text3,
            }}
          >
            {doctor.doctor_id}
          </span>
        </div>
      </div>

      {/* Actions intentionally absent — 导出 / 查看消息 / 设置随访目标 were
          placeholders. 查看消息 was redundant with the existing 沟通 tab,
          and 导出 + 设置随访目标 don't have real backends yet. They'll
          return as wired buttons once the underlying flows ship. */}
    </section>
  );
}
