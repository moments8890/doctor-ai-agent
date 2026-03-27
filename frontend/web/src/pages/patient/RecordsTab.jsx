/**
 * RecordsTab — patient record list + new-record entry point.
 *
 * Extracted from PatientPage.jsx. Shows:
 *  - NewItemCard for creating a new record (starts interview)
 *  - List view or timeline view toggle
 *  - When urlSubpage is a numeric record ID, renders RecordDetail instead
 *
 * Props:
 *  - token: string — patient auth token
 *  - onNewRecord: () => void — callback to start new record / interview
 *  - urlSubpage: string | undefined — from route param :subpage
 */

import { useEffect, useState, useCallback } from "react";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { Box, CircularProgress, Typography } from "@mui/material";
import { usePatientApi } from "../../api/PatientApiContext";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import RecordAvatar from "../../components/RecordAvatar";
import DateAvatar from "../../components/DateAvatar";
import StatusBadge from "../../components/StatusBadge";
import { TYPE, COLOR } from "../../theme";
import { RECORD_TYPE_LABEL, formatDate } from "./constants";
import RecordDetail from "./subpages/RecordDetail";

const _DL = { pending: "诊断中", completed: "待审核", confirmed: "已确认", failed: "诊断失败" };
const _DC = { "诊断中": COLOR.warning, "待审核": COLOR.accent, "已确认": COLOR.success, "诊断失败": COLOR.danger };

const RECORD_TYPE_ICON_COLOR = {
  visit: COLOR.primary,
  interview_summary: COLOR.accent,
  import: COLOR.text4,
  dictation: COLOR.warning,
};

function groupByMonth(records) {
  const groups = [];
  let currentKey = "";
  for (const rec of records) {
    const d = new Date(rec.created_at);
    const key = `${d.getFullYear()}年${d.getMonth() + 1}月`;
    if (key !== currentKey) {
      currentKey = key;
      groups.push({ label: key, items: [] });
    }
    groups[groups.length - 1].items.push(rec);
  }
  return groups;
}

