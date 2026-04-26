// AllPatientsPage — admin v3 全体患者 cross-doctor list.
//
// Layout: header (title + count) → filter bar (chips + doctor dropdown +
// search) → table panel. Click a row to drill into that patient's doctor
// page (?v=3&doctor=<id>). Read-only — partner doctors land here from the
// 概览 → 全体患者 sidebar item.
//
// Data: /api/admin/patients via usePatientList; doctor dropdown is fed from
// /api/admin/doctors (same auth, fetched once on mount).

import { useEffect, useMemo, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";
import usePatientList from "./usePatientList";

const PAGE_SIZE = 100;
const ADMIN_TOKEN_KEY = "adminToken";

// 高危 / 未达标 chips intentionally OMITTED from v1 — the backend has no
// per-patient risk field yet, so those filters would always return empty
// (codex review 2026-04-24 flagged them as "fake affordances"). Re-add
// them when /api/admin/patients exposes a populated `risk` field.
const FILTER_CHIPS = [
  { key: "all",    label: "全部" },
  { key: "silent", label: "7天无沟通" },
  { key: "postop", label: "术后随访" },
];


// ─── small utility helpers ────────────────────────────────────────────────

function formatRelative(ts) {
  // ts is a "YYYY-MM-DD HH:MM:SS" string (UTC) — see filters._fmt_ts.
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
  // else: short date
  const yr = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yr}-${mo}-${dd}`;
}

function formatGender(g) {
  if (g === "male" || g === "M") return "男";
  if (g === "female" || g === "F") return "女";
  return g || "—";
}

function navigateToDoctor(doctorId) {
  if (!doctorId || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.delete("section");
  params.delete("patient");
  params.set("v", "3");
  params.set("doctor", doctorId);
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

// Drill straight into the patient detail surface, preserving doctor context
// so the topbar back arrow returns to that doctor's view (then back again
// returns to this list via browser history). The cross-doctor 全体患者
// table is the natural entry point for "show me everything about this
// patient" — the doctor cell on the same row is wired separately for
// "I want to see the doctor instead".
function navigateToPatient(patientId, doctorId) {
  if (patientId == null || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.delete("section");
  params.set("v", "3");
  if (doctorId) params.set("doctor", doctorId);
  params.set("patient", String(patientId));
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}


// ─── doctor-list fetch (small, local, no separate hook needed) ────────────

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
          }))
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


// ─── sub-components ───────────────────────────────────────────────────────

function Chip({ active, onClick, label, icon, iconColor, count }) {
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
      {icon && (
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 14, color: iconColor || COLOR.text2 }}
        >
          {icon}
        </span>
      )}
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
          icon={chip.icon}
          iconColor={chip.iconColor}
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
          placeholder="搜索患者姓名"
          onChange={(e) => onQChange(e.target.value)}
          style={{
            border: "none",
            outline: "none",
            background: "transparent",
            fontSize: 12.5,
            color: COLOR.text1,
            width: 140,
          }}
        />
      </div>
    </div>
  );
}

function StatusPill({ risk }) {
  // Only render a pill when the backend gives us a populated risk field.
  // Codex 2026-04-24 critique: showing "稳定" for any patient with messages
  // is dishonest — "has messages" ≠ "stable". When risk lands on the API,
  // re-enable danger / warn pills here.
  if (risk === "danger") {
    return <Pill color={COLOR.danger} bg={COLOR.dangerTint} label="高危" />;
  }
  if (risk === "warn") {
    return <Pill color={COLOR.warning} bg={COLOR.warningTint} label="未达标" />;
  }
  return <span style={{ color: COLOR.text3 }}>—</span>;
}

function Pill({ color, bg, label }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 20,
        padding: "0 8px",
        borderRadius: RADIUS.pill,
        background: bg,
        color,
        fontSize: 11,
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
}

function PatientTable({ items }) {
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
    padding: "10px 12px",
    borderBottom: `1px solid ${COLOR.borderSubtle}`,
    fontSize: FONT.body,
    color: COLOR.text1,
    verticalAlign: "middle",
  };
  const NUM_TD = {
    ...TD,
    fontFamily: FONT_STACK.mono,
    fontVariantNumeric: "tabular-nums",
    color: COLOR.text2,
    textAlign: "right",
    width: 88,
  };

  return (
    <div style={{ maxHeight: 640, overflow: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "separate",
          borderSpacing: 0,
        }}
      >
        <thead>
          <tr>
            <th style={TH}>患者</th>
            <th style={TH}>主治医生</th>
            <th style={{ ...TH, width: 64 }}>性别</th>
            <th style={{ ...TH, width: 80 }}>出生年</th>
            <th style={{ ...TH, width: 140 }}>最后消息</th>
            <th style={{ ...TH, textAlign: "right", width: 96 }}>30d 消息</th>
            <th style={{ ...TH, textAlign: "right", width: 80 }}>病历数</th>
            <th style={{ ...TH, width: 80 }}>状态</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, idx) => {
            const hasRecent = Boolean(p.last_message_at);
            return (
              <tr
                key={`${p.doctor_id}-${p.id}-${idx}`}
                onClick={() => navigateToPatient(p.id, p.doctor_id)}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = COLOR.bgPage)
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
                title={`查看 ${p.name} 详情`}
                style={{ cursor: "pointer", transition: "120ms" }}
              >
                <td style={{ ...TD, fontWeight: 600 }}>{p.name}</td>
                <td
                  onClick={(e) => {
                    e.stopPropagation();
                    navigateToDoctor(p.doctor_id);
                  }}
                  title={`查看 ${p.doctor_name} 的详情`}
                  style={{
                    ...TD,
                    color: COLOR.info,
                    fontWeight: 500,
                    cursor: "pointer",
                    textDecoration: "underline dotted",
                    textUnderlineOffset: 3,
                  }}
                >
                  {p.doctor_name}
                </td>
                <td style={{ ...TD, color: COLOR.text2 }}>
                  {formatGender(p.gender)}
                </td>
                <td
                  style={{
                    ...TD,
                    color: COLOR.text2,
                    fontFamily: FONT_STACK.mono,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {p.year_of_birth || "—"}
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
                  {formatRelative(p.last_message_at)}
                </td>
                <td style={NUM_TD}>{p.message_count_30d ?? 0}</td>
                <td style={NUM_TD}>{p.record_count ?? 0}</td>
                <td style={TD}>
                  <StatusPill risk={p.risk} />
                </td>
              </tr>
            );
          })}
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
        第 {page} / {totalPages} 页 · 共 {total} 位
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


// ─── main page component ─────────────────────────────────────────────────

export default function AllPatientsPage() {
  const [filter, setFilter] = useState("all");
  const [doctorId, setDoctorId] = useState(null);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  // Reset to page 1 on filter / query / doctor change.
  useEffect(() => setOffset(0), [filter, doctorId, q]);

  const doctorOptions = useDoctorOptions();
  const { items, total, loading, error, refetch } = usePatientList({
    limit: PAGE_SIZE,
    offset,
    filter,
    doctorId,
    q,
  });

  const headerCount = useMemo(() => {
    if (loading) return "…";
    return `共 ${total} 位`;
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
          全体患者
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
        />

        {loading && (
          <div style={{ padding: "12px 14px" }}>
            <SectionLoading title="正在加载患者…" />
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
              icon="inbox"
              title="暂无匹配的患者"
              desc="试试切换筛选条件，或清空搜索词。"
            />
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <>
            <PatientTable items={items} />
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
