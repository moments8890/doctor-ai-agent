import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import PeopleOutlineOutlinedIcon from "@mui/icons-material/PeopleOutlineOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PsychologyAltOutlinedIcon from "@mui/icons-material/PsychologyAltOutlined";
import LabelOutlinedIcon from "@mui/icons-material/LabelOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import TextSnippetOutlinedIcon from "@mui/icons-material/TextSnippetOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import { getAdminTableRows, getAdminTables } from "../api";
import { t } from "../i18n";

const TABLES = [
  { key: "patients", icon: <PeopleOutlineOutlinedIcon fontSize="small" /> },
  { key: "medical_records", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { key: "doctor_tasks", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { key: "neuro_cases", icon: <PsychologyAltOutlinedIcon fontSize="small" /> },
  { key: "patient_labels", icon: <LabelOutlinedIcon fontSize="small" /> },
  { key: "patient_label_assignments", icon: <LinkOutlinedIcon fontSize="small" /> },
  { key: "system_prompts", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "doctor_contexts", icon: <AccountTreeOutlinedIcon fontSize="small" /> },
];

function NavTab({ active, onClick, icon, children }) {
  return (
    <Button
      variant={active ? "contained" : "outlined"}
      onClick={onClick}
      startIcon={icon}
      sx={{ justifyContent: "flex-start", borderRadius: 2, width: "100%", minHeight: 42 }}
    >
      {children}
    </Button>
  );
}

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const COL_WIDTH = {
  id: 64,
  key: 140,
  patient_id: 84,
  doctor_id: 144,
  patient_name: 112,
  name: 112,
  gender: 72,
  year_of_birth: 88,
  chief_complaint: 220,
  diagnosis: 180,
  primary_diagnosis: 180,
  treatment_plan: 240,
  follow_up_plan: 220,
  title: 220,
  summary: 260,
  content: 320,
  created_at: 164,
  updated_at: 164,
  due_at: 164,
};

export default function AdminPage() {
  const [doctorId, setDoctorId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [activeTable, setActiveTable] = useState("patients");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [tableCounts, setTableCounts] = useState({});
  const [rows, setRows] = useState([]);

  const columns = useMemo(() => {
    const allKeys = [];
    for (const row of rows) {
      for (const key of Object.keys(row || {})) {
        if (!allKeys.includes(key)) allKeys.push(key);
      }
    }
    return allKeys;
  }, [rows]);

  const activeLabel = t(`admin.tables.${activeTable}`);
  const colCount = columns.length + 1;

  function escapeCsv(value) {
    const text = toCell(value).replace(/"/g, '""');
    return `"${text}"`;
  }

  function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    const payload = JSON.stringify(rows, null, 2);
    downloadFile(`${activeTable}.json`, payload, "application/json;charset=utf-8");
  }

  function exportCsv() {
    const head = columns.map((col) => escapeCsv(t(`admin.cols.${col}`))).join(",");
    const body = rows
      .map((row) => columns.map((col) => escapeCsv(row[col])).join(","))
      .join("\n");
    const csv = [head, body].filter(Boolean).join("\n");
    downloadFile(`${activeTable}.csv`, csv, "text/csv;charset=utf-8");
  }

  async function copyRow(row) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(row, null, 2));
      setStatus({ type: "success", text: t("admin.copySuccess") });
    } catch (error) {
      setStatus({ type: "error", text: t("admin.copyFailed", { message: error.message }) });
    }
  }

  async function loadTableList() {
    const data = await getAdminTables({
      doctorId: doctorId.trim(),
      patientName: patientName.trim(),
      dateFrom,
      dateTo,
    });
    const next = {};
    for (const item of data.items || []) {
      next[item.key] = item.count;
    }
    setTableCounts(next);
  }

  async function loadTableData(tableKey = activeTable) {
    const data = await getAdminTableRows({
      tableKey,
      doctorId: doctorId.trim(),
      patientName: patientName.trim(),
      dateFrom,
      dateTo,
      limit: 300,
    });
    setRows(data.items || []);
  }

  async function loadAll(tableKey = activeTable) {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      await Promise.all([loadTableList(), loadTableData(tableKey)]);
    } catch (error) {
      setStatus({ type: "error", text: t("admin.loadFailed", { message: error.message }) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll("patients");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "radial-gradient(1200px 640px at 92% -8%, rgba(15,118,110,0.16), transparent 65%), radial-gradient(900px 520px at -12% 108%, rgba(47,79,111,0.15), transparent 62%), #f3f7f8",
      }}
    >
      <Container maxWidth="xl" sx={{ py: 2.5 }}>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "300px minmax(0,1fr)" }, alignItems: "start" }}>
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("admin.pageTitle")}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("admin.pageSubtitle")}
                </Typography>
                <TextField size="small" label={t("admin.filters.doctorName")} value={doctorId} onChange={(e) => setDoctorId(e.target.value)} sx={{ mt: 1 }} fullWidth />
                <TextField size="small" label={t("admin.filters.patientName")} value={patientName} onChange={(e) => setPatientName(e.target.value)} sx={{ mt: 1 }} fullWidth />
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <TextField size="small" type="date" label={t("admin.filters.dateFrom")} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} fullWidth />
                  <TextField size="small" type="date" label={t("admin.filters.dateTo")} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} fullWidth />
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.8 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  {t("admin.navTitle")}
                </Typography>
                <Stack spacing={1}>
                  {TABLES.map((item) => (
                    <NavTab
                      key={item.key}
                      active={activeTable === item.key}
                      icon={item.icon}
                      onClick={() => {
                        setActiveTable(item.key);
                        loadAll(item.key);
                      }}
                    >
                      {t(`admin.tables.${item.key}`)}
                    </NavTab>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>
                  {t("admin.counts.title")}
                </Typography>
                <Stack spacing={0.4}>
                  {TABLES.map((item, idx) => (
                    <Box key={`cnt-${item.key}`}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between">
                        <Stack direction="row" spacing={0.8} alignItems="center">
                          <Box sx={{ color: "text.secondary", display: "grid", placeItems: "center" }}>{item.icon}</Box>
                          <Typography variant="body2" color="text.secondary">{t(`admin.tables.${item.key}`)}</Typography>
                        </Stack>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{tableCounts[item.key] || 0}</Typography>
                      </Stack>
                      {idx < TABLES.length - 1 ? <Divider sx={{ mt: 0.55 }} /> : null}
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>

          <Card sx={{ borderRadius: 1.5 }}>
            <CardContent>
              {!!status.text ? <Alert severity={status.type} sx={{ mb: 1.5 }}>{status.text}</Alert> : null}

              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.2 }}>
                <Stack direction="row" spacing={0.8} alignItems="center">
                  <StorageOutlinedIcon fontSize="small" />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{activeLabel}</Typography>
                </Stack>
                <Stack direction="row" spacing={0.8}>
                  <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportCsv} disabled={!rows.length}>
                    {t("admin.exportCsv")}
                  </Button>
                  <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportJson} disabled={!rows.length}>
                    {t("admin.exportJson")}
                  </Button>
                  <Button variant="contained" size="small" onClick={() => loadAll(activeTable)} disabled={loading}>
                    {loading ? t("common.loading") : t("admin.reload")}
                  </Button>
                </Stack>
              </Stack>

              <TableContainer
                sx={{
                  border: "1px solid #d8e3e8",
                  borderRadius: 1.5,
                  backgroundColor: "#f8fbfc",
                  maxHeight: "74vh",
                }}
              >
                <Table size="small" stickyHeader sx={{ tableLayout: "fixed", minWidth: 980 }}>
                  <TableHead>
                    <TableRow>
                      {columns.map((key) => (
                        <TableCell
                          key={`head-${key}`}
                          sx={{
                            fontWeight: 700,
                            color: "text.secondary",
                            whiteSpace: "nowrap",
                            width: COL_WIDTH[key] || 140,
                            maxWidth: COL_WIDTH[key] || 140,
                            backgroundColor: "#eef4f6",
                            px: 1,
                            py: 0.75,
                            fontSize: 12,
                          }}
                        >
                          {t(`admin.cols.${key}`)}
                        </TableCell>
                      ))}
                      <TableCell sx={{ width: 56, maxWidth: 56, backgroundColor: "#eef4f6", px: 0.5, py: 0.75 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row, rowIdx) => (
                      <TableRow key={`row-${row.id ?? row.key ?? rowIdx}`} hover>
                        {columns.map((key) => (
                          <TableCell
                            key={`cell-${rowIdx}-${key}`}
                            sx={{
                              verticalAlign: "top",
                              borderBottom: "1px solid #e4edf0",
                              width: COL_WIDTH[key] || 140,
                              maxWidth: COL_WIDTH[key] || 140,
                              py: 0.45,
                              px: 1,
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
                              fontSize: 12,
                              lineHeight: 1.35,
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {toCell(row[key])}
                          </TableCell>
                        ))}
                        <TableCell sx={{ py: 0.2, px: 0.2, borderBottom: "1px solid #e4edf0", verticalAlign: "top" }}>
                          <IconButton size="small" onClick={() => copyRow(row)} title={t("admin.copyRow")}>
                            <ContentCopyOutlinedIcon sx={{ fontSize: 15 }} />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                    {!rows.length ? (
                      <TableRow>
                        <TableCell colSpan={colCount} sx={{ py: 1.2 }}>
                          <Typography color="text.secondary">{t("admin.empty")}</Typography>
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}
