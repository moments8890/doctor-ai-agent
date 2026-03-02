import { useEffect, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { getPatientTimeline, getPatients, getPrompts, getRecords, updatePrompt } from "../api";

export default function ManagePage() {
  const [doctorId, setDoctorId] = useState("web_doctor");
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [patientFilter, setPatientFilter] = useState("");
  const [patients, setPatients] = useState([]);
  const [records, setRecords] = useState([]);
  const [basePrompt, setBasePrompt] = useState("");
  const [extPrompt, setExtPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [riskFilter, setRiskFilter] = useState("");
  const [followUpFilter, setFollowUpFilter] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [timeline, setTimeline] = useState([]);

  async function loadAll() {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      const [p, r, prompts] = await Promise.all([
        getPatients(doctorId.trim() || "web_doctor", {
          risk: riskFilter,
          followUpState: followUpFilter,
        }),
        getRecords({ doctorId: doctorId.trim() || "web_doctor", patientId: patientFilter.trim() }),
        getPrompts(),
      ]);
      setPatients(p.items || []);
      setRecords(r.items || []);
      setBasePrompt(prompts.structuring || "");
      setExtPrompt(prompts.structuring_extension || "");
    } catch (error) {
      setStatus({ type: "error", text: `Load failed: ${error.message}` });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskFilter, followUpFilter]);

  async function savePrompt(key, content) {
    try {
      await updatePrompt(key, content);
      setStatus({ type: "success", text: `${key} saved.` });
    } catch (error) {
      setStatus({ type: "error", text: `Save failed: ${error.message}` });
    }
  }

  function formatRawValue(value) {
    if (value === null || value === undefined) return "null";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  async function loadTimeline(patientId) {
    if (!patientId) return;
    try {
      const data = await getPatientTimeline({
        doctorId: doctorId.trim() || "web_doctor",
        patientId,
        limit: 100,
      });
      setTimeline(data.events || []);
    } catch (error) {
      setStatus({ type: "error", text: `Timeline load failed: ${error.message}` });
      setTimeline([]);
    }
  }

  return (
    <Box sx={{ minHeight: "100vh", background: "linear-gradient(165deg, #edf3f9 0%, #f6f0e7 100%)" }}>
      <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: "1px solid #d8e1e3" }}>
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Doctor Management (MUI)
          </Typography>
          <Button component={RouterLink} to="/" variant="outlined">
            Open Chat
          </Button>
          <TextField
            size="small"
            label="Doctor ID"
            value={doctorId}
            onChange={(e) => setDoctorId(e.target.value)}
          />
          <Button variant="contained" onClick={loadAll} disabled={loading}>
            {loading ? "Loading..." : "Reload"}
          </Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 2 }}>
        {!!status.text ? <Alert severity={status.type}>{status.text}</Alert> : null}
        <Card sx={{ mt: 2 }}>
          <CardContent>
            <Tabs value={tab} onChange={(_, v) => setTab(v)}>
              <Tab label={`Patients (${patients.length})`} />
              <Tab label={`Records (${records.length})`} />
              <Tab label="Customization" />
            </Tabs>
          </CardContent>
        </Card>

        {tab === 0 ? (
          <Stack spacing={1.25} sx={{ mt: 2 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel id="risk-filter-label">Risk</InputLabel>
                <Select
                  labelId="risk-filter-label"
                  label="Risk"
                  value={riskFilter}
                  onChange={(e) => setRiskFilter(e.target.value)}
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="critical">critical</MenuItem>
                  <MenuItem value="high">high</MenuItem>
                  <MenuItem value="medium">medium</MenuItem>
                  <MenuItem value="low">low</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="followup-filter-label">Follow-up</InputLabel>
                <Select
                  labelId="followup-filter-label"
                  label="Follow-up"
                  value={followUpFilter}
                  onChange={(e) => setFollowUpFilter(e.target.value)}
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="not_needed">not_needed</MenuItem>
                  <MenuItem value="scheduled">scheduled</MenuItem>
                  <MenuItem value="due_soon">due_soon</MenuItem>
                  <MenuItem value="overdue">overdue</MenuItem>
                </Select>
              </FormControl>
            </Stack>
            {patients.map((p) => (
              <Card key={p.id}>
                <CardContent>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                    <Typography variant="subtitle1">{p.name}</Typography>
                    {p.primary_category ? <Chip size="small" label={`cat:${p.primary_category}`} /> : null}
                    {p.primary_risk_level ? <Chip size="small" color="warning" label={`risk:${p.primary_risk_level}`} /> : null}
                    {p.follow_up_state ? <Chip size="small" variant="outlined" label={`f/u:${p.follow_up_state}`} /> : null}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    id={p.id} | {p.gender || "unknown"} | {p.year_of_birth ? `${new Date().getFullYear() - p.year_of_birth}y` : "age n/a"} | records={p.record_count}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    risk_score={p.risk_score ?? "-"} | risk_rules={p.risk_rules_version || "-"} | risk_at={p.risk_computed_at || "-"}
                  </Typography>
                  <br />
                  <Typography variant="caption" color="text.secondary">
                    created: {p.created_at || "-"}
                  </Typography>
                  <Box sx={{ mt: 1 }}>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => {
                        setTab(1);
                        setPatientFilter(String(p.id));
                        setSelectedPatientId(String(p.id));
                        loadTimeline(p.id);
                      }}
                    >
                      Filter records by this patient
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            ))}
            {!patients.length ? <Typography color="text.secondary">No patients yet.</Typography> : null}
          </Stack>
        ) : null}

        {tab === 1 ? (
          <Box sx={{ mt: 2 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 1.5 }}>
              <TextField
                size="small"
                label="Patient ID filter"
                value={patientFilter}
                onChange={(e) => setPatientFilter(e.target.value)}
              />
              <Button variant="outlined" onClick={loadAll}>
                Apply
              </Button>
            </Stack>
            <Stack spacing={1.25}>
              {records.map((r) => (
                <Card key={r.id}>
                  <CardContent>
                    <Typography variant="subtitle1">record_id={r.id}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      raw field view
                    </Typography>
                    <Box
                      sx={{
                        mt: 1.2,
                        p: 1.25,
                        borderRadius: 1.5,
                        border: "1px solid #d8e1e3",
                        backgroundColor: "#fafcfd",
                        fontFamily: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
                        fontSize: "0.8rem",
                      }}
                    >
                      {Object.entries(r).map(([key, value]) => (
                        <Typography
                          key={key}
                          component="div"
                          sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                        >
                          {key}: {formatRawValue(value)}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              ))}
              {!records.length ? <Typography color="text.secondary">No records found.</Typography> : null}
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle1">Patient Timeline (Debug)</Typography>
            {!selectedPatientId ? (
              <Typography color="text.secondary">Select a patient from Patients tab to load timeline.</Typography>
            ) : null}
            <Stack spacing={1}>
              {timeline.map((e) => (
                <Card key={`${e.type}-${e.id}`}>
                  <CardContent>
                    <Typography variant="subtitle2">
                      {e.type} #{e.id}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {e.timestamp || "-"}
                    </Typography>
                    <Box
                      sx={{
                        mt: 1.2,
                        p: 1.25,
                        borderRadius: 1.5,
                        border: "1px solid #d8e1e3",
                        backgroundColor: "#fafcfd",
                        fontFamily: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
                        fontSize: "0.8rem",
                      }}
                    >
                      {Object.entries(e.payload || {}).map(([key, value]) => (
                        <Typography
                          key={key}
                          component="div"
                          sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                        >
                          {key}: {formatRawValue(value)}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              ))}
              {selectedPatientId && !timeline.length ? (
                <Typography color="text.secondary">No timeline events yet.</Typography>
              ) : null}
            </Stack>
          </Box>
        ) : null}

        {tab === 2 ? (
          <Stack spacing={1.5} sx={{ mt: 2 }}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1">structuring</Typography>
                <TextField
                  multiline
                  minRows={8}
                  fullWidth
                  value={basePrompt}
                  onChange={(e) => setBasePrompt(e.target.value)}
                  sx={{ mt: 1 }}
                />
                <Button sx={{ mt: 1 }} variant="contained" onClick={() => savePrompt("structuring", basePrompt)}>
                  Save Base Prompt
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <Typography variant="subtitle1">structuring.extension</Typography>
                <TextField
                  multiline
                  minRows={8}
                  fullWidth
                  value={extPrompt}
                  onChange={(e) => setExtPrompt(e.target.value)}
                  sx={{ mt: 1 }}
                />
                <Button
                  sx={{ mt: 1 }}
                  variant="contained"
                  onClick={() => savePrompt("structuring.extension", extPrompt)}
                >
                  Save Extension Prompt
                </Button>
              </CardContent>
            </Card>
          </Stack>
        ) : null}
      </Container>
    </Box>
  );
}
