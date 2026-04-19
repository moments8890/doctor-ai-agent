/**
 * @route /doctor/patients
 *
 * v2 PatientsPage — antd-mobile patient list with search + NL search + AI tags.
 */
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { List, SearchBar, Button, ErrorBlock, DotLoading } from "antd-mobile";
import { usePatients, useAIAttention } from "../../../lib/doctorQueries";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { relativeDate } from "../../../utils/time";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { NameAvatar, LoadingCenter, EmptyState } from "../../components";

// ── Helpers ────────────────────────────────────────────────────────

// Detect queries that should go through the NL search backend rather than
// being matched locally on the name field.
function isNLQuery(q) {
  return /[的得了这那哪]{1}|姓|阿姨|叔叔|奶奶|大爷|多岁|中年|老年|男性|女性|上周|本周|最近|昨天/.test(q);
}

function patientSubtitle(patient, aiTag) {
  const age = patient.year_of_birth
    ? new Date().getFullYear() - patient.year_of_birth
    : null;
  const genderStr = patient.gender
    ? { male: "男", female: "女" }[patient.gender] || patient.gender
    : null;
  const base = [
    genderStr,
    age ? `${age}岁` : null,
    patient.chief_complaint || patient.primary_category || `${patient.record_count || 0}份病历`,
  ]
    .filter(Boolean)
    .join(" · ");
  if (!aiTag) return base;
  return (
    <span>
      {base} · <span style={{ color: APP.primary }}>AI: {aiTag}</span>
    </span>
  );
}

function UrgencyTag({ triage }) {
  if (!triage) return null;
  if (triage === "urgent")
    return (
      <span
        style={{
          fontSize: FONT.xs,
          fontWeight: 600,
          padding: "1px 5px",
          borderRadius: RADIUS.xs,
          background: APP.danger,
          color: APP.white,
          marginLeft: 4,
          flexShrink: 0,
        }}
      >
        紧急
      </span>
    );
  if (triage === "symptom_report" || triage === "side_effect")
    return (
      <span
        style={{
          fontSize: FONT.xs,
          fontWeight: 600,
          padding: "1px 5px",
          borderRadius: RADIUS.xs,
          background: APP.warning,
          color: APP.white,
          marginLeft: 4,
          flexShrink: 0,
        }}
      >
        待处理
      </span>
    );
  return null;
}

// ── Main component ─────────────────────────────────────────────────

