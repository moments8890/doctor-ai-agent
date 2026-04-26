// ChatCenterPage — admin v3 cross-doctor 沟通中心 (communication inbox).
//
// One row per (patient, doctor) thread, ordered by last message DESC.
// Click a row → expands inline below it with the WeChat-style chat
// history (mirrors the doctor-detail 沟通 tab style: filled brand
// bubble for outbound, light card for inbound, day-tag separators,
// in-bubble HH:MM stamp). Multiple rows can be expanded at once.
// Closing collapses the body but keeps the row anchored.
//
// Visual reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.chat-list`, `.cl-row`, `.cl-search`.

import { Fragment, useEffect, useMemo, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";
import useChatCenterList from "./useChatCenterList";

const PAGE_SIZE = 50;
const ADMIN_TOKEN_KEY = "adminToken";

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


// ─── chat-bubble helpers (WeChat style) ───────────────────────────────────

function parseTs(ts) {
  if (!ts) return null;
  const d = new Date(`${String(ts).replace(" ", "T")}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function fmtStamp(d) {
  if (!d) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtDayTag(d) {
  if (!d) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  if (sameDay) return `今天 · ${m} 月 ${dd} 日`;
  if (isYesterday) return `昨天 · ${m} 月 ${dd} 日`;
  return `${m} 月 ${dd} 日 · ${weekdays[d.getDay()]}`;
}

function dayKey(d) {
  return d ? d.toDateString() : "";
}

const DRAFT_STATUS_LABEL = {
  generated: "草稿 · 待发送",
  edited: "草稿 · 已编辑",
  dismissed: "草稿 · 已忽略",
  stale: "草稿 · 已超时",
};

function buildBubbleItems(messages, drafts) {
  const sent = (messages || [])
    .filter((m) => m && (m.direction === "inbound" || m.direction === "outbound"))
    .map((m) => ({
      kind: "bubble",
      role: m.direction === "outbound" ? "doctor" : "patient",
      // Surfaces the AI-vs-doctor distinction on outbound bubbles so an
      // auditor can tell which replies were drafted by the AI on the
      // doctor's behalf vs. typed by the doctor. null for legacy rows
      // — those render as plain doctor bubbles (no pill).
      source: m.source || null,
      text: m.content || "",
      ts: parseTs(m.created_at),
      _id: `m-${m.id}`,
    }));

  // Unsent drafts surface as ghost bubbles on the doctor (right) side so
  // the auditor can see what AI proposed without reading the chat as if
  // the patient saw it. Use edited_text when the doctor edited but
  // never sent; fall back to the original AI draft.
  const drafted = (drafts || []).map((d) => ({
    kind: "draft",
    role: "doctor",
    status: d.status || "generated",
    text: (d.edited_text && d.edited_text.trim()) || d.draft_text || "",
    ts: parseTs(d.created_at),
    _id: `d-${d.id}`,
  }));

  const merged = [...sent, ...drafted].sort((a, b) => {
    if (!a.ts) return -1;
    if (!b.ts) return 1;
    return a.ts.getTime() - b.ts.getTime();
  });

  const out = [];
  let last = null;
  for (const b of merged) {
    const k = dayKey(b.ts);
    if (k !== last) {
      out.push({ kind: "day", label: fmtDayTag(b.ts), _key: `day-${k}` });
      last = k;
    }
    out.push({ ...b, stamp: fmtStamp(b.ts) });
  }
  return out;
}

function Bubble({ role, source, text, stamp }) {
  const isDoctor = role === "doctor";
  const isAi = isDoctor && source === "ai";
  return (
    <div
      style={{
        alignSelf: isDoctor ? "flex-end" : "flex-start",
        maxWidth: "70%",
        padding: "10px 14px",
        fontSize: 14,
        lineHeight: 1.55,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        background: isDoctor ? COLOR.brand : COLOR.bgCard,
        color: isDoctor ? "#fff" : COLOR.text1,
        border: isDoctor ? "none" : `1px solid ${COLOR.borderSubtle}`,
        borderRadius: isDoctor ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
      }}
    >
      <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{text}</div>
      <div
        style={{
          alignSelf: "flex-end",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {isAi && (
          <span
            title="AI 起草，已发送给患者"
            style={{
              fontFamily: FONT_STACK.mono,
              fontSize: 9.5,
              fontWeight: 600,
              letterSpacing: "0.08em",
              padding: "1px 6px",
              borderRadius: 999,
              background: "rgba(255,255,255,0.22)",
              color: "rgba(255,255,255,0.95)",
            }}
          >
            AI
          </span>
        )}
        {stamp && (
          <span
            style={{
              fontFamily: FONT_STACK.mono,
              fontSize: 10.5,
              color: isDoctor ? "rgba(255,255,255,0.75)" : COLOR.text3,
            }}
          >
            {stamp}
          </span>
        )}
      </div>
    </div>
  );
}

// Ghost bubble for unsent AI drafts. Right-aligned (doctor side), dashed
// border, muted background, and a "草稿 · {状态}" pill so an auditor can
// see what AI proposed but the doctor never sent. Status labels:
//   generated → 待发送, edited → 已编辑 (still unsent), dismissed → 已忽略,
//   stale → 已超时.
function DraftBubble({ status, text, stamp }) {
  const label = DRAFT_STATUS_LABEL[status] || "草稿";
  const isDismissed = status === "dismissed" || status === "stale";
  return (
    <div
      title={
        status === "dismissed"
          ? "AI 起草，医生忽略，未发送"
          : status === "stale"
          ? "AI 起草，超过有效期未发送"
          : status === "edited"
          ? "AI 起草，医生已编辑但尚未发送"
          : "AI 起草，待医生审核发送"
      }
      style={{
        alignSelf: "flex-end",
        maxWidth: "70%",
        padding: "10px 14px",
        fontSize: 14,
        lineHeight: 1.55,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        background: COLOR.bgCardAlt || COLOR.bgPage,
        color: isDismissed ? COLOR.text3 : COLOR.text2,
        border: `1px dashed ${COLOR.borderDefault}`,
        borderRadius: "12px 12px 4px 12px",
        opacity: isDismissed ? 0.75 : 1,
      }}
    >
      <div
        style={{
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          textDecoration: isDismissed ? "line-through" : "none",
        }}
      >
        {text || "（空草稿）"}
      </div>
      <div
        style={{
          alignSelf: "flex-end",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            fontFamily: FONT_STACK.mono,
            fontSize: 9.5,
            fontWeight: 600,
            letterSpacing: "0.04em",
            padding: "1px 6px",
            borderRadius: 999,
            background: COLOR.bgCard,
            color: COLOR.text2,
            border: `1px solid ${COLOR.borderSubtle}`,
          }}
        >
          {label}
        </span>
        {stamp && (
          <span
            style={{
              fontFamily: FONT_STACK.mono,
              fontSize: 10.5,
              color: COLOR.text3,
            }}
          >
            {stamp}
          </span>
        )}
      </div>
    </div>
  );
}

function DayTag({ label }) {
  return (
    <span
      style={{
        alignSelf: "center",
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: COLOR.text3,
        background: COLOR.bgCard,
        padding: "3px 12px",
        borderRadius: 999,
        border: `1px solid ${COLOR.borderSubtle}`,
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
}


// ─── per-row thread body (fetches its own messages on mount) ──────────────

function ThreadBody({ patientId, doctorId, doctorName }) {
  const [data, setData] = useState({ items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (patientId == null || !doctorId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const url = `/api/admin/messages/thread?patient_id=${encodeURIComponent(patientId)}&doctor_id=${encodeURIComponent(doctorId)}`;
    fetchAdminJson(url)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId, doctorId]);

  const items = useMemo(
    () => buildBubbleItems(data.items, data.drafts),
    [data.items, data.drafts],
  );

  return (
    <div
      style={{
        background: COLOR.bgCardAlt || COLOR.bgPage,
        borderTop: `1px solid ${COLOR.borderSubtle}`,
        padding: "18px 22px",
      }}
    >
      <div
        style={{
          maxHeight: 480,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {loading && (
          <div
            style={{
              alignSelf: "center",
              color: COLOR.text3,
              fontSize: FONT.sm,
              padding: "16px 0",
            }}
          >
            正在加载会话…
          </div>
        )}
        {!loading && error && (
          <div
            style={{
              alignSelf: "center",
              color: COLOR.danger,
              fontSize: FONT.sm,
              padding: "16px 0",
            }}
          >
            加载失败：{error}
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div
            style={{
              alignSelf: "center",
              color: COLOR.text3,
              fontSize: FONT.sm,
              padding: "16px 0",
            }}
          >
            暂无消息
          </div>
        )}
        {!loading && !error &&
          items.map((it, idx) => {
            if (it.kind === "day") return <DayTag key={it._key || idx} label={it.label} />;
            if (it.kind === "draft") {
              return (
                <DraftBubble
                  key={it._id ?? idx}
                  status={it.status}
                  text={it.text}
                  stamp={it.stamp}
                />
              );
            }
            return (
              <Bubble
                key={it._id ?? idx}
                role={it.role}
                source={it.source}
                text={it.text}
                stamp={it.stamp}
              />
            );
          })}
      </div>
      <div
        style={{
          marginTop: 10,
          paddingTop: 10,
          borderTop: `1px solid ${COLOR.borderSubtle}`,
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            navigateToDoctor(doctorId);
          }}
          style={{
            border: `1px solid ${COLOR.borderDefault}`,
            background: COLOR.bgCard,
            color: COLOR.text1,
            borderRadius: RADIUS.sm,
            padding: "6px 14px",
            fontSize: FONT.sm,
            cursor: "pointer",
          }}
          title={doctorName ? `查看 ${doctorName} 的详情` : undefined}
        >
          查看医生详情 →
        </button>
      </div>
    </div>
  );
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

function ChatRow({ entry, isOpen, onClick }) {
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
      onMouseEnter={(e) => {
        if (!isOpen) e.currentTarget.style.background = COLOR.bgCard;
      }}
      onMouseLeave={(e) => {
        if (!isOpen) e.currentTarget.style.background = "transparent";
      }}
      title={isOpen ? "点击收起" : "点击展开会话"}
      style={{
        padding: "12px 14px",
        display: "grid",
        gridTemplateColumns: "20px 36px 1fr auto",
        gap: 12,
        alignItems: "center",
        cursor: "pointer",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        transition: "120ms",
        background: isOpen ? COLOR.bgPage : "transparent",
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: 18,
          color: COLOR.text3,
          transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
          transition: "transform 140ms",
          display: "inline-block",
        }}
      >
        chevron_right
      </span>
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
            {entry.doctor_name || "(未命名医生)"}
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
  // Set of expanded thread keys ("doctorId-patientId"). Multiple rows can
  // be open at once for cross-thread comparison.
  const [expandedKeys, setExpandedKeys] = useState(() => new Set());

  // Reset to page 1 + collapse on filter / query change.
  useEffect(() => {
    setOffset(0);
    setExpandedKeys(new Set());
  }, [filter, q]);

  // Collapse all when paging — out-of-view rows shouldn't keep state.
  useEffect(() => {
    setExpandedKeys(new Set());
  }, [offset]);

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

  const toggle = (key) =>
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

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
          <div>
            {items.map((entry) => {
              const key = `${entry.doctor_id}-${entry.patient_id}`;
              const isOpen = expandedKeys.has(key);
              return (
                <Fragment key={key}>
                  <ChatRow
                    entry={entry}
                    isOpen={isOpen}
                    onClick={() => toggle(key)}
                  />
                  {isOpen && (
                    <ThreadBody
                      patientId={entry.patient_id}
                      doctorId={entry.doctor_id}
                      doctorName={entry.doctor_name}
                    />
                  )}
                </Fragment>
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
