import { useMemo, useState } from "react";
import {
  AppBar,
  Box,
  Button,
  Container,
  Paper,
  Stack,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { sendChat } from "../api";
import RecordFields from "../components/RecordFields";

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Paper
      elevation={0}
      sx={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        maxWidth: "min(90%, 780px)",
        p: 1.5,
        bgcolor: isUser ? "#edf6ff" : "#effaf2",
        borderColor: isUser ? "#c7ddf8" : "#c7e8d0",
      }}
    >
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
        {msg.content}
      </Typography>
      {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
    </Paper>
  );
}

export default function ChatPage() {
  const [doctorId, setDoctorId] = useState("web_doctor");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello, you can ask me to create patients, save records, and query history.",
    },
  ]);

  const history = useMemo(
    () => messages.map((m) => ({ role: m.role, content: m.content })),
    [messages]
  );

  async function onSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const data = await sendChat({
        text,
        doctor_id: doctorId.trim() || "web_doctor",
        history,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply || "Received.", record: data.record || null },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Request failed: ${error.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box sx={{ minHeight: "100vh", background: "linear-gradient(145deg, #f4efe5 0%, #ddeceb 100%)" }}>
      <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: "1px solid #d8e1e3" }}>
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Doctor AI Chat (MUI)
          </Typography>
          <Button component={RouterLink} to="/manage" variant="outlined">
            Open Manage
          </Button>
          <TextField
            size="small"
            label="Doctor ID"
            value={doctorId}
            onChange={(e) => setDoctorId(e.target.value)}
          />
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 2 }}>
        <Paper sx={{ p: 2, minHeight: "72vh", display: "flex", flexDirection: "column" }}>
          <Stack spacing={1.25} sx={{ flex: 1, overflowY: "auto", pr: 1 }}>
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
              placeholder="Type clinical notes, patient creation command, or query..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
            />
            <Button variant="contained" onClick={onSend} disabled={loading}>
              {loading ? "Sending..." : "Send"}
            </Button>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