export default function PatientsPage() {
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const { data, isLoading, isError, refetch } = usePatients();
  const { data: attentionData } = useAIAttention();

  const patients = useMemo(() => {
    const items = Array.isArray(data) ? data : data?.items || [];
    return items;
  }, [data]);

  // AI attention → map of patientId → short tag string. Attention-tagged
  // patients float to the top of the list so the doctor sees them first.
  const aiTagMap = useMemo(() => {
    const out = {};
    const list = attentionData?.patients || [];
    for (const p of list) {
      if (p.patient_id) {
        out[p.patient_id] = p.short_tag || p.reason?.slice(0, 12) || "关注";
      }
    }
    return out;
  }, [attentionData]);

  const [search, setSearch] = useState("");
  const [nlResults, setNlResults] = useState(null);
  const [nlLoading, setNlLoading] = useState(false);

  function handleSearchChange(val) {
    setSearch(val);
    setNlResults(null);
  }

  // NL search fires on Enter / submit. Queries matching isNLQuery() go to the
  // backend; plain-text queries keep using the local name filter.
  async function handleSearchSubmit() {
    const q = search.trim();
    if (!q || !isNLQuery(q)) return;
    setNlLoading(true);
    try {
      const d = await api.searchPatients(doctorId, q);
      setNlResults(d?.items || []);
    } catch {
      setNlResults([]);
    } finally {
      setNlLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const q = search.trim();
    const base = !q
      ? patients
      : nlResults !== null
        ? nlResults
        : patients.filter((p) => (p.name || "").includes(q));
    // Sort: AI-attention patients first, then by most recent activity
    return [...base].sort((a, b) => {
      const aTagged = aiTagMap[a.id] ? 1 : 0;
      const bTagged = aiTagMap[b.id] ? 1 : 0;
      if (aTagged !== bTagged) return bTagged - aTagged;
      const aDate = a.last_activity_at || a.created_at || "";
      const bDate = b.last_activity_at || b.created_at || "";
      return bDate.localeCompare(aDate);
    });
  }, [patients, search, nlResults, aiTagMap]);

  function handlePatientClick(patient) {
    navigate(`/doctor/patients/${patient.id}`);
  }

  function handleNewInterview() {
    navigate("/doctor/patients/new");
  }

  if (isLoading) return <LoadingCenter fullPage />;

  if (isError) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
        <ErrorBlock
          status="default"
          title="加载失败"
          description="无法获取患者列表"
        >
          <Button color="primary" onClick={() => refetch()}>
            重试
          </Button>
        </ErrorBlock>
      </div>
    );
  }

  const showNLHint = search.trim() && isNLQuery(search.trim()) && nlResults === null && !nlLoading;
  const showNLActive = nlResults !== null && search.trim();

  return (
    <div style={pageContainer}>
      {/* Search bar */}
      <div style={styles.searchWrap}>
        <SearchBar
          placeholder={`搜索患者${patients.length > 0 ? `（共${patients.length}人）` : ""}`}
          value={search}
          onChange={handleSearchChange}
          onSearch={handleSearchSubmit}
          onClear={() => { setSearch(""); setNlResults(null); }}
          style={{ flex: 1 }}
        />
      </div>

      {/* NL search hint / status strip */}
      {showNLHint && (
        <div style={styles.nlStrip}>
          按回车用AI搜索：「{search.trim()}」
        </div>
      )}
      {nlLoading && (
        <div style={styles.nlStrip}>
          AI 搜索中 <DotLoading color="primary" />
        </div>
      )}
      {showNLActive && !nlLoading && (
        <div style={styles.nlStrip}>
          AI 搜索结果 · {nlResults.length} 位患者
        </div>
      )}

      {/* Patient list */}
      <div style={scrollable}>
        {filtered.length === 0 && !isLoading && (
          search
            ? <EmptyState title="无匹配患者" description="试试其他关键词" />
            : <EmptyState title="暂无患者" description="点击右上角 + 新建第一位患者" action="新建病历" onAction={handleNewInterview} />
        )}

        {filtered.length > 0 && (
          <List
            style={{
              "--border-top": "none",
              "--border-bottom": "none",
              "--border-inner": `0.5px solid ${APP.border}`,
            }}
          >
            {filtered.map((patient) => {
              const triage =
                patient.latest_triage_category || patient.triage_category;
              const timeStr = relativeDate(
                patient.last_activity_at ||
                  patient.updated_at ||
                  patient.created_at
              );
              const aiTag = aiTagMap[patient.id];
              return (
                <List.Item
                  key={patient.id}
                  prefix={<NameAvatar name={patient.name} size={36} />}
                  description={patientSubtitle(patient, aiTag)}
                  extra={
                    <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
                      {timeStr}
                    </span>
                  }
                  onClick={() => handlePatientClick(patient)}
                  style={{ "--align-items": "center" }}
                >
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <span style={{ fontWeight: 500, fontSize: FONT.md }}>
                      {patient.name || "未命名"}
                    </span>
                    <UrgencyTag triage={triage} />
                  </div>
                </List.Item>
              );
            })}
          </List>
        )}
      </div>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────

const styles = {
  searchWrap: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    background: APP.surface,
    borderBottom: `0.5px solid ${APP.border}`,
    flexShrink: 0,
  },
  nlStrip: {
    padding: "6px 16px",
    fontSize: FONT.sm,
    color: APP.text4,
    background: APP.surfaceAlt,
    borderBottom: `0.5px solid ${APP.borderLight}`,
    flexShrink: 0,
  },
};
