// AiAdoptionPanel — left tile in the 总览 row-3-1 grid.
// Mirrors `<div class="panel">…<div class="adoption">…` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~1386-1428).
//
// Layout: 40px headline (COLOR.info per codex polish — green is reserved for
// the breakdown bar / area chart) + 3-row breakdown + stacked bar + 14d area
// chart. Headline pct sign is 20px superscript.
//
// Data: pulls /api/admin/overview hero.ai_acceptance for the platform-wide
// rate. Falls back to the per-doctor stats_7d block (ai_accepted /
// ai_edited / ai_rejected) when present, since /overview is not scoped per
// doctor and the doctor detail view should reflect the visible doctor.

import { useEffect, useState } from "react";
import Panel from "./Panel";
import { COLOR, FONT, FONT_STACK } from "../tokens";

const ADMIN_TOKEN_KEY = "adminToken";

async function fetchAdminJson(url) {
  const token =
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function pct(n, total) {
  if (!total) return 0;
  return Math.round((n / total) * 100);
}

function safeRate(confirmed, total) {
  if (!total) return null;
  return Math.round((confirmed / total) * 100);
}

function BreakdownRow({ label, value, isLast }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        fontSize: FONT.base,
        padding: "5px 0",
        borderBottom: isLast ? "none" : `1px dashed ${COLOR.borderSubtle}`,
      }}
    >
      <span style={{ color: COLOR.text2 }}>{label}</span>
      <span
        style={{
          fontVariantNumeric: "tabular-nums",
          fontWeight: 500,
          color: COLOR.text1,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function StackedBar({ accept, edit, reject }) {
  return (
    <div
      style={{
        width: "100%",
        height: 4,
        background: COLOR.bgCanvas,
        borderRadius: 999,
        overflow: "hidden",
        marginTop: 12,
        display: "flex",
      }}
    >
      <span style={{ height: "100%", width: `${accept}%`, background: COLOR.brand }} />
      <span
        style={{
          height: "100%",
          width: `${edit}%`,
          background: COLOR.info,
          opacity: 0.85,
        }}
      />
      <span
        style={{
          height: "100%",
          width: `${reject}%`,
          background: COLOR.danger,
          opacity: 0.6,
        }}
      />
    </div>
  );
}

function AreaChart() {
  // Static 600x130 area chart matching the mockup `path`/`polyline` exactly.
  // The shape is illustrative — no live 14-day series is exposed by the API
  // yet. Once the backend ships a per-doctor adoption time-series, swap the
  // hardcoded points for the API response.
  const points =
    "0,86 40,76 80,82 120,68 160,64 200,52 240,58 280,46 320,50 360,38 400,44 440,30 480,36 520,26 560,32 600,20";
  return (
    <>
      <svg
        viewBox="0 0 600 130"
        preserveAspectRatio="none"
        style={{
          width: "100%",
          height: 130,
          display: "block",
          marginTop: 14,
        }}
      >
        <defs>
          <linearGradient id="adoptionFillBrand" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={COLOR.brand} stopOpacity="0.18" />
            <stop offset="100%" stopColor={COLOR.brand} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" x2="600" y1="32" y2="32" stroke={COLOR.borderSubtle} strokeDasharray="2 4" />
        <line x1="0" x2="600" y1="65" y2="65" stroke={COLOR.borderSubtle} strokeDasharray="2 4" />
        <line x1="0" x2="600" y1="98" y2="98" stroke={COLOR.borderSubtle} strokeDasharray="2 4" />
        <path
          d={`M0,86 L40,76 L80,82 L120,68 L160,64 L200,52 L240,58 L280,46 L320,50 L360,38 L400,44 L440,30 L480,36 L520,26 L560,32 L600,20 L600,130 L0,130 Z`}
          fill="url(#adoptionFillBrand)"
        />
        <polyline
          points={points}
          fill="none"
          stroke={COLOR.brand}
          strokeWidth="2"
        />
        <circle cx="600" cy="20" r="3.5" fill={COLOR.brand} />
      </svg>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: FONT.xs,
          color: COLOR.text3,
          fontFamily: FONT_STACK.mono,
          marginTop: 4,
        }}
      >
        <span>04·10</span>
        <span>04·14</span>
        <span>04·18</span>
        <span>04·22</span>
        <span>今日</span>
      </div>
    </>
  );
}

export default function AiAdoptionPanel({ doctor }) {
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchAdminJson("/api/admin/overview")
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch(() => {
        // Non-fatal — fall back to doctor.stats_7d below.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Prefer per-doctor numbers (always available on stats_7d) so the panel
  // reflects the doctor whose detail page is shown.
  const stats = doctor?.stats_7d || {};
  const perDoctorTotal =
    (stats.ai_accepted || 0) +
    (stats.ai_edited || 0) +
    (stats.ai_rejected || 0);

  let confirmed = stats.ai_accepted || 0;
  let edited = stats.ai_edited || 0;
  let rejected = stats.ai_rejected || 0;
  let total = perDoctorTotal;

  if (perDoctorTotal === 0 && overview?.hero?.ai_acceptance) {
    const ai = overview.hero.ai_acceptance;
    confirmed = ai.confirmed || 0;
    edited = ai.edited || 0;
    rejected = ai.rejected || 0;
    total = confirmed + edited + rejected;
  }

  const rate = safeRate(confirmed, total);
  const acceptPct = pct(confirmed, total);
  const editPct = pct(edited, total);
  const rejectPct = pct(rejected, total);

  return (
    <Panel
      title="AI 建议如何被使用"
      icon="network_intelligence"
      aside={total > 0 ? `14d · ${total} 条` : "14d"}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: 24,
          alignItems: "center",
        }}
      >
        <div
          style={{
            fontSize: 40,
            lineHeight: 1,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            color: COLOR.info,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {rate != null ? rate : "—"}
          {rate != null && (
            <span
              style={{
                fontSize: 20,
                verticalAlign: "super",
                marginLeft: 2,
                color: COLOR.info,
              }}
            >
              %
            </span>
          )}
        </div>
        <div>
          <BreakdownRow label="直接采纳" value={confirmed} />
          <BreakdownRow label="医生修改后采纳" value={edited} />
          <BreakdownRow label="拒绝 / 改写" value={rejected} isLast />
        </div>
      </div>
      <StackedBar
        accept={total > 0 ? acceptPct : 60}
        edit={total > 0 ? editPct : 18}
        reject={total > 0 ? rejectPct : 22}
      />
      <AreaChart />
    </Panel>
  );
}
