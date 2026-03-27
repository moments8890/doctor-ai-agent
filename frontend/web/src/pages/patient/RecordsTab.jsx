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
import { useNavigate } from "react-router-dom";
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

export default function RecordsTab({ token, onNewRecord, urlSubpage }) {
  const navigate = useNavigate();
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
        <Box sx={{ bgcolor: COLOR.white }}>
          {records.map(rec => {
            const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
            const chief = rec.structured?.chief_complaint;
            const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 40) || "";
            const title = preview ? `${typeLabel} · ${preview}` : typeLabel;
            const ds = rec.diagnosis_status;
            const dsLabel = ds ? _DL[ds] : null;
            return (
              <ListCard
                key={rec.id}
                avatar={<DateAvatar date={rec.created_at} />}
                title={title}
                subtitle={dsLabel ? dsLabel : undefined}
                right={dsLabel ? <StatusBadge label={dsLabel} colorMap={_DC} fallbackColor={COLOR.text4} /> : undefined}
                chevron
                onClick={() => navigate(`/patient/records/${rec.id}`)}
              />
            );
          })}
        </Box>
      )}
    </Box>
  );
}
