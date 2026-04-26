// AiActivityPage — admin v3 知识 & AI cross-doctor activity page.
//
// First-impression page for the partner doctor: a condensed feed of recent AI
// suggestions across the entire platform with their doctor decision outcomes.
// Visual reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
// `.deck` + `.dc` + `.kb-list` patterns from the per-doctor AI 与知识 tab,
// adapted into a denser one-row-per-suggestion table to scale to 50+ items.
//
// Layout:
//   1. Header (title + count badge)
//   2. KPI strip — 平台采纳率 / 总建议数 / 已采纳 / 修改后采纳
//   3. Filter bar — 5 decision chips + doctor dropdown + search
//   4. Activity rows — section icon | patient + doctor | content preview |
//      decision badge | timestamp. Click → drill into that doctor.
//
// Data: /api/admin/suggestions/recent via useAiActivityList. The platform
// adoption rate comes from /api/admin/overview hero.ai_acceptance (a single
// extra fetch on mount; reuses the DashboardPage pattern). Counts in the KPI
// strip refresh as the user changes filters: we issue a per-decision count
// query for each tab using the same hook, with limit=1 (we only need .total).

import { useEffect, useMemo, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";
import useAiActivityList from "./useAiActivityList";

const PAGE_SIZE = 50;
const ADMIN_TOKEN_KEY = "adminToken";

const FILTER_CHIPS = [
  { key: "all",     label: "全部" },
  { key: "accept",  label: "已采纳" },
  { key: "edit",    label: "修改后采纳" },
  { key: "reject",  label: "拒绝" },
  { key: "pending", label: "待处理" },
];

// Section → Material Symbols icon (per task brief).
const SECTION_ICON = {
  workup:        "troubleshoot",
  differential:  "psychology",
  treatment:     "medication",
  followup:      "event_repeat",
};
const DEFAULT_SECTION_ICON = "network_intelligence";

// Decision → badge colors (matches DecisionCard st-* tokens).
const BADGE_BY_DECISION = {
  confirmed: { background: COLOR.brandTint,   color: COLOR.brand,   label: "医生确认" },
  edited:    { background: COLOR.infoTint,    color: COLOR.info,    label: "修改后采纳" },
  rejected:  { background: COLOR.dangerTint,  color: COLOR.danger,  label: "医生拒绝" },
  generated: { background: COLOR.warningTint, color: COLOR.warning, label: "待处理" },
};
function badgeFor(decision) {
  if (!decision) return BADGE_BY_DECISION.generated;
  return BADGE_BY_DECISION[decision] || BADGE_BY_DECISION.generated;
}

const SECTION_LABEL = {
  workup: "辅助检查",
  differential: "鉴别诊断",
  treatment: "治疗方案",
  followup: "随访建议",
};


// ─── small helpers ────────────────────────────────────────────────────────

function formatRelative(ts) {
  // ts is "YYYY-MM-DD HH:MM:SS" UTC string from filters._fmt_ts.
  if (!ts) return "—";
  const d = new Date(`${ts.replace(" ", "T")}Z`);
  if (Number.isNaN(d.getTime())) return ts;
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `今天 ${hh}:${mm}`;
  if (isYesterday) return `昨天 ${hh}:${mm}`;
  const yr = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yr}-${mo}-${dd}`;
}

// Both helpers PRESERVE the existing section= param so the sidebar
// stays highlighted on 知识 & AI when the operator drills in. v3/index.jsx
// resolves patient= / doctor= for the rendered surface but reads section=
// for the sidebar highlight.

function navigateToDoctor(doctorId) {
  if (!doctorId || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.delete("patient");
  params.set("v", "3");
  params.set("doctor", doctorId);
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

// Drill into the patient detail surface — the suggestion lives inline
// under its parent record there, alongside the full clinical context
// (records, messages, tasks). Falls back to the doctor view when the
// row has no patient_id (older suggestions before the field was added).
function navigateToSuggestion({ patientId, doctorId }) {
  if (typeof window === "undefined") return;
  if (patientId == null) {
    navigateToDoctor(doctorId);
    return;
  }
  const params = new URLSearchParams(window.location.search);
  params.set("v", "3");
  if (doctorId) params.set("doctor", doctorId);
  params.set("patient", String(patientId));
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}


// ─── doctor-list fetch (small, local) ─────────────────────────────────────

function useDoctorOptions() {
  const [opts, setOpts] = useState([]);
  useEffect(() => {
    let cancelled = false;
    const token =
      localStorage.getItem(ADMIN_TOKEN_KEY) ||
      (import.meta.env.DEV ? "dev" : "");
    fetch("/api/admin/doctors", {
      headers: token ? { "X-Admin-Token": token } : {},
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((body) => {
        if (cancelled) return;
        const list = Array.isArray(body.items) ? body.items : [];
        setOpts(
          list.map((d) => ({
            id: d.doctor_id,
            name: d.name || "(未命名医生)",
          })),
        );
      })
      .catch(() => {
        if (cancelled) return;
        setOpts([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return opts;
}


// ─── platform-wide acceptance rate (from /api/admin/overview) ─────────────

function usePlatformAcceptance() {
  const [rate, setRate] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const token =
      localStorage.getItem(ADMIN_TOKEN_KEY) ||
      (import.meta.env.DEV ? "dev" : "");
    fetch("/api/admin/overview", {
      headers: token ? { "X-Admin-Token": token } : {},
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((body) => {
        if (cancelled) return;
        const r = body?.hero?.ai_acceptance?.rate;
        setRate(Number.isFinite(r) ? r : null);
      })
      .catch(() => {
        if (cancelled) return;
        setRate(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return rate;
}


// ─── small per-decision count (limit=1, only need .total) ─────────────────

function useDecisionCount({ filter, doctorId, q }) {
  const { total } = useAiActivityList({ limit: 1, offset: 0, filter, doctorId, q });
  return total;
}


// ─── sub-components ───────────────────────────────────────────────────────

function Chip({ active, onClick, label, count }) {
  return (
    <span
      onClick={onClick}
      style={{
        fontSize: 12.5,
        height: 28,
        padding: "0 11px",
        borderRadius: RADIUS.pill,
        border: `1px solid ${active ? COLOR.text2 : COLOR.borderDefault}`,
        background: active ? COLOR.bgCanvas : COLOR.bgCard,
        color: COLOR.text1,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        userSelect: "none",
      }}
    >
      {label}
      {count != null && (
        <span
          style={{
            color: active ? COLOR.text2 : COLOR.text3,
            fontVariantNumeric: "tabular-nums",
            fontFamily: FONT_STACK.mono,
            fontSize: 11,
            marginLeft: 2,
          }}
        >
          {count}
        </span>
      )}
    </span>
  );
}

function FilterBar({
  filter,
  onFilterChange,
  doctorId,
  onDoctorChange,
  doctorOptions,
  q,
  onQChange,
  counts,
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "10px 14px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCardAlt,
        flexWrap: "wrap",
      }}
    >
      {FILTER_CHIPS.map((chip) => (
        <Chip
          key={chip.key}
          active={filter === chip.key}
          onClick={() => onFilterChange(chip.key)}
          label={chip.label}
          count={counts?.[chip.key]}
        />
      ))}
      <span style={{ flex: 1 }} />

      <select
        value={doctorId || ""}
        onChange={(e) => onDoctorChange(e.target.value || null)}
        style={{
          height: 28,
          fontSize: 12.5,
          padding: "0 8px",
          borderRadius: RADIUS.sm,
          border: `1px solid ${COLOR.borderDefault}`,
          background: COLOR.bgCard,
          color: COLOR.text1,
          cursor: "pointer",
        }}
      >
        <option value="">所有医生</option>
        {doctorOptions.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>

      <div
        style={{
          height: 28,
          padding: "0 8px",
          borderRadius: RADIUS.sm,
          border: `1px solid ${COLOR.borderDefault}`,
          background: COLOR.bgCard,
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 14, color: COLOR.text3 }}
        >
          search
        </span>
        <input
          type="text"
          value={q}
          placeholder="搜索患者或建议内容"
          onChange={(e) => onQChange(e.target.value)}
          style={{
            border: "none",
            outline: "none",
            background: "transparent",
            fontSize: 12.5,
            color: COLOR.text1,
            width: 180,
          }}
        />
      </div>
    </div>
  );
}

function DecisionBadge({ decision }) {
  const v = badgeFor(decision);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 22,
        padding: "0 10px",
        borderRadius: RADIUS.pill,
        background: v.background,
        color: v.color,
        fontSize: 11.5,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {v.label}
    </span>
  );
}

function SectionIcon({ section }) {
  const icon = SECTION_ICON[section] || DEFAULT_SECTION_ICON;
  return (
    <div
      style={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        background: COLOR.infoTint,
        color: COLOR.info,
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
        {icon}
      </span>
    </div>
  );
}

function ActivityTable({ items }) {
  const TH = {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: COLOR.text3,
    fontWeight: 600,
    textAlign: "left",
    padding: "10px 12px",
    borderBottom: `1px solid ${COLOR.borderSubtle}`,
    background: COLOR.bgCardAlt,
    position: "sticky",
    top: 0,
    zIndex: 1,
  };
  const TD = {
    padding: "12px",
    borderBottom: `1px solid ${COLOR.borderSubtle}`,
    fontSize: FONT.body,
    color: COLOR.text1,
    verticalAlign: "middle",
  };

  return (
    <div style={{ maxHeight: 640, overflow: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "separate",
          borderSpacing: 0,
          tableLayout: "fixed",
        }}
      >
        <thead>
          <tr>
            <th style={{ ...TH, width: 44 }} aria-label="模块"></th>
            <th style={{ ...TH, width: 200 }}>患者 / 主治</th>
            <th style={TH}>建议内容</th>
            <th style={{ ...TH, width: 120 }}>结论</th>
            <th style={{ ...TH, width: 120 }}>时间</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s, idx) => (
            <tr
              key={`${s.id}-${idx}`}
              onClick={() =>
                navigateToSuggestion({
                  patientId: s.patient_id,
                  doctorId: s.doctor_id,
                })
              }
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = COLOR.bgPage)
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "transparent")
              }
              title={s.patient_name ? `查看 ${s.patient_name} 详情` : undefined}
              style={{ cursor: "pointer", transition: "120ms" }}
            >
              <td style={TD}>
                <SectionIcon section={s.section} />
              </td>
              <td style={TD}>
                <div style={{ fontWeight: 600, color: COLOR.text1 }}>
                  {s.patient_name || "—"}
                </div>
                <div
                  style={{
                    fontSize: 11.5,
                    color: COLOR.info,
                    fontWeight: 500,
                    marginTop: 2,
                  }}
                >
                  {s.doctor_name}
                </div>
              </td>
              <td
                style={{
                  ...TD,
                  color: COLOR.text2,
                  fontSize: 13,
                  lineHeight: 1.5,
                }}
              >
                <div
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  {SECTION_LABEL[s.section] && (
                    <span
                      style={{
                        fontSize: 10.5,
                        textTransform: "uppercase",
                        letterSpacing: "0.1em",
                        color: COLOR.text3,
                        fontWeight: 600,
                        flexShrink: 0,
                      }}
                    >
                      {SECTION_LABEL[s.section]}
                    </span>
                  )}
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    {s.content_preview || "—"}
                  </span>
                  {s.cited_knowledge_count > 0 && (
                    <span
                      style={{
                        fontSize: 10.5,
                        color: COLOR.info,
                        background: COLOR.infoTint,
                        padding: "2px 7px",
                        borderRadius: RADIUS.pill,
                        fontWeight: 600,
                        flexShrink: 0,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 3,
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: 12 }}
                      >
                        menu_book
                      </span>
                      {s.cited_knowledge_count}
                    </span>
                  )}
                </div>
              </td>
              <td style={TD}>
                <DecisionBadge decision={s.decision} />
              </td>
              <td
                style={{
                  ...TD,
                  color: COLOR.text2,
                  fontFamily: FONT_STACK.mono,
                  fontVariantNumeric: "tabular-nums",
                  fontSize: 12.5,
                }}
              >
                {formatRelative(s.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pager({ total, offset, limit, onPrev, onNext }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  const btn = (enabled) => ({
    height: 30,
    padding: "0 12px",
    borderRadius: RADIUS.sm,
    border: `1px solid ${COLOR.borderDefault}`,
    background: enabled ? COLOR.bgCard : COLOR.bgCardAlt,
    color: enabled ? COLOR.text1 : COLOR.text3,
    fontSize: 12.5,
    cursor: enabled ? "pointer" : "not-allowed",
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 10,
        padding: "10px 14px",
        borderTop: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCardAlt,
      }}
    >
      <span
        style={{
          fontSize: 12,
          color: COLOR.text2,
          fontFamily: FONT_STACK.mono,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        第 {page} / {totalPages} 页 · 共 {total} 条
      </span>
      <button
        type="button"
        onClick={canPrev ? onPrev : undefined}
        disabled={!canPrev}
        style={btn(canPrev)}
      >
        上一页
      </button>
      <button
        type="button"
        onClick={canNext ? onNext : undefined}
        disabled={!canNext}
        style={btn(canNext)}
      >
        下一页
      </button>
    </div>
  );
}

function KpiCell({ label, value, unit, valueColor, hint, isLast }) {
  return (
    <div
      style={{
        padding: "14px 16px",
        borderRight: isLast ? "none" : `1px solid ${COLOR.borderSubtle}`,
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div
        style={{
          fontSize: FONT.xs,
          textTransform: "uppercase",
          letterSpacing: "0.12em",
          color: COLOR.text3,
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 28,
          lineHeight: "32px",
          fontWeight: 600,
          letterSpacing: "-0.02em",
          color: valueColor || COLOR.text1,
          fontVariantNumeric: "tabular-nums",
          fontFamily: FONT_STACK.mono,
          display: "flex",
          alignItems: "baseline",
          gap: 4,
        }}
      >
        {value}
        {unit && (
          <span
            style={{
              fontSize: FONT.base,
              fontWeight: 400,
              color: valueColor || COLOR.text2,
              letterSpacing: 0,
              fontFamily: FONT_STACK.sans,
            }}
          >
            {unit}
          </span>
        )}
      </div>
      {hint && (
        <div
          style={{
            fontSize: 11.5,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

function KpiStrip({ acceptanceRate, totalCount, acceptCount, editCount }) {
  const adoptionPct =
    acceptanceRate != null && Number.isFinite(acceptanceRate)
      ? Math.round(acceptanceRate * 100)
      : null;
  const cells = [
    {
      label: "平台采纳率",
      value: adoptionPct != null ? adoptionPct : "—",
      unit: adoptionPct != null ? "%" : null,
      valueColor: adoptionPct != null ? COLOR.info : COLOR.text3,
      hint: "已采纳 + 修改后采纳",
    },
    {
      label: "总建议数",
      value: totalCount ?? "—",
      hint: "全部 AI 建议",
    },
    {
      label: "已采纳",
      value: acceptCount ?? "—",
      valueColor: acceptCount > 0 ? COLOR.brand : COLOR.text1,
    },
    {
      label: "修改后采纳",
      value: editCount ?? "—",
      valueColor: editCount > 0 ? COLOR.info : COLOR.text1,
    },
  ];
  return (
    <section
      data-v3="ai-kpi"
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        overflow: "hidden",
        boxShadow: SHADOW.s1,
      }}
    >
      {cells.map((c, i) => (
        <KpiCell key={c.label} {...c} isLast={i === cells.length - 1} />
      ))}
    </section>
  );
}


// ─── main page component ─────────────────────────────────────────────────

export default function AiActivityPage() {
  const [filter, setFilter] = useState("all");
  const [doctorId, setDoctorId] = useState(null);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  // Reset to page 1 on filter / query / doctor change.
  useEffect(() => setOffset(0), [filter, doctorId, q]);

  const doctorOptions = useDoctorOptions();
  const platformAcceptance = usePlatformAcceptance();
  const { items, total, loading, error, refetch } = useAiActivityList({
    limit: PAGE_SIZE,
    offset,
    filter,
    doctorId,
    q,
  });

  // Per-tab counts (limit=1, only `.total`). Each bucket is a one-row hit so
  // the cost is small. Counts respect the doctor + q filters so the chip
  // numbers stay aligned with the visible list.
  const totalAll = useDecisionCount({ filter: "all", doctorId, q });
  const totalAccept = useDecisionCount({ filter: "accept", doctorId, q });
  const totalEdit = useDecisionCount({ filter: "edit", doctorId, q });
  const totalReject = useDecisionCount({ filter: "reject", doctorId, q });
  const totalPending = useDecisionCount({ filter: "pending", doctorId, q });

  const counts = {
    all: totalAll,
    accept: totalAccept,
    edit: totalEdit,
    reject: totalReject,
    pending: totalPending,
  };

  const headerCount = useMemo(() => {
    if (loading && total === 0) return "…";
    return `共 ${total} 条建议`;
  }, [loading, total]);

  return (
    <div style={{ paddingTop: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          padding: "0 4px",
        }}
      >
        <div
          style={{
            fontSize: FONT.xl,
            fontWeight: 600,
            color: COLOR.text1,
            letterSpacing: "-0.01em",
          }}
        >
          知识 & AI
        </div>
        <div
          style={{
            fontSize: FONT.sm,
            color: COLOR.text2,
            fontFamily: FONT_STACK.mono,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {headerCount}
        </div>
      </div>

      {/* KPI strip removed per codex 2026-04-24 review — duplicates the
          AI 采纳率 number on the dashboard, and chip counts already convey
          the same info. The KpiStrip + KpiCell components are kept in this
          file for now in case we want a different per-page summary later. */}

      {/* Panel */}
      <section
        style={{
          background: COLOR.bgCard,
          border: `1px solid ${COLOR.borderSubtle}`,
          borderRadius: RADIUS.lg,
          boxShadow: SHADOW.s1,
          overflow: "hidden",
        }}
      >
        <FilterBar
          filter={filter}
          onFilterChange={setFilter}
          doctorId={doctorId}
          onDoctorChange={setDoctorId}
          doctorOptions={doctorOptions}
          q={q}
          onQChange={setQ}
          counts={counts}
        />

        {loading && items.length === 0 && (
          <div style={{ padding: "12px 14px" }}>
            <SectionLoading title="正在加载 AI 建议…" />
          </div>
        )}

        {!loading && error && (
          <div style={{ padding: "12px 14px" }}>
            <SectionError message={error} onRetry={refetch} />
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div style={{ padding: "12px 14px" }}>
            <EmptyState
              icon="network_intelligence"
              title="暂无匹配的 AI 建议"
              desc="试试切换决策筛选条件，或清空搜索词。"
            />
          </div>
        )}

        {!error && items.length > 0 && (
          <>
            <ActivityTable items={items} />
            <Pager
              total={total}
              offset={offset}
              limit={PAGE_SIZE}
              onPrev={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              onNext={() => setOffset((o) => o + PAGE_SIZE)}
            />
          </>
        )}
      </section>
    </div>
  );
}
