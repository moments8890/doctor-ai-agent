// ChatCenterPage — admin v3 cross-doctor 沟通中心 (communication inbox).
//
// One row per (patient, doctor) thread, ordered by last message DESC.
// Click a row → navigate to that doctor's profile (?v=3&doctor=<id>) and
// let the user pick the 沟通 tab. We intentionally do NOT open a thread
// modal here — the inbox is a router, not a chat UI.
//
// Visual reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.chat-list`, `.cl-row`, `.cl-search` (adapted: each row also shows the
//   主治医生 name in info color so the cross-doctor scope is visible).

import { useEffect, useMemo, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";
import useChatCenterList from "./useChatCenterList";

const PAGE_SIZE = 50;

const FILTER_CHIPS = [
  { key: "all",    label: "全部",   icon: "forum" },
  { key: "unread", label: "未回复", icon: "mark_email_unread" },
  { key: "today",  label: "今日",   icon: "today" },
];


// ─── helpers ──────────────────────────────────────────────────────────────

function formatRelative(ts) {
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
  if (sameDay) return `${hh}:${mm}`;
  if (isYesterday) return `昨 ${hh}:${mm}`;
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${mo}·${dd}`;
}

function snippetText(msg) {
  const raw = (msg?.content || "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  if (msg.direction === "outbound") return `我：${raw}`;
  return raw;
}

function navigateToDoctor(doctorId) {
  if (!doctorId || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.delete("section");
  params.set("v", "3");
  params.set("doctor", doctorId);
  window.history.pushState({}, "", `?${params.toString()}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}


// ─── sub-components ───────────────────────────────────────────────────────

function Chip({ active, onClick, label, icon }) {
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
          style={{ fontSize: 14, color: active ? COLOR.text2 : COLOR.text3 }}
        >
          {icon}
        </span>
      )}
      {label}
    </span>
  );
}

function FilterBar({ filter, onFilterChange, q, onQChange }) {
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
        />
      ))}
      <span style={{ flex: 1 }} />

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
          placeholder="搜索患者或消息内容"
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

function ChatRow({ entry, onClick }) {
  const initial = (entry.patient_name || "?").trim().charAt(0) || "?";
  const time = formatRelative(entry?.last_message?.created_at);
  const unread = (entry.unread_count || 0) > 0;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = COLOR.bgCard)}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      style={{
        padding: "12px 14px",
        display: "grid",
        gridTemplateColumns: "36px 1fr auto",
        gap: 12,
        alignItems: "center",
        cursor: "pointer",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        transition: "120ms",
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          fontSize: 14,
          fontWeight: 600,
          background: COLOR.bgCanvas,
          color: COLOR.text2,
        }}
      >
        {initial}
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 8,
            color: COLOR.text1,
          }}
        >
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minWidth: 0,
            }}
          >
            {entry.patient_name || "未命名"}
          </span>
          <span
            style={{
              fontSize: 11,
              color: COLOR.info,
              fontWeight: 500,
              padding: "1px 6px",
              borderRadius: RADIUS.pill,
              background: COLOR.infoTint,
              flexShrink: 0,
            }}
          >
            {entry.doctor_name || entry.doctor_id}
          </span>
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: COLOR.text2,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            marginTop: 2,
          }}
        >
          {snippetText(entry.last_message)}
        </div>
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          gap: 6,
          minWidth: 44,
        }}
      >
        {time && (
          <span
            style={{
              fontSize: 11,
              color: COLOR.text3,
              fontFamily: FONT_STACK.mono,
            }}
          >
            {time}
          </span>
        )}
        {unread && (
          <span
            aria-label={`${entry.unread_count} 条未读`}
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: COLOR.brand,
            }}
          />
        )}
      </div>
    </div>
  );
}


// ─── main page component ──────────────────────────────────────────────────

export default function ChatCenterPage() {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  // Reset to page 1 on filter / query change.
  useEffect(() => setOffset(0), [filter, q]);

  const { items, total, loading, error, refetch } = useChatCenterList({
    limit: PAGE_SIZE,
    offset,
    filter,
    q,
  });

  const headerCount = useMemo(() => {
    if (loading) return "…";
    return `共 ${total} 条会话`;
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
          沟通中心
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
          q={q}
          onQChange={setQ}
        />

        {loading && (
          <div style={{ padding: "12px 14px" }}>
            <SectionLoading title="正在加载会话…" />
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
              icon="forum"
              title="暂无匹配的会话"
              desc="试试切换筛选条件，或清空搜索词。"
            />
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div style={{ maxHeight: 640, overflow: "auto" }}>
            {items.map((entry) => {
              const key = `${entry.doctor_id}-${entry.patient_id}`;
              return (
                <ChatRow
                  key={key}
                  entry={entry}
                  onClick={() => navigateToDoctor(entry.doctor_id)}
                />
              );
            })}
          </div>
        )}

        {!loading && !error && total > PAGE_SIZE && (
          <Pager
            total={total}
            offset={offset}
            limit={PAGE_SIZE}
            onPrev={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            onNext={() => setOffset((o) => o + PAGE_SIZE)}
          />
        )}
      </section>
    </div>
  );
}

// Pager mirrors AllPatientsPage's pager — backend supports offset/limit but
// the page was previously silently capping visibility at PAGE_SIZE.
// Codex 2026-04-24 critique flagged this as "silent visibility cap".
function Pager({ total, offset, limit, onPrev, onNext }) {
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
      <button type="button" onClick={canPrev ? onPrev : undefined} disabled={!canPrev} style={btn(canPrev)}>
        上一页
      </button>
      <button type="button" onClick={canNext ? onNext : undefined} disabled={!canNext} style={btn(canNext)}>
        下一页
      </button>
    </div>
  );
}
