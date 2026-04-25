// PartnerReport — 合作伙伴报表 page (current ISO week).
// Reads /api/admin/ops/partner-report.
// Three ops-cards: 本周采纳率 / 本周活跃患者 / 本周危险信号.
// Below: top-doctors table + a "下载 PDF" no-op stub.

import { useEffect, useState } from "react";
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

function downloadPdfNoop() {
  // TODO export — wire up real PDF generation in a follow-up.
  // Keeping this as a hover-feedback no-op so the partner-doctor demo doesn't
  // 404 a click before the export pipeline lands.
  if (typeof window !== "undefined") {
    window.alert("PDF 下载即将上线");
  }
}

export default function PartnerReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchJson("/api/admin/ops/partner-report")
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

  const adoptionRate = data.adoption?.rate || 0;
  const adoptionTotal = data.adoption?.total || 0;
  const topDoctors = Array.isArray(data.top_doctors) ? data.top_doctors : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <span style={{ fontSize: FONT.sm, color: COLOR.text2 }}>
          报告周期：{data.start_date} → {data.end_date}（{data.week}）
        </span>
        <a
          onClick={downloadPdfNoop}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontSize: 12.5,
            color: COLOR.info,
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            download
          </span>
          下载 PDF
        </a>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
        }}
      >
        <OpsCard
          icon="summarize"
          title="本周采纳率"
          num={
            <>
              {Math.round(adoptionRate * 100)}
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 400,
                  color: COLOR.text2,
                  marginLeft: 4,
                }}
              >
                %
              </span>
            </>
          }
          meter={adoptionRate}
          sub={`共 ${adoptionTotal} 条 AI 建议被处理`}
        />
        <OpsCard
          icon="groups"
          title="本周活跃患者"
          num={data.patient_active || 0}
          sub="本周内有消息往来的独立患者数"
        />
        <OpsCard
          icon="warning"
          title="本周危险信号"
          num={data.danger_signals_triggered || 0}
          sub="触发的临床危险信号事件数"
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
            本周活跃医生 Top 3
          </span>
          <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>
            按采纳率排序
          </span>
        </div>

        {topDoctors.length === 0 ? (
          <div
            style={{
              padding: "40px 16px",
              textAlign: "center",
              color: COLOR.text3,
              fontSize: FONT.body,
            }}
          >
            本周暂无数据
          </div>
        ) : (
          <div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1fr",
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
              <span>医生</span>
              <span>采纳率</span>
              <span>患者数</span>
              <span>doctor_id</span>
            </div>
            {topDoctors.map((d, idx) => (
              <div
                key={d.doctor_id || idx}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1fr",
                  gap: 12,
                  padding: "12px 16px",
                  alignItems: "center",
                  borderBottom:
                    idx === topDoctors.length - 1
                      ? "none"
                      : `1px solid ${COLOR.borderSubtle}`,
                  fontSize: FONT.body,
                  color: COLOR.text1,
                }}
              >
                <span style={{ fontWeight: 500 }}>{d.name}</span>
                <span style={{ color: COLOR.brand, fontWeight: 600 }}>
                  {Math.round((d.adoption_rate || 0) * 100)}%
                </span>
                <span style={{ color: COLOR.text2 }}>
                  {d.patient_count || 0}
                </span>
                <span
                  style={{
                    color: COLOR.text3,
                    fontFamily: FONT_STACK.mono,
                    fontSize: 12,
                  }}
                >
                  {d.doctor_id}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
