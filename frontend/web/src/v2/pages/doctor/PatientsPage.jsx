/**
 * @route /doctor/patients
 *
 * v2 PatientsPage — antd-mobile patient list with search.
 * No MUI, no src/components, no src/theme.js.
 */
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { List, SearchBar, Button, SpinLoading, ErrorBlock } from "antd-mobile";
import { AddOutline } from "antd-mobile-icons";
import { usePatients } from "../../../lib/doctorQueries";
import { relativeDate } from "../../../utils/time";
import { APP } from "../../theme";

// ── Helpers ────────────────────────────────────────────────────────

function patientSubtitle(patient) {
  const age = patient.year_of_birth
    ? new Date().getFullYear() - patient.year_of_birth
    : null;
  const genderStr = patient.gender
    ? { male: "男", female: "女" }[patient.gender] || patient.gender
    : null;
  return [
    genderStr,
    age ? `${age}岁` : null,
    patient.chief_complaint || patient.primary_category || `${patient.record_count || 0}份病历`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function NameCircle({ name }) {
  const ch = (name || "?")[0];
  return (
    <div
      style={{
        width: 40,
        height: 40,
        borderRadius: "50%",
        background: "#07C160",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 16,
        fontWeight: 600,
        flexShrink: 0,
      }}
    >
      {ch}
    </div>
  );
}

function UrgencyTag({ triage }) {
  if (!triage) return null;
  if (triage === "urgent")
    return (
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          padding: "1px 5px",
          borderRadius: 4,
          background: "#FA5151",
          color: "#fff",
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
          fontSize: 10,
          fontWeight: 600,
          padding: "1px 5px",
          borderRadius: 4,
          background: "#FFC300",
          color: "#fff",
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
  const { data, isLoading, isError, refetch } = usePatients();

  const patients = useMemo(() => {
    const items = Array.isArray(data) ? data : data?.items || [];
    return items;
  }, [data]);

  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const q = search.trim();
    if (!q) return patients;
    return patients.filter((p) => (p.name || "").includes(q));
  }, [patients, search]);

  function handlePatientClick(patient) {
    navigate(`/doctor/patients/${patient.id}`);
  }

  function handleNewInterview() {
    navigate("/doctor/patients/new");
  }

  if (isLoading) {
    return (
      <div style={styles.center}>
        <SpinLoading color="#07C160" style={{ "--size": "32px" }} />
      </div>
    );
  }

  if (isError) {
    return (
      <div style={styles.center}>
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

  return (
    <div style={styles.page}>
      {/* Search bar */}
      <div style={styles.searchWrap}>
        <SearchBar
          placeholder={`搜索患者${patients.length > 0 ? `（共${patients.length}人）` : ""}`}
          value={search}
          onChange={setSearch}
          onClear={() => setSearch("")}
          style={{
            "--background": APP.surface,
            flex: 1,
          }}
        />
        <Button
          color="primary"
          size="small"
          style={styles.newBtn}
          onClick={handleNewInterview}
        >
          <AddOutline style={{ marginRight: 2 }} />
          新建病历
        </Button>
      </div>

      {/* Patient list */}
      <div style={styles.listWrap}>
        {filtered.length === 0 && !isLoading && (
          <ErrorBlock
            status="empty"
            title={search ? "无匹配患者" : "暂无患者"}
            description={search ? "试试其他关键词" : "点击「新建病历」添加第一位患者"}
            style={{ paddingTop: 40 }}
          />
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
              return (
                <List.Item
                  key={patient.id}
                  prefix={<NameCircle name={patient.name} />}
                  description={patientSubtitle(patient)}
                  extra={
                    <span style={{ fontSize: 12, color: APP.text4 }}>
                      {timeStr}
                    </span>
                  }
                  onClick={() => handlePatientClick(patient)}
                  style={{ "--align-items": "center" }}
                >
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <span style={{ fontWeight: 500, fontSize: 15 }}>
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
  page: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: APP.surfaceAlt,
    overflow: "hidden",
  },
  searchWrap: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    background: APP.surface,
    borderBottom: `0.5px solid ${APP.border}`,
    flexShrink: 0,
  },
  newBtn: {
    flexShrink: 0,
    "--background-color": "#07C160",
    "--border-color": "#07C160",
    "--text-color": "#fff",
    borderRadius: 8,
    height: 32,
    padding: "0 10px",
    fontSize: 13,
    display: "flex",
    alignItems: "center",
  },
  listWrap: {
    flex: 1,
    overflowY: "auto",
  },
  center: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
  },
};
