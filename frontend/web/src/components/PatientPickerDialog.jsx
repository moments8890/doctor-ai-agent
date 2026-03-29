import { useState, useEffect, useRef, useCallback } from "react";
import {
  Box, CircularProgress, Dialog, DialogTitle, IconButton,
  InputAdornment, TextField, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import SearchIcon from "@mui/icons-material/Search";
import { useApi } from "../api/ApiContext";
import ListCard from "./ListCard";
import NameAvatar from "./NameAvatar";
import SectionLabel from "./SectionLabel";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

function formatPatientTime(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (dt.getTime() === today.getTime()) return `今天 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (dt.getTime() === yesterday.getTime()) return "昨天";
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

function getPatientAge(patient) {
  if (patient.age != null) return patient.age;
  if (patient.year_of_birth) return new Date().getFullYear() - patient.year_of_birth;
  return null;
}

function getPatientSubtitle(patient) {
  const age = getPatientAge(patient);
  return [
    patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
    age != null ? `${age}岁` : null,
    patient.chief_complaint || patient.primary_category || (patient.record_count != null ? `${patient.record_count}份病历` : null),
  ].filter(Boolean).join(" · ");
}

function PatientPickerRow({ patient, onClick }) {
  const timeStr = formatPatientTime(patient.updated_at || patient.created_at);
  return (
    <ListCard
      avatar={<NameAvatar name={patient.name} size={36} />}
      title={patient.name}
      subtitle={getPatientSubtitle(patient)}
      right={timeStr ? <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{timeStr}</Typography> : null}
      onClick={onClick}
    />
  );
}

export default function PatientPickerDialog({ open, onClose, doctorId, onSelect }) {
  const { getPatients, searchPatients } = useApi();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const [query, setQuery] = useState("");
  const [patients, setPatients] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const loadRecent = useCallback(() => {
    setLoading(true);
    getPatients(doctorId, {}, 50)
      .then((data) => setPatients(data.items || []))
      .catch(() => setPatients([]))
      .finally(() => setLoading(false));
  }, [doctorId]);

  const doSearch = useCallback((q) => {
    if (!q.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    searchPatients(doctorId, q.trim())
      .then((data) => setResults(data.items || []))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  }, [doctorId]);

  useEffect(() => {
    if (!open) return;
    loadRecent();
  }, [open, loadRecent]);

  useEffect(() => {
    clearTimeout(timerRef.current);
    if (!query.trim()) {
      setResults([]);
      return () => clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => doSearch(query), 300);
    return () => clearTimeout(timerRef.current);
  }, [query, doSearch]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  const handleSelect = (patient) => {
    onSelect({ id: patient.id, name: patient.name });
    onClose();
  };

  const trimmedQuery = query.trim();
  const visibleItems = trimmedQuery ? results : patients;
  const sectionLabel = trimmedQuery ? `匹配 · ${visibleItems.length}位患者` : `最近 · ${visibleItems.length}位患者`;
  const emptyText = trimmedQuery ? `未找到患者「${trimmedQuery}」` : "暂无患者档案";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={fullScreen}
      fullWidth
      maxWidth="xs"
      PaperProps={{ sx: { borderRadius: fullScreen ? 0 : RADIUS.sm, display: "flex", flexDirection: "column", maxHeight: "80vh", bgcolor: COLOR.surfaceAlt } }}
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pb: 1 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>选择患者</Typography>
        <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </DialogTitle>

      <Box sx={{ px: 1.5, pb: 1, bgcolor: COLOR.surfaceAlt }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          placeholder="输入姓名搜索患者"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                {loading && trimmedQuery ? <CircularProgress size={14} /> : <SearchIcon fontSize="small" />}
              </InputAdornment>
            ),
          }}
          sx={{
            "& .MuiOutlinedInput-root": {
              borderRadius: RADIUS.sm,
              bgcolor: COLOR.white,
              "& fieldset": { borderColor: "#e0e0e0" },
              "&.Mui-focused fieldset": { borderColor: COLOR.primary },
            },
          }}
        />
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt }}>
        {!loading && (
          <SectionLabel sx={{ bgcolor: COLOR.surface, borderTop: `0.5px solid ${COLOR.borderLight}`, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            {sectionLabel}
          </SectionLabel>
        )}
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={28} sx={{ color: COLOR.primary }} />
          </Box>
        ) : visibleItems.length > 0 ? (
          visibleItems.map((patient) => (
            <PatientPickerRow key={patient.id} patient={patient} onClick={() => handleSelect(patient)} />
          ))
        ) : (
          <Typography sx={{ textAlign: "center", py: 6, color: COLOR.text4, fontSize: TYPE.body.fontSize }}>
            {emptyText}
          </Typography>
        )}
      </Box>
    </Dialog>
  );
}
