// ChatList — left rail of the 沟通 tab. Renders a search box on top and a
// patient-grouped feed of recent chats below. Active row gets the 2px brand
// left rail + brand-fill avatar.
//
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.chat-list`, `.cl-search`, `.cl-row`, `.cl-row.active`, `.cl-av`,
//   `.cl-name`, `.cl-name .risk`, `.cl-snip`, `.cl-time`, `.unread`
//
// Data: groups `messages.items[]` by `patient_id` and keeps the latest message
// as snippet/timestamp. The search input is style-only for now (Task 2.4
// scope) — actual filtering lives in a later task.
//
// Props:
//   messages:  Array<{ id, patient_id, patient_name, content, direction,
//                      source, created_at }>
//   activeId:  string | number | null
//   onSelect:  (patientId) => void
//   patientsById?: Record<patientId, { risk?: "danger"|"warn", unread?: boolean }>
//                  Optional risk + unread flags from the related patients
//                  block. Until /related exposes per-thread unread counts,
//                  callers may pass undefined and we render no dot.

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

function groupByPatient(messages) {
  if (!Array.isArray(messages)) return [];
  const byId = new Map();
  // messages.items is already ordered by created_at DESC server-side, so the
  // first time we see a patient_id we have its newest message.
  for (const m of messages) {
    if (!m || m.patient_id == null) continue;
    const key = String(m.patient_id);
    if (byId.has(key)) continue;
    byId.set(key, m);
  }
  return Array.from(byId.values());
}

function formatTimestamp(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `${hh}:${mm}`;
  if (isYesterday) return `昨 ${hh}:${mm}`;
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${m}·${dd}`;
}

function snippetText(m) {
  const raw = (m?.content || "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  // Direction marker: outbound replies look more natural with a leading
  // "我:" so a glance distinguishes who said what last.
  if (m.direction === "outbound") return `我：${raw}`;
  return raw;
}

function RiskPill({ risk }) {
  if (risk !== "danger" && risk !== "warn") return null;
  const high = risk === "danger";
  return (
    <span
      style={{
        fontSize: 9.5,
        padding: "0 5px",
        borderRadius: 999,
        fontWeight: 600,
        letterSpacing: "0.04em",
        background: high ? COLOR.dangerTint : COLOR.warningTint,
        color:      high ? COLOR.danger     : COLOR.warning,
      }}
    >
      {high ? "高危" : "未达标"}
    </span>
  );
}

function Row({ entry, active, onClick, patientMeta }) {
  const initial = (entry.patient_name || "?").trim().charAt(0) || "?";
  const time = formatTimestamp(entry.created_at);
  const risk = patientMeta?.risk;
  const unread = !!patientMeta?.unread;

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
      style={{
        padding: "10px 12px",
        display: "grid",
        gridTemplateColumns: "30px 1fr auto",
        gap: 10,
        alignItems: "center",
        cursor: "pointer",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        position: "relative",
        background: active ? COLOR.bgCard : "transparent",
      }}
    >
      {active && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 2,
            background: COLOR.brand,
          }}
        />
      )}
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          fontSize: 12,
          fontWeight: 600,
          background: active ? COLOR.brand : COLOR.bgCanvas,
          color:      active ? "#fff"      : COLOR.text2,
        }}
      >
        {initial}
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 6,
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
          <RiskPill risk={risk} />
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: COLOR.text2,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            marginTop: 1,
          }}
        >
          {snippetText(entry)}
        </div>
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          gap: 4,
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
            aria-hidden
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

function SearchBox() {
  // Style-only per Task 2.4. Wired in a later task.
  return (
    <div
      style={{
        padding: "10px 12px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: COLOR.bgCard,
          border: `1px solid ${COLOR.borderDefault}`,
          borderRadius: RADIUS.md,
          padding: "6px 10px",
          fontSize: 12.5,
          color: COLOR.text3,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
          search
        </span>
        <input
          placeholder="搜索患者…"
          style={{
            flex: 1,
            border: "none",
            outline: "none",
            background: "transparent",
            font: "inherit",
            color: COLOR.text1,
            minWidth: 0,
          }}
          // Non-functional in this task: prevent focus from showing browser
          // default validation chrome on empty submit while still allowing
          // typing (the input is harmless).
        />
      </div>
    </div>
  );
}

export default function ChatList({
  messages,
  activeId,
  onSelect,
  patientsById,
}) {
  const grouped = groupByPatient(messages);

  return (
    <div
      data-v3="chat-list"
      style={{
        borderRight: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCardAlt,
        overflowY: "auto",
        minHeight: 0,
      }}
    >
      <SearchBox />
      {grouped.length === 0 ? (
        <div
          style={{
            padding: "32px 16px",
            textAlign: "center",
            fontSize: FONT.sm,
            color: COLOR.text3,
          }}
        >
          暂无患者会话
        </div>
      ) : (
        grouped.map((entry) => {
          const key = String(entry.patient_id);
          const isActive = activeId != null && String(activeId) === key;
          return (
            <Row
              key={key}
              entry={entry}
              active={isActive}
              patientMeta={patientsById?.[key]}
              onClick={() => onSelect?.(entry.patient_id)}
            />
          );
        })
      )}
    </div>
  );
}
