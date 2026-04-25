// TimelinePanel — full-width activity feed below the row-3-1 grid in 总览.
// Mirrors the `<div class="timeline">` block in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~1473-1540).
//
// Data: /api/admin/activity returns a global 24h feed across all doctors.
// We filter client-side by doctor_id (the endpoint does not accept that
// query yet) and group remaining events by day. Day headers render like
// "今天 · 04 月 24 日" / "昨天 · 04 月 23 日" / "04 月 22 日".
//
// Row layout: 64px mono time / 22px tinted icon / detail text (ellipsis) /
// status chip. Dashed divider between rows.
//
// Icon-bg/fg color map locked to the spec:
//   msg → infoTint / info
//   ai → warningTint / warning
//   record → brandTint / brand
//   task → dangerTint / danger

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

const ICON_BG = {
  msg: COLOR.infoTint,
  ai: COLOR.warningTint,
  record: COLOR.brandTint,
  task: COLOR.dangerTint,
};
const ICON_FG = {
  msg: COLOR.info,
  ai: COLOR.warning,
  record: COLOR.brand,
  task: COLOR.danger,
};

// Map backend event_type → visual category (msg/ai/record/task) + icon glyph.
function classify(item) {
  const t = item.event_type || item.type || "";
  if (t === "ai_suggestion" || t === "ai") {
    return { kind: "ai", icon: "auto_awesome" };
  }
  if (t === "record") {
    return { kind: "record", icon: "description" };
  }
  if (t === "task") {
    return { kind: "task", icon: "event" };
  }
  if (t === "message" || t === "message_inbound" || t === "message_outbound") {
    return { kind: "msg", icon: "mail" };
  }
  // Fallback → treat as message.
  return { kind: "msg", icon: "mail" };
}

// Status chip class → bg/fg color tuple matching st-accept/st-edit/st-reject/
// st-pending/st-done from the mockup.
const STATUS_STYLES = {
  accept: { bg: COLOR.brandTint, fg: COLOR.brand },
  edit: { bg: COLOR.infoTint, fg: COLOR.info },
  reject: { bg: COLOR.dangerTint, fg: COLOR.danger },
  pending: { bg: COLOR.warningTint, fg: COLOR.warning },
  done: { bg: COLOR.brandTint, fg: COLOR.brand },
};

// Map raw status/decision strings to a (label, kind) pair.
function statusChip(item) {
  const raw = String(item.status || "").toLowerCase();
  const evt = item.event_type || item.type || "";
  if (evt === "ai_suggestion") {
    if (raw === "confirmed" || raw === "accept") {
      return { label: "医生确认", kind: "accept" };
    }
    if (raw === "edited") return { label: "医生修改后采纳", kind: "edit" };
    if (raw === "rejected") return { label: "拒绝", kind: "reject" };
    return { label: "待处理", kind: "pending" };
  }
  if (evt === "task") {
    if (raw === "completed" || raw === "done") {
      return { label: "已完成", kind: "done" };
    }
    if (raw === "cancelled") return { label: "已取消", kind: "reject" };
    return { label: "待处理", kind: "pending" };
  }
  if (evt === "record") {
    return { label: "已确认", kind: "done" };
  }
  // message
  if (raw === "outbound" || raw === "sent") {
    return { label: "已发送", kind: "done" };
  }
  return { label: "待回复", kind: "pending" };
}

function StatusPill({ chip }) {
  const style = STATUS_STYLES[chip.kind] || STATUS_STYLES.pending;
  return (
    <span
      style={{
        fontSize: FONT.xs,
        padding: "2px 8px",
        borderRadius: 999,
        fontWeight: 500,
        whiteSpace: "nowrap",
        background: style.bg,
        color: style.fg,
      }}
    >
      {chip.label}
    </span>
  );
}

