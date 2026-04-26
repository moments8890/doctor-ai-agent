// AiActivityPage — admin v3 知识库 page (cross-doctor knowledge corpus).
//
// Was previously "知识 & AI" with a suggestion table; the AI activity panel
// was dropped (per-doctor surface owns it) and the page is now the corpus
// browser: a header, a doctor + search filter bar, and the knowledge list.
//
// File name kept for URL stability (?v=3&section=overview/ai resolves here).

import { useEffect, useState } from "react";

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import RecentKnowledgeFeed from "./RecentKnowledgeFeed";

const ADMIN_TOKEN_KEY = "adminToken";


// ─── doctor-list fetch (small, local) ─────────────────────────────────────

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
          })),
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


// ─── filter bar (doctor + search) ─────────────────────────────────────────

function FilterBar({ doctorId, onDoctorChange, doctorOptions, q, onQChange }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "10px 14px",
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        flexWrap: "wrap",
      }}
    >
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
          placeholder="搜索标题、摘要或正文"
          onChange={(e) => onQChange(e.target.value)}
          style={{
            border: "none",
            outline: "none",
            background: "transparent",
            fontSize: 12.5,
            color: COLOR.text1,
            width: 220,
          }}
        />
      </div>
    </div>
  );
}


// ─── main page component ─────────────────────────────────────────────────

export default function AiActivityPage() {
  const [doctorId, setDoctorId] = useState(null);
  const [q, setQ] = useState("");

  const doctorOptions = useDoctorOptions();

  return (
    <div style={{ paddingTop: 24, display: "flex", flexDirection: "column", gap: 16 }}>
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
          知识库
        </div>
        <div
          style={{
            fontSize: FONT.sm,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
          }}
        >
          全平台知识沉淀
        </div>
      </div>

      <FilterBar
        doctorId={doctorId}
        onDoctorChange={setDoctorId}
        doctorOptions={doctorOptions}
        q={q}
        onQChange={setQ}
      />

      <RecentKnowledgeFeed doctorId={doctorId} q={q} />
    </div>
  );
}
