import { useEffect, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Stack,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { getPatients, getPrompts, getRecords, updatePrompt } from "../api";

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

  async function loadAll() {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      const [p, r, prompts] = await Promise.all([
        getPatients(doctorId.trim() || "web_doctor"),
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

  async function savePrompt(key, content) {
    try {
      await updatePrompt(key, content);
      setStatus({ type: "success", text: `${key} saved.` });
    } catch (error) {
      setStatus({ type: "error", text: `Save failed: ${error.message}` });
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
            {patients.map((p) => (
              <Card key={p.id}>
                <CardContent>
                  <Typography variant="subtitle1">{p.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    id={p.id} | {p.gender || "unknown"} | {p.age ? `${p.age}y` : "age n/a"} | records={p.record_count}
                  </Typography>
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
                    <Typography variant="subtitle1">{r.patient_name || "Unlinked patient"}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      record_id={r.id} | created={r.created_at || "-"}
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <b>Chief:</b> {r.chief_complaint || "-"}
                    </Typography>
                    <Typography variant="body2">
                      <b>Diagnosis:</b> {r.diagnosis || "-"}
                    </Typography>
                    <Typography variant="body2">
                      <b>Treatment:</b> {r.treatment_plan || "-"}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
              {!records.length ? <Typography color="text.secondary">No records found.</Typography> : null}
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