function TimelineIcon({ kind, icon }) {
  return (
    <span
      style={{
        width: 22,
        height: 22,
        borderRadius: 6,
        display: "grid",
        placeItems: "center",
        background: ICON_BG[kind] || COLOR.bgCanvas,
        color: ICON_FG[kind] || COLOR.text2,
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
        {icon}
      </span>
    </span>
  );
}

// "今天 · 04 月 24 日" / "昨天 · 04 月 23 日" / "04 月 22 日"
function formatDayHeader(dateStr, todayStr, yesterdayStr) {
  // dateStr is YYYY-MM-DD
  const [, m, d] = dateStr.split("-");
  const stem = `${m} 月 ${d} 日`;
  if (dateStr === todayStr) return `今天 · ${stem}`;
  if (dateStr === yesterdayStr) return `昨天 · ${stem}`;
  return stem;
}

function getDateKey(ts) {
  // The backend ships ISO-ish strings via _fmt_ts. Slice the date portion off
  // the front (handles both YYYY-MM-DDTHH:MM:SS and YYYY-MM-DD HH:MM forms).
  if (!ts) return "";
  const s = String(ts).replace("T", " ");
  return s.slice(0, 10);
}

function getTimeOfDay(ts) {
  if (!ts) return "";
  const s = String(ts).replace("T", " ");
  // Pull HH:MM
  const time = s.slice(11, 16);
  return time || "";
}

function todayKey() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function yesterdayKey() {
  const now = new Date();
  now.setDate(now.getDate() - 1);
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export default function TimelinePanel({ doctorId, doctorName }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchAdminJson("/api/admin/activity")
      .then((data) => {
        if (cancelled) return;
        const all = data?.items || [];
        const filtered = doctorId
          ? all.filter((it) => it.doctor_id === doctorId)
          : all;
        setItems(filtered.slice(0, 30));
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
  }, [doctorId]);

  // Group by day key, preserving descending order (newest first).
  const groups = [];
  const seen = new Map();
  for (const item of items) {
    const key = getDateKey(item.created_at || item.ts);
    if (!seen.has(key)) {
      const arr = [];
      seen.set(key, arr);
      groups.push({ key, items: arr });
    }
    seen.get(key).push(item);
  }

  const today = todayKey();
  const yesterday = yesterdayKey();
  const headerName = doctorName ? `${doctorName} · 近期足迹` : "近期足迹";
  const aside = items.length > 0 ? `${items.length} events` : "";

  return (
    <Panel title={headerName} icon="history" aside={aside}>
      {loading && (
        <div
          style={{
            padding: "20px 0",
            textAlign: "center",
            fontSize: FONT.base,
            color: COLOR.text3,
          }}
        >
          加载中…
        </div>
      )}
      {error && !loading && (
        <div
          style={{
            padding: "20px 0",
            textAlign: "center",
            fontSize: FONT.base,
            color: COLOR.danger,
          }}
        >
          加载失败：{error}
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div
          style={{
            padding: "32px 0",
            textAlign: "center",
            fontSize: FONT.base,
            color: COLOR.text3,
          }}
        >
          近期暂无活动
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {groups.map((g, gIdx) => (
            <div key={g.key}>
              <div
                style={{
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: COLOR.text3,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  padding: gIdx === 0 ? "0 0 6px" : "12px 0 6px",
                  borderBottom: `1px solid ${COLOR.borderSubtle}`,
                  marginBottom: 4,
                }}
              >
                {formatDayHeader(g.key, today, yesterday)}
              </div>
              {g.items.map((item, iIdx) => {
                const cat = classify(item);
                const chip = statusChip(item);
                return (
                  <div
                    key={`${g.key}-${item.id || iIdx}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "64px 22px 1fr auto",
                      gap: 10,
                      alignItems: "center",
                      height: 36,
                      borderTop:
                        iIdx === 0
                          ? "none"
                          : `1px dashed ${COLOR.borderSubtle}`,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: FONT_STACK.mono,
                        fontSize: 11.5,
                        color: COLOR.text3,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {getTimeOfDay(item.created_at || item.ts)}
                    </span>
                    <TimelineIcon kind={cat.kind} icon={cat.icon} />
                    <span
                      style={{
                        fontSize: 13.5,
                        color: COLOR.text1,
                        lineHeight: 1.45,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {item.detail || "(无描述)"}
                    </span>
                    <StatusPill chip={chip} />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
