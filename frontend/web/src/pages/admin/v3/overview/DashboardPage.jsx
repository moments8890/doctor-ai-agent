// DashboardPage — cross-doctor 仪表盘 (admin v3, ?v=3&section=overview/dashboard).
//
// First-impression page for hospital partner doctors. Layout:
//   1. CrossDoctorKpiStrip       (5 platform-wide KPIs)
//   2. row-3-1 grid:
//        Left  → AiAdoptionPanel  (no `doctor` prop → falls back to platform-wide
//                                  /api/admin/overview hero.ai_acceptance)
//        Right → stack of SystemHealthPanel + AlertsCallout
//   3. TimelinePanel              (no doctorId → all activity, "平台动态")
//
// Data: a single `/api/admin/overview` fetch hydrates the KPI strip, system
// health panel, and alerts. AiAdoptionPanel and TimelinePanel each own their
// own fetches (already implemented), so this page composes them without
// forwarding the response. We still display a skeleton/empty/error state for
// the parts that depend on /overview.

import { useEffect, useState } from "react";
import { COLOR, FONT, SPACE } from "../tokens";
import AiAdoptionPanel from "../doctorDetail/AiAdoptionPanel";
import TimelinePanel from "../doctorDetail/TimelinePanel";
import CrossDoctorKpiStrip from "./CrossDoctorKpiStrip";
import SystemHealthPanel from "./SystemHealthPanel";
import AlertsCallout from "./AlertsCallout";

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

function KpiSkeleton() {
  return (
    <div
      style={{
        height: 96,
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: 12,
      }}
    />
  );
}

function ErrorBanner({ error }) {
  return (
    <div
      style={{
        padding: "10px 14px",
        background: COLOR.dangerTint,
        border: `1px solid ${COLOR.danger}33`,
        color: COLOR.danger,
        fontSize: FONT.base,
        borderRadius: 12,
      }}
    >
      加载概览数据失败：{error}
    </div>
  );
}

export default function DashboardPage() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAdminJson("/api/admin/overview")
      .then((data) => {
        if (cancelled) return;
        setOverview(data);
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
  }, []);

  const hero = overview?.hero;
  const secondary = overview?.secondary;
  const alerts = overview?.alerts;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: SPACE.sectionGap,
        paddingTop: 4,
        paddingBottom: SPACE.pageGutter,
      }}
    >
      {error && <ErrorBanner error={error} />}

      {loading && !overview ? (
        <KpiSkeleton />
      ) : (
        <CrossDoctorKpiStrip hero={hero} secondary={secondary} />
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 3fr) minmax(0, 1fr)",
          gap: SPACE.sectionGap,
          alignItems: "start",
        }}
      >
        <AiAdoptionPanel />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: SPACE.sectionGap,
            minWidth: 0,
          }}
        >
          <SystemHealthPanel hero={hero} secondary={secondary} />
          <AlertsCallout alerts={alerts} />
        </div>
      </div>

      <TimelinePanel title="平台动态" />
    </div>
  );
}
