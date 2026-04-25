// DoctorList — fallback view when no `?doctor=<id>` is in the URL.
// Fetches /api/admin/doctors and renders a simple list. Clicking a row
// updates the URL to `?v=3&doctor=<id>` so the v3 entry mounts the
// AdminDoctorDetailV3 component on the next render cycle.

import { useEffect, useState } from "react";
import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

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

function fmtRelative(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 16);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return `${d.getFullYear()}·${String(d.getMonth() + 1).padStart(2, "0")}·${String(d.getDate()).padStart(2, "0")}`;
}

function firstChar(name) {
  if (!name) return "医";
  const trimmed = String(name).trim();
  return trimmed ? trimmed.charAt(0) : "医";
}

function selectDoctor(doctorId) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  params.set("v", "3");
  params.set("doctor", doctorId);
  const next = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
  // Push then dispatch popstate so the v3 entry re-reads the URL.
  window.history.pushState(null, "", next);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function DoctorRow({ doctor }) {
  const [hover, setHover] = useState(false);
  const dept = doctor.department || doctor.specialty || "";
  return (
    <div
      onClick={() => selectDoctor(doctor.doctor_id)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 12,
        alignItems: "center",
        padding: "12px 16px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        cursor: "pointer",
        background: hover ? COLOR.bgCardAlt : "transparent",
        transition: "100ms",
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: COLOR.infoTint,
          color: COLOR.info,
          display: "grid",
          placeItems: "center",
          fontSize: FONT.md,
          fontWeight: 600,
        }}
      >
        {firstChar(doctor.name)}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontSize: FONT.body, fontWeight: 500, color: COLOR.text1 }}>
            {doctor.name || "(未命名医生)"}
          </span>
          {dept && (
            <span
              style={{
                fontSize: 11.5,
                background: COLOR.brandTint,
                color: COLOR.brand,
                padding: "2px 9px",
                borderRadius: RADIUS.pill,
                fontWeight: 500,
              }}
            >
              {dept}
            </span>
          )}
        </div>
        <span
          style={{
            fontSize: FONT.xs,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
          }}
        >
          {doctor.doctor_id}
        </span>
      </div>
      <span style={{ fontSize: FONT.sm, color: COLOR.text2 }}>
        最近活跃 {fmtRelative(doctor.last_active)}
      </span>
    </div>
  );
}

export default function DoctorList() {
  const [doctors, setDoctors] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // include_unnamed=false hides invite-link clicks that never reached the
  // nickname step. Operators flip this on when investigating drop-off.
  const [showUnnamed, setShowUnnamed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const url = showUnnamed
      ? "/api/admin/doctors?include_unnamed=true"
      : "/api/admin/doctors";
    fetchJson(url)
      .then((data) => {
        if (cancelled) return;
        setDoctors(data.doctors || data.items || []);
      })
      .catch((e) => !cancelled && setError(e.message || String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [showUnnamed]);

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

  const list = doctors || [];

  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: "0 1px 1px rgba(15,23,28,0.04)",
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
          选择医生
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <label
            style={{
              fontSize: FONT.sm,
              color: COLOR.text3,
              display: "flex",
              alignItems: "center",
              gap: 6,
              cursor: "pointer",
              userSelect: "none",
            }}
          >
            <input
              type="checkbox"
              checked={showUnnamed}
              onChange={(e) => setShowUnnamed(e.target.checked)}
              style={{ cursor: "pointer" }}
            />
            显示未入驻
          </label>
          <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>{list.length} 位</span>
        </div>
      </div>
      {list.length === 0 ? (
        <div style={{ padding: "40px 16px", textAlign: "center", color: COLOR.text3, fontSize: FONT.body }}>
          暂无医生
        </div>
      ) : (
        list.map((d) => <DoctorRow key={d.doctor_id} doctor={d} />)
      )}
    </section>
  );
}
