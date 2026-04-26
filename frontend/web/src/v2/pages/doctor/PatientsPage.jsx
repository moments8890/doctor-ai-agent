/**
 * @route /doctor/patients
 *
 * v2 PatientsPage — antd-mobile patient list with search + NL search + AI tags.
 */
import { useState, useMemo, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { List, SearchBar, Button, ErrorBlock, DotLoading, Popup, PullToRefresh } from "antd-mobile";
import { Collapse } from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { usePatients, useAIAttention } from "../../../lib/doctorQueries";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { relativeDate, formatAge } from "../../../utils/time";
import { APP, FONT, ICON, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { NameAvatar, LoadingCenter, EmptyState } from "../../components";

// ── Helpers ────────────────────────────────────────────────────────

// Detect queries that should go through the NL search backend rather than
// being matched locally on the name field.
function isNLQuery(q) {
  return /[的得了这那哪]{1}|姓|阿姨|叔叔|奶奶|大爷|多岁|中年|老年|男性|女性|上周|本周|最近|昨天/.test(q);
}

// Row subtitle (vitals only): "男 · 70岁 · 0份病历".
// Action items like "患者消息待处理" / "任务到期" render on their own green line below.
function patientSubtitle(patient) {
  const genderStr = patient.gender
    ? { male: "男", female: "女" }[patient.gender] || patient.gender
    : null;
  return [
    genderStr,
    formatAge(patient.year_of_birth),
    `${patient.record_count || 0}份病历`,
  ]
    .filter(Boolean)
    .join(" · ");
}

// Section header — title + optional badge + (optional) collapse chevron.
// When collapsible, tapping anywhere on the header toggles the section and
// the chevron rotates 90° when open. Non-collapsible sections omit the chevron.
function SectionHeader({ title, badgeCount, open, onToggle, collapsible }) {
  return (
    <div
      onClick={collapsible ? onToggle : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        padding: "14px 16px 8px",
        background: APP.surface,
        cursor: collapsible ? "pointer" : "default",
        userSelect: "none",
      }}
    >
      <span style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
        {title}
      </span>
      {badgeCount > 0 && (
        <span
          style={{
            marginLeft: 8,
            minWidth: 18,
            height: 18,
            padding: "0 6px",
            borderRadius: 9,
            backgroundColor: APP.danger,
            color: APP.white,
            fontSize: FONT.xs,
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            lineHeight: 1,
          }}
        >
          {badgeCount}
        </span>
      )}
      <span style={{ flex: 1 }} />
      {collapsible && (
        <ChevronRightIcon
          sx={{
            fontSize: ICON.sm,
            color: APP.text4,
            transform: open ? "rotate(90deg)" : "rotate(0deg)",
            transition: "transform 0.2s ease",
          }}
        />
      )}
    </div>
  );
}

function PatientSection({
  title,
  badgeCount,
  patients,
  attentionMap,
  onPatientClick,
  collapsible = true,
  defaultOpen = true,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const effectiveOpen = collapsible ? open : true;
  return (
    <>
      <SectionHeader
        title={title}
        badgeCount={badgeCount}
        open={effectiveOpen}
        onToggle={() => setOpen((v) => !v)}
        collapsible={collapsible}
      />
      <Collapse in={effectiveOpen} timeout={200} unmountOnExit>
      <List
        style={{
          "--border-top": "none",
          "--border-bottom": "none",
          "--border-inner": `0.5px solid ${APP.border}`,
        }}
      >
        {patients.map((patient) => {
          const timeStr = relativeDate(
            patient.last_activity_at ||
              patient.updated_at ||
              patient.created_at
          );
          const attn = attentionMap[patient.id];
          // 新 badge: patient is unviewed AND created in the last 24h.
          // The 24h window prevents a dropped mark-viewed POST from
          // stranding the badge forever (Codex correctness fix).
          const createdMs = patient.created_at
            ? Date.parse(patient.created_at) || 0
            : 0;
          const isNewUnviewed =
            !patient.first_doctor_view_at &&
            createdMs > 0 &&
            (Date.now() - createdMs) < 24 * 60 * 60 * 1000;
          return (
            <List.Item
              key={patient.id}
              prefix={<NameAvatar name={patient.name} size={36} />}
              description={
                <>
                  {patientSubtitle(patient)}
                  {attn?.reason && (
                    <div style={{ marginTop: 4, color: APP.primary, fontSize: FONT.sm }}>
                      {attn.reason}
                    </div>
                  )}
                </>
              }
              extra={
                <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
                  {timeStr}
                </span>
              }
              onClick={() => onPatientClick(patient)}
              style={{ "--align-items": "center" }}
            >
              <span style={{ fontWeight: 500, fontSize: FONT.md }}>
                {patient.name || "未命名"}
              </span>
              {isNewUnviewed && (
                <span
                  style={{
                    marginLeft: 8,
                    padding: "1px 6px",
                    borderRadius: RADIUS.sm || 4,
                    background: APP.primary,
                    color: APP.white,
                    fontSize: FONT.xs,
                    fontWeight: 500,
                    verticalAlign: "middle",
                  }}
                >
                  新
                </span>
              )}
            </List.Item>
          );
        })}
      </List>
      </Collapse>
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────

export default function PatientsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = usePatients();
  const { data: attentionData } = useAIAttention();

  // "新建病历" shortcut from MyAIPage arrives as ?action=new. Open the picker
  // and clean the URL so back-navigation doesn't reopen it.
  const [pickerOpen, setPickerOpen] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("action") === "new") {
      setPickerOpen(true);
      params.delete("action");
      const qs = params.toString();
      navigate(
        `${location.pathname}${qs ? `?${qs}` : ""}`,
        { replace: true }
      );
    }
  }, [location.search]); // eslint-disable-line react-hooks/exhaustive-deps

  function startIntake(patient) {
    setPickerOpen(false);
    navigate(patient ? `/doctor/patients/new?patient_id=${patient.id}` : "/doctor/patients/new");
  }

  const patients = useMemo(() => {
    const items = Array.isArray(data) ? data : data?.items || [];
    return items;
  }, [data]);

  // AI attention → per-patient aggregate: primary reason text, shown as a
  // green second line under the vitals. Unread messages win over due tasks
  // and unreviewed suggestions when a patient has multiple flags.
  const PRIORITY = { unread_message: 0, due_task: 1, unreviewed_suggestion: 2 };
  const attentionMap = useMemo(() => {
    const out = {};
    const list = attentionData?.patients || [];
    for (const p of list) {
      if (!p.patient_id) continue;
      const incoming = {
        type: p.type || "",
        reason: p.reason || p.short_tag || "需关注",
        urgency: p.urgency || "medium",
      };
      const cur = out[p.patient_id];
      if (!cur) {
        out[p.patient_id] = incoming;
        continue;
      }
      const curPri = PRIORITY[cur.type] ?? 99;
      const inPri = PRIORITY[incoming.type] ?? 99;
      if (inPri < curPri) out[p.patient_id] = incoming;
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
    return !q
      ? patients
      : nlResults !== null
        ? nlResults
        : patients.filter((p) => (p.name || "").includes(q));
  }, [patients, search, nlResults]);

  // Partition filtered list into 3 sections. Each patient appears in exactly
  // one section; ordering inside each section is most-recent-activity first.
  const groups = useMemo(() => {
    const pending = [];
    const recent = [];
    const others = [];
    const sevenDaysAgo = Date.now() - 7 * 86400 * 1000;
    const sortByActivity = (a, b) => {
      const aDate = a.last_activity_at || a.created_at || "";
      const bDate = b.last_activity_at || b.created_at || "";
      return bDate.localeCompare(aDate);
    };
    for (const p of filtered) {
      if (attentionMap[p.id]) {
        pending.push(p);
        continue;
      }
      const ts = new Date(p.last_activity_at || p.created_at || 0).getTime();
      if (Number.isFinite(ts) && ts > sevenDaysAgo) recent.push(p);
      else others.push(p);
    }
    return {
      pending: pending.sort(sortByActivity),
      recent: recent.sort(sortByActivity),
      others: others.sort(sortByActivity),
    };
  }, [filtered, attentionMap]);

  function handlePatientClick(patient) {
    navigate(`/doctor/patients/${patient.id}`);
  }

  function handleNewIntake() {
    navigate("/doctor/patients?action=new");
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

      {/* "新建病历" picker — triggered by ?action=new from MyAIPage */}
      <Popup
        visible={pickerOpen}
        onMaskClick={() => setPickerOpen(false)}
        onClose={() => setPickerOpen(false)}
        bodyStyle={{
          borderTopLeftRadius: RADIUS.lg,
          borderTopRightRadius: RADIUS.lg,
          maxHeight: "72vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={styles.pickerHeader}>选择患者</div>
        <div style={styles.pickerBody}>
          <div
            role="button"
            onClick={() => startIntake(null)}
            style={styles.pickerNewRow}
          >
            <div style={styles.pickerNewIcon}>
              <AddCircleOutlineIcon sx={{ fontSize: ICON.md, color: APP.primary }} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1 }}>
                新建患者
              </div>
              <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                在对话中输入患者信息
              </div>
            </div>
          </div>
          {patients.length > 0 && (
            <List
              style={{
                "--border-top": "none",
                "--border-bottom": "none",
                "--border-inner": `0.5px solid ${APP.border}`,
              }}
            >
              {patients.map((p) => {
                const genderStr = p.gender
                  ? { male: "男", female: "女" }[p.gender] || p.gender
                  : null;
                const sub = [genderStr, formatAge(p.year_of_birth)]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <List.Item
                    key={p.id}
                    prefix={<NameAvatar name={p.name} size={36} />}
                    description={sub}
                    onClick={() => startIntake(p)}
                    arrow
                  >
                    <span style={{ fontSize: FONT.md, fontWeight: 500 }}>
                      {p.name || "未命名"}
                    </span>
                  </List.Item>
                );
              })}
            </List>
          )}
          {patients.length === 0 && (
            <div
              style={{
                padding: "16px",
                textAlign: "center",
                fontSize: FONT.sm,
                color: APP.text4,
              }}
            >
              暂无患者记录
            </div>
          )}
        </div>
      </Popup>

      {/* Patient list — pull-to-refresh refetches both the patients list and
          the unseen-patient count so the 新 badges and 今日关注 row update
          together. Doctor doesn't have to wait for the 10s/30s polling. */}
      <div style={scrollable}>
        <PullToRefresh
          onRefresh={async () => {
            await Promise.all([
              refetch(),
              queryClient.invalidateQueries({ queryKey: QK.unseenPatientCount(doctorId) }),
            ]);
          }}
          pullingText="下拉刷新"
          canReleaseText="松开刷新"
          refreshingText="正在刷新…"
          completeText="已刷新"
        >
        {filtered.length === 0 && !isLoading && (
          search
            ? <EmptyState title="无匹配患者" description="试试其他关键词" />
            : <EmptyState title="暂无患者" description="点击右上角 + 新建第一位患者" action="新建病历" onAction={handleNewIntake} />
        )}

        {filtered.length > 0 && (
          <>
            {groups.pending.length > 0 && (
              <PatientSection
                title="待处理"
                badgeCount={groups.pending.length}
                patients={groups.pending}
                attentionMap={attentionMap}
                onPatientClick={handlePatientClick}
              />
            )}
            {groups.recent.length > 0 && (
              <PatientSection
                title="最近互动"
                patients={groups.recent}
                attentionMap={attentionMap}
                onPatientClick={handlePatientClick}
              />
            )}
            {groups.others.length > 0 && (
              <PatientSection
                title="全部患者"
                patients={groups.others}
                attentionMap={attentionMap}
                onPatientClick={handlePatientClick}
                collapsible={false}
              />
            )}
            <div
              style={{
                textAlign: "center",
                padding: "24px 16px 48px",
                fontSize: FONT.sm,
                color: APP.text4,
              }}
            >
              共 {patients.length} 位患者
            </div>
          </>
        )}
        </PullToRefresh>
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
  pickerHeader: {
    padding: "14px 16px 10px",
    fontSize: FONT.md,
    fontWeight: 600,
    color: APP.text1,
    borderBottom: `0.5px solid ${APP.border}`,
    flexShrink: 0,
  },
  pickerBody: {
    overflowY: "auto",
    paddingBottom: 8,
  },
  pickerNewRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    cursor: "pointer",
    borderBottom: `0.5px solid ${APP.border}`,
  },
  pickerNewIcon: {
    width: 36,
    height: 36,
    borderRadius: "50%",
    background: APP.primaryLight,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
};
