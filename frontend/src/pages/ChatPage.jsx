import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDoctorStore } from "../store/doctorStore";
import { setWebToken } from "../api";
import {
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ChatBubbleOutlineRoundedIcon from "@mui/icons-material/ChatBubbleOutlineRounded";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import { Link as RouterLink } from "react-router-dom";
import { sendChat } from "../api";
import FeatureChangelog from "../components/FeatureChangelog";
import RecordFields from "../components/RecordFields";
import { t } from "../i18n";

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Paper
      elevation={0}
      sx={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        maxWidth: "min(92%, 760px)",
        p: 1.5,
        borderRadius: 1,
        bgcolor: isUser ? "#eaf4ff" : "#eefaf4",
        borderColor: isUser ? "#c8def6" : "#c9e8d4",
      }}
    >
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
        {msg.content}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        {msg.ts || "-"}
      </Typography>
      {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
    </Paper>
  );
}

export default function ChatPage() {
  const navigate = useNavigate();
  const { doctorId, doctorName, clearAuth } = useDoctorStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);

  function onLogout() {
    setWebToken("");
    clearAuth();
    navigate("/login", { replace: true });
  }

  function nowTs() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  function historyKey(name) {
    return `doctor_ai_chat_history:${(name || "anon").trim() || "anon"}`;
  }

  useEffect(() => {
    const raw = localStorage.getItem(historyKey(doctorId));
    if (!raw) {
      setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length) {
        setMessages(parsed);
      } else {
        setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
      }
    } catch {
      setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  useEffect(() => {
    if (!messages.length) return;
    localStorage.setItem(historyKey(doctorId), JSON.stringify(messages));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, doctorId]);

  const history = useMemo(
    () => messages.map((m) => ({ role: m.role, content: m.content })),
    [messages]
  );

  const assistantCount = useMemo(
    () => messages.filter((m) => m.role === "assistant").length,
    [messages]
  );

  const chatStats = [
    { key: "totalTurns", label: t("chat.stats.totalTurns"), value: messages.length, icon: <ChatBubbleOutlineRoundedIcon fontSize="small" /> },
    { key: "assistantTurns", label: t("chat.stats.assistantTurns"), value: assistantCount, icon: <SmartToyOutlinedIcon fontSize="small" /> },
    { key: "doctorTag", label: t("chat.stats.doctorTag"), value: doctorName || doctorId || "-", icon: <MedicalServicesOutlinedIcon fontSize="small" /> },
  ];

  async function onSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);

    try {
      const data = await sendChat({
        text,
        doctor_id: doctorId,
        history,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply || t("chat.received"), record: data.record || null, ts: nowTs() },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: t("chat.requestFailed", { message: error.message }), ts: nowTs() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "radial-gradient(1200px 640px at 92% -8%, rgba(15,118,110,0.16), transparent 65%), radial-gradient(900px 520px at -12% 108%, rgba(47,79,111,0.15), transparent 62%), #f3f7f8",
      }}
    >
      <Container maxWidth="xl" sx={{ py: 2.5 }}>
        <Card sx={{ borderRadius: 1.5, mb: 1.5 }}>
          <CardContent sx={{ py: "10px !important", px: 1.2 }}>
            <Stack direction="row" spacing={1} sx={{ width: "100%" }}>
              <Button component={RouterLink} to="/" variant="contained" size="small" disabled startIcon={<ForumOutlinedIcon fontSize="small" />} sx={{ flex: 1 }}>
                {t("nav.openChat")}
              </Button>
              <Button component={RouterLink} to="/manage" variant="outlined" size="small" startIcon={<DashboardOutlinedIcon fontSize="small" />} sx={{ flex: 1 }}>
                {t("nav.openManage")}
              </Button>
            </Stack>
          </CardContent>
        </Card>

        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns: { xs: "1fr", lg: "300px minmax(0, 1fr)" },
            alignItems: "start",
          }}
        >
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("chat.pageTitle")}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("chat.pageSubtitle")}
                </Typography>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    {t("login.loggedInAs")}：<strong>{doctorName || doctorId}</strong>
                  </Typography>
                  <Button size="small" color="inherit" onClick={onLogout} sx={{ ml: 1, flexShrink: 0 }}>
                    {t("login.logout")}
                  </Button>
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>
                  {t("chat.stats.title")}
                </Typography>
                <Stack spacing={0.4}>
                  {chatStats.map((row, idx) => (
                    <Box key={row.key}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between">
                        <Stack direction="row" spacing={0.8} alignItems="center">
                          <Box sx={{ color: "text.secondary", display: "grid", placeItems: "center" }}>{row.icon}</Box>
                          <Typography variant="body2" color="text.secondary">{row.label}</Typography>
                        </Stack>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{row.value}</Typography>
                      </Stack>
                      {idx < chatStats.length - 1 ? <Divider sx={{ mt: 0.55 }} /> : null}
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <FeatureChangelog />
          </Stack>

          <Paper sx={{ p: 2, minHeight: "88vh", display: "flex", flexDirection: "column", borderRadius: 1.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
              {t("chat.workspaceTitle")}
            </Typography>

            <Stack spacing={1.2} sx={{ flex: 1, overflowY: "auto", pr: 1 }}>
              {messages.map((msg, idx) => (
                <MsgBubble key={`${msg.role}-${idx}`} msg={msg} />
              ))}
            </Stack>

            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 2 }}>
              <TextField
                multiline
                minRows={2}
                maxRows={6}
                fullWidth
                placeholder={t("chat.placeholder")}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
              />
              <Button variant="contained" onClick={onSend} disabled={loading} sx={{ borderRadius: 1.5, minWidth: { sm: 110 } }}>
                {loading ? t("chat.sending") : t("chat.send")}
              </Button>
            </Stack>
          </Paper>
        </Box>
      </Container>
    </Box>
  );
}
