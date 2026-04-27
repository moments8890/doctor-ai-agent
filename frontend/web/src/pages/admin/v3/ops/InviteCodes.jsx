// InviteCodes — read-only view of all invite codes.
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html `.ops-card` 邀请码使用 block.
//
// Top: ops-card with activation meter (used / total).
// Below: full table of invite codes. Click row → copy code to clipboard.

import { useEffect, useMemo, useState } from "react";
import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";

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

function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 10);
  return `${d.getFullYear()}·${String(d.getMonth() + 1).padStart(2, "0")}·${String(d.getDate()).padStart(2, "0")}`;
}

function copyCode(code) {
  if (typeof navigator === "undefined" || !navigator.clipboard) return;
  navigator.clipboard.writeText(code).catch(() => {
    /* clipboard rejection is silent — partner doctor view is best-effort */
  });
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

function StatusPill({ active }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 9px",
        borderRadius: RADIUS.pill,
        fontSize: 11.5,
        fontWeight: 500,
        background: active ? COLOR.brandTint : COLOR.bgCanvas,
        color: active ? COLOR.brand : COLOR.text3,
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 14 }}
      >
        {active ? "check_circle" : "radio_button_unchecked"}
      </span>
      {active ? "启用" : "停用"}
    </span>
  );
}

export default function InviteCodes() {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchJson("/api/admin/invite-codes")
      .then((data) => {
        if (cancelled) return;
        setItems(Array.isArray(data?.items) ? data.items : []);
      })
      .catch((e) => !cancelled && setError(e.message || String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const summary = useMemo(() => {
    const list = items || [];
    const total = list.length;
    const activated = list.filter((r) => (r.used_count || 0) > 0).length;
    return { total, activated };
  }, [items]);

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

  const list = items || [];
  const meter =
    summary.total > 0 ? summary.activated / summary.total : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        data-v3="kpi"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
        }}
      >
        <OpsCard
          icon="key"
          title="邀请码使用"
          num={
            <>
              {summary.activated}
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 400,
                  color: COLOR.text2,
                  marginLeft: 4,
                }}
              >
                / {summary.total} 已激活
              </span>
            </>
          }
          meter={meter}
          sub={
            summary.total === 0
              ? "暂无邀请码"
              : `共 ${summary.total} 张 · 已使用 ${summary.activated} 张`
          }
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
            全部邀请码
          </span>
          <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>
            {list.length} 张
          </span>
        </div>

        {list.length === 0 ? (
          <div
            style={{
              padding: "40px 16px",
              textAlign: "center",
              color: COLOR.text3,
              fontSize: FONT.body,
            }}
          >
            暂无邀请码
          </div>
        ) : (
          <div data-v3="table-scroll">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1.4fr 1fr",
                gap: 12,
                padding: "10px 16px",
                fontSize: 11,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLOR.text3,
                fontWeight: 600,
                borderBottom: `1px solid ${COLOR.borderSubtle}`,
                background: COLOR.bgCardAlt,
              }}
            >
              <span>邀请码</span>
              <span>状态</span>
              <span>已使用</span>
              <span>归属医生</span>
              <span>创建时间</span>
            </div>
            {list.map((r) => (
              <div
                key={r.code}
                onClick={() => copyCode(r.code)}
                title="点击复制邀请码"
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1.4fr 1fr",
                  gap: 12,
                  padding: "12px 16px",
                  alignItems: "center",
                  borderBottom: `1px solid ${COLOR.borderSubtle}`,
                  cursor: "pointer",
                  fontSize: FONT.body,
                  color: COLOR.text1,
                }}
              >
                <span
                  style={{
                    fontFamily: FONT_STACK.mono,
                    fontSize: 13,
                    color: COLOR.text1,
                    fontWeight: 500,
                  }}
                >
                  {r.code}
                </span>
                <span>
                  <StatusPill active={!!r.active} />
                </span>
                <span style={{ color: COLOR.text2 }}>
                  {r.used_count || 0} / {r.max_uses || 1}
                </span>
                <span
                  style={{
                    color: r.doctor_id ? COLOR.text1 : COLOR.text4,
                    fontFamily: r.doctor_id ? FONT_STACK.mono : FONT_STACK.sans,
                    fontSize: r.doctor_id ? 12 : FONT.body,
                  }}
                >
                  {r.doctor_id || (r.doctor_name ? `${r.doctor_name} (待激活)` : "—")}
                </span>
                <span style={{ color: COLOR.text2, fontSize: FONT.sm }}>
                  {fmtDate(r.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
