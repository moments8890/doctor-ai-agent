// PatientsTab — admin v3 doctor-detail 患者 tab.
// Composes the panel head + filter bar + 3-col card grid.
// Exported so AdminDoctorDetailV3 (Task 2.1 owner) can wire it in next.
//
// Data: takes raw `patients` prop (from `related.patients?.items`). Because
// the API doesn't yet emit the exact shape the filter expects (risk /
// silentDays / isPostOp), we run a small `normalizePatients` adapter inside
// this file. If the adapter can't derive a field with confidence it leaves
// it null — chips other than 全部 will simply show 0 counts. That's
// acceptable for v1 of the admin v3 port.

import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";
import usePatientFilter from "../hooks/usePatientFilter";
import PatientFilterBar from "./PatientFilterBar";
import PatientCard from "./PatientCard";
import EmptyState from "../components/EmptyState";

// TODO normalize — replace heuristics below with first-class API fields once
// the backend exposes risk/silentDays/postop on /api/admin/doctors/{id}/related.
function normalizePatients(items) {
  if (!Array.isArray(items)) return [];
  const now = Date.now();

  return items.map((raw) => {
    // risk: best-effort from common field names; default null
    let risk = raw.risk ?? null;
    if (!risk) {
      if (raw.red_flag === true || raw.flag === "danger") risk = "danger";
      else if (raw.flag === "warn" || raw.flag === "warning") risk = "warn";
    }

    // silentDays: derive from last_message_at if present
    let silentDays = raw.silentDays ?? raw.silent_days;
    if (silentDays == null && raw.last_message_at) {
      const last = Date.parse(raw.last_message_at);
      if (!Number.isNaN(last)) {
        silentDays = Math.max(0, Math.floor((now - last) / 86400000));
      }
    }
    if (silentDays == null) silentDays = 0;

    // isPostOp: explicit field or tag scan
    let isPostOp = raw.isPostOp ?? raw.is_post_op ?? false;
    if (!isPostOp && Array.isArray(raw.tags)) {
      isPostOp = raw.tags.some((t) => /术后|post.?op/i.test(String(t)));
    }

    // Build a one-line meta from available demographics
    const metaParts = [];
    if (raw.gender) metaParts.push(raw.gender);
    if (raw.birth_year) metaParts.push(String(raw.birth_year));
    if (raw.condition || raw.diagnosis) metaParts.push(raw.condition || raw.diagnosis);
    const meta = metaParts.length ? metaParts.join(" · ") : null;

    // Stats: best-effort
    const stats = {
      messages: raw.message_count ?? raw.messages ?? 0,
      records: raw.record_count ?? raw.records ?? 0,
    };

    // Status tag — pick the first applicable signal, else null
    let statusTag = null;
    if (risk === "danger") statusTag = { label: "高危信号", kind: "danger" };
    else if (risk === "warn") statusTag = { label: "需关注", kind: "warn" };
    else if (silentDays >= 7) statusTag = { label: `${silentDays} 天未联系`, kind: "quiet" };

    return {
      id: raw.id ?? raw.patient_id ?? raw.uid ?? Math.random().toString(36).slice(2),
      name: raw.name ?? raw.patient_name ?? "未命名",
      meta,
      risk,
      silentDays,
      isPostOp,
      spark: raw.spark ?? null,
      stats,
      statusTag,
    };
  });
}

function PanelHead({ title, aside }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 14px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          fontSize: FONT.md,
          fontWeight: 600,
          color: COLOR.text1,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          groups
        </span>
        {title}
      </div>
      {aside && (
        <div style={{ fontSize: FONT.sm, color: COLOR.text2 }}>{aside}</div>
      )}
    </div>
  );
}

export default function PatientsTab({ patients }) {
  const normalized = normalizePatients(patients || []);
  const { filter, setFilter, filtered, counts } = usePatientFilter(normalized);

  return (
    <div
      style={{
        marginTop: 16,
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        overflow: "hidden",
      }}
    >
      <PanelHead title="医生的患者" aside={`${normalized.length} 位`} />
      <PatientFilterBar filter={filter} onChange={setFilter} counts={counts} />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 10,
          padding: "12px 14px",
        }}
      >
        {filtered.map((p) => (
          <PatientCard key={p.id} patient={p} />
        ))}
      </div>
      {filtered.length === 0 && (
        <div style={{ padding: "12px 14px" }}>
          <EmptyState
            icon="inbox"
            title="暂无匹配的患者"
            desc="试试切换筛选条件，或检查该医生是否还没添加患者。"
          />
        </div>
      )}
    </div>
  );
}