function TimelineView({ records, navigate }) {
  const groups = groupByMonth(records);
  return (
    <Box sx={{ px: 2, py: 1 }}>
      {groups.map((group) => (
        <Box key={group.label}>
          {/* Month header */}
          <Typography sx={{
            fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text3,
            mb: 1, mt: 1.5,
          }}>
            {group.label}
          </Typography>

          {/* Timeline items with vertical line */}
          <Box sx={{ position: "relative", pl: 3 }}>
            {/* Vertical connecting line */}
            <Box sx={{
              position: "absolute", left: 7, top: 8, bottom: 8,
              width: 2, bgcolor: COLOR.borderLight, borderRadius: 1,
            }} />

            {group.items.map((rec, idx) => {
              const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
              const chief = rec.structured?.chief_complaint;
              const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 30) || "";
              const ds = rec.diagnosis_status;
              const dsLabel = ds ? _DL[ds] : null;
              const dotColor = RECORD_TYPE_ICON_COLOR[rec.record_type] || COLOR.text4;
              const d = new Date(rec.created_at);
              const dayStr = `${d.getMonth() + 1}/${d.getDate()}`;
              const diagnosis = rec.structured?.diagnosis;

              return (
                <Box key={rec.id}
                  onClick={() => navigate(`/patient/records/${rec.id}`)}
                  sx={{
                    position: "relative", mb: idx < group.items.length - 1 ? 1.5 : 0,
                    cursor: "pointer", "&:active": { opacity: 0.7 },
                  }}
                >
                  {/* Timeline dot */}
                  <Box sx={{
                    position: "absolute", left: -24, top: 6,
                    width: 12, height: 12, borderRadius: "50%",
                    bgcolor: dotColor, border: "2px solid #fff",
                    boxShadow: `0 0 0 1.5px ${dotColor}40`,
                    zIndex: 1,
                  }} />

                  {/* Card */}
                  <Box sx={{
                    bgcolor: "#fff", borderRadius: "8px", px: 1.5, py: 1,
                    border: `0.5px solid ${COLOR.borderLight}`,
                  }}>
                    {/* Top row: type + date */}
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.3 }}>
                      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: dotColor, fontWeight: 600 }}>
                        {typeLabel}
                      </Typography>
                      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                        {dayStr}
                      </Typography>
                    </Box>

                    {/* Chief complaint */}
                    {preview && (
                      <Typography sx={{
                        fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.text1,
                        lineHeight: 1.4, mb: 0.3,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {preview}
                      </Typography>
                    )}

                    {/* Bottom row: diagnosis + status badge */}
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      {diagnosis ? (
                        <Typography sx={{
                          fontSize: TYPE.secondary.fontSize, color: COLOR.text3,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, mr: 1,
                        }}>
                          {diagnosis}
                        </Typography>
                      ) : <Box />}
                      {dsLabel && <StatusBadge label={dsLabel} colorMap={_DC} fallbackColor={COLOR.text4} />}
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export default function RecordsTab({ token, onNewRecord, urlSubpage }) {
  const navigate = useAppNavigate();
  const { getPatientRecords } = usePatientApi();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [recordView, setRecordView] = useState("list"); // "list" or "timeline"

  const loadRecords = useCallback(() => {
    setLoading(true);
    getPatientRecords(token).then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, getPatientRecords]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  // URL-driven record detail: /patient/records/:recordId
  if (urlSubpage && urlSubpage !== "interview") {
    return (
      <RecordDetail
        recordId={urlSubpage}
        token={token}
        onBack={() => navigate("/patient/records")}
      />
    );
  }

  if (loading) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={20} /></Box>;
  }

  return (
    <Box sx={{ flex: 1, overflowY: "auto", position: "relative" }}>
      {/* New record row */}
      <NewItemCard title="新建病历" subtitle="开始AI预问诊" onClick={onNewRecord} />

      {/* Section label + view toggle */}
      {records.length > 0 && (
        <>
          <Box sx={{ px: 2, py: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>
              最近 · {records.length}份病历
            </Typography>
          </Box>
          <Box sx={{ display: "flex", gap: 0.8, px: 2, py: 1 }}>
            {[{ key: "list", label: "病历" }, { key: "timeline", label: "时间线" }].map(v => (
              <Box
                key={v.key}
                onClick={() => setRecordView(v.key)}
                sx={{
                  px: 1.5, py: 0.4, borderRadius: "4px", cursor: "pointer",
                  fontSize: TYPE.secondary.fontSize, fontWeight: recordView === v.key ? 600 : 400,
                  bgcolor: recordView === v.key ? COLOR.primary : COLOR.white,
                  color: recordView === v.key ? COLOR.white : COLOR.text3,
                  border: recordView === v.key ? "none" : `0.5px solid ${COLOR.border}`,
                }}
              >
                {v.label}
              </Box>
            ))}
          </Box>
        </>
      )}

      {/* Record list */}
      {records.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <Typography color="text.secondary">暂无病历记录</Typography>
          <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: "block" }}>
            点击上方「新建病历」开始预问诊
          </Typography>
        </Box>
      ) : recordView === "list" ? (
        <Box sx={{ bgcolor: "#fff" }}>
          {records.map(rec => {
            const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
            const chief = rec.structured?.chief_complaint;
            const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 40) || "（内容为空）";
            const ds = rec.diagnosis_status;
            const dsLabel = ds ? _DL[ds] : null;
            return (
              <ListCard
                key={rec.id}
                avatar={<RecordAvatar type={rec.record_type} />}
                title={typeLabel}
                subtitle={preview}
                right={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                    {dsLabel && (
                      <StatusBadge label={dsLabel} colorMap={_DC} fallbackColor={COLOR.text4} />
                    )}
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{formatDate(rec.created_at)}</Typography>
                  </Box>
                }
                onClick={() => navigate(`/patient/records/${rec.id}`)}
              />
            );
          })}
        </Box>
      ) : (
        <TimelineView records={records} navigate={navigate} />
      )}
    </Box>
  );
}
