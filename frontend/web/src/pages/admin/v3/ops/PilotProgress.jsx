// PilotProgress — 试点进度 page.
// Reads /api/admin/ops/pilot-progress.
// Top: ops-card with current week / total + meter + next-milestone hint.
// Below: timeline list of all milestones with done / pending icons.

import { useEffect, useMemo, useState } from "react";
import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";

const ADMIN_TOKEN_KEY = "adminToken";

async function fetchJson(url) {
  const token =
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function fmtDate(iso) {
  if (!iso) return "—";
  const parts = String(iso).split("-");
  if (parts.length < 3) return iso;
  return `${parts[0]}·${parts[1]}·${parts[2]}`;
}

function OpsCard({ icon, title, num, sub, meter }) {
  return (
    <div
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        boxShadow: SHADOW.s1,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          fontWeight: 600,
          color: COLOR.text1,
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{ color: COLOR.text2, fontSize: 18 }}
        >
          {icon}
        </span>
        {title}
      </div>
      <div
        style={{
          fontSize: 24,
          fontWeight: 600,
          fontVariantNumeric: "tabular-nums",
          color: COLOR.text1,
          letterSpacing: "-0.02em",
        }}
      >
        {num}
      </div>
      {meter !== undefined && (
        <div
          style={{
            height: 4,
            background: COLOR.bgCanvas,
            borderRadius: 999,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${Math.max(0, Math.min(100, meter * 100))}%`,
              height: "100%",
              background: COLOR.info,
            }}
          />
        </div>
      )}
      {sub && <div style={{ fontSize: 12, color: COLOR.text2 }}>{sub}</div>}
    </div>
  );
}

function MilestoneRow({ m, last }) {
  const done = !!m.done;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 14,
        alignItems: "center",
        padding: "12px 16px",
        borderBottom: last ? "none" : `1px solid ${COLOR.borderSubtle}`,
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: 22,
          color: done ? COLOR.brand : COLOR.text4,
        }}
      >
        {done ? "check_circle" : "radio_button_unchecked"}
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span
          style={{
            fontSize: FONT.body,
            color: COLOR.text1,
            fontWeight: 500,
            textDecoration: done ? "none" : "none",
          }}
        >
          {m.label}
        </span>
        <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>
          {fmtDate(m.date)}
        </span>
      </div>
      <span
        style={{
          fontSize: 11.5,
          padding: "2px 9px",
          borderRadius: RADIUS.pill,
          fontWeight: 500,
          background: done ? COLOR.brandTint : COLOR.bgCanvas,
          color: done ? COLOR.brand : COLOR.text3,
        }}
      >
        {done ? "已完成" : "待办"}
      </span>
    </div>
  );
}

export default function PilotProgress() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchJson("/api/admin/ops/pilot-progress")
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => !cancelled && setError(e.message || String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const nextMilestone = useMemo(() => {
    if (!data?.milestones) return null;
    return data.milestones.find((m) => !m.done) || null;
  }, [data]);

  if (loading) {
    return (
      <div style={{ padding: "40px 16px", color: COLOR.text2, fontSize: FONT.body }}>
        加载中…
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ padding: "40px 16px", color: COLOR.danger, fontSize: FONT.body }}>
        加载失败：{error}
      </div>
    );
  }
  if (!data) return null;

  const weekMeter = data.total_weeks ? data.current_week / data.total_weeks : 0;
  const doctorMeter = data.doctors_target
    ? data.doctors_active / data.doctors_target
    : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
        }}
      >
        <OpsCard
          icon="timeline"
          title="试点进度"
          num={
            <>
              第 {data.current_week}{" "}
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 400,
                  color: COLOR.text2,
                  marginLeft: 4,
                }}
              >
                / {data.total_weeks} 周
              </span>
            </>
          }
          meter={weekMeter}
          sub={
            nextMilestone
              ? `下一里程碑 ${fmtDate(nextMilestone.date)} · ${nextMilestone.label}`
              : "全部里程碑已完成"
          }
        />
        <OpsCard
          icon="deployed_code_history"
          title="试点医生"
          num={
            <>
              {data.doctors_active}
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 400,
                  color: COLOR.text2,
                  marginLeft: 4,
                }}
              >
                / {data.doctors_target} 位
              </span>
            </>
          }
          meter={doctorMeter}
          sub={`首批目标 ${data.doctors_target} 位 · 已加入 ${data.doctors_active} 位`}
        />
        <OpsCard
          icon="check_circle"
          title="已完成里程碑"
          num={
            <>
              {data.milestones?.filter((m) => m.done).length || 0}
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 400,
                  color: COLOR.text2,
                  marginLeft: 4,
                }}
              >
                / {data.milestones?.length || 0}
              </span>
            </>
          }
          sub={`试点开始于 ${fmtDate(data.start_date)}`}
        />
      </div>

      <section
        style={{
          background: COLOR.bgCard,
          border: `1px solid ${COLOR.borderSubtle}`,
          borderRadius: RADIUS.lg,
          boxShadow: SHADOW.s1,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: 44,
            padding: "0 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: `1px solid ${COLOR.borderSubtle}`,
          }}
        >
          <span style={{ fontSize: FONT.body, fontWeight: 600, color: COLOR.text1 }}>
            里程碑时间线
          </span>
          <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>
            共 {data.milestones?.length || 0} 项
          </span>
        </div>
        {(data.milestones || []).map((m, idx) => (
          <MilestoneRow
            key={`${m.date}-${idx}`}
            m={m}
            last={idx === (data.milestones?.length || 0) - 1}
          />
        ))}
      </section>
    </div>
  );
}
