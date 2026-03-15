/**
 * 患者自助门户页面
 *
 * URL 示例：/patient?d=doctorId
 *
 * 未登录：显示姓名输入框，调用 POST /api/patient/session
 * 已登录：显示患者病历列表 + 消息输入框
 */

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import { patientSession, getPatientRecords, sendPatientMessage } from "../api";

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function recordTypeLabel(type) {
  const map = {
    visit: "门诊记录",
    dictation: "语音记录",
    import: "导入记录",
    interview_summary: "问诊小结",
  };
  return map[type] || type;
}

// ---------------------------------------------------------------------------
// Login panel
// ---------------------------------------------------------------------------

function LoginPanel({ doctorId, onLogin }) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入您的姓名");
      return;
    }
    if (!doctorId) {
      setError("链接缺少医生编号，请联系您的医生重新分享链接。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await patientSession(doctorId, trimmed);
      onLogin(data.token, data.patient_name);
    } catch (err) {
      if (err.status === 404) {
        setError("未找到匹配的患者记录，请确认姓名是否与您的医生档案一致。");
      } else {
        setError(err.message || "登录失败，请稍后重试。");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 2,
        background:
          "#ededed",
      }}
    >
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: 48, color: "primary.main" }} />
            <Typography variant="h6" fontWeight={700} textAlign="center">
              患者健康档案
            </Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              请输入您的姓名，查看您的诊疗记录
            </Typography>

            <Box component="form" onSubmit={handleSubmit} sx={{ width: "100%" }}>
              <Stack spacing={2}>
                <TextField
                  label="您的姓名"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                  fullWidth
                  size="small"
                  inputProps={{ autoComplete: "name" }}
                />
                {error && (
                  <Typography variant="body2" color="error">
                    {error}
                  </Typography>
                )}
                <Button
                  type="submit"
                  variant="contained"
                  fullWidth
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={16} color="inherit" /> : null}
                >
                  {loading ? "验证中…" : "查看我的档案"}
                </Button>
              </Stack>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Records panel
// ---------------------------------------------------------------------------

function RecordsPanel({ token, patientName, onLogout }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [sendLoading, setSendLoading] = useState(false);
  const [sendReply, setSendReply] = useState("");

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getPatientRecords(token);
      setRecords(Array.isArray(data) ? data : []);
    } catch (err) {
      if (err.status === 401) {
        onLogout();
        return;
      }
      setError("加载病历失败，请刷新页面重试。");
    } finally {
      setLoading(false);
    }
  }, [token, onLogout]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  async function handleSend(e) {
    e.preventDefault();
    const text = message.trim();
    if (!text) return;
    setSendLoading(true);
    setSendReply("");
    try {
      const data = await sendPatientMessage(token, text);
      setSendReply(data.reply || "");
      setMessage("");
    } catch (err) {
      if (err.status === 401) {
        onLogout();
        return;
      }
      setSendReply("发送失败，请稍后重试。");
    } finally {
      setSendLoading(false);
    }
  }

  return (
    <Box sx={{ maxWidth: 600, mx: "auto", px: 2, py: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <MedicalServicesOutlinedIcon color="primary" />
          <Typography variant="h6" fontWeight={700}>
            {patientName} 的健康档案
          </Typography>
        </Stack>
        <Button size="small" color="inherit" onClick={onLogout}>
          退出
        </Button>
      </Stack>

      <Divider sx={{ mb: 2 }} />

      {/* Records */}
      <Typography variant="subtitle2" color="text.secondary" mb={1}>
        诊疗记录
      </Typography>

      {loading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress size={32} />
        </Box>
      )}

      {!loading && error && (
        <Typography color="error" variant="body2" mb={2}>
          {error}
        </Typography>
      )}

      {!loading && !error && records.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
          暂无诊疗记录
        </Typography>
      )}

      <Stack spacing={2} mb={3}>
        {records.map((rec) => (
          <Card key={rec.id} variant="outlined" sx={{ borderRadius: 2 }}>
            <CardContent sx={{ pb: "12px !important" }}>
              <Stack direction="row" justifyContent="space-between" mb={0.5}>
                <Typography variant="caption" color="text.secondary">
                  {recordTypeLabel(rec.record_type)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatDate(rec.created_at)}
                </Typography>
              </Stack>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {rec.content || "（内容为空）"}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Divider sx={{ mb: 2 }} />

      {/* Message form */}
      <Typography variant="subtitle2" color="text.secondary" mb={1}>
        向医生发送消息
      </Typography>
      <Box component="form" onSubmit={handleSend}>
        <Stack spacing={1.5}>
          <TextField
            multiline
            minRows={3}
            maxRows={8}
            fullWidth
            size="small"
            placeholder="请输入您的问题或病情描述…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          {sendReply && (
            <Card variant="outlined" sx={{ borderRadius: 2, bgcolor: "action.hover" }}>
              <CardContent sx={{ py: "8px !important", px: 2 }}>
                <Typography variant="body2">{sendReply}</Typography>
              </CardContent>
            </Card>
          )}
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={sendLoading || !message.trim()}
            startIcon={sendLoading ? <CircularProgress size={16} color="inherit" /> : null}
          >
            {sendLoading ? "发送中…" : "发送消息"}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

export default function PatientPage() {
  const [searchParams] = useSearchParams();
  const doctorId = searchParams.get("d") || "";

  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(
    () => localStorage.getItem(STORAGE_NAME_KEY) || ""
  );

  function handleLogin(newToken, name) {
    localStorage.setItem(STORAGE_KEY, newToken);
    localStorage.setItem(STORAGE_NAME_KEY, name);
    setToken(newToken);
    setPatientName(name);
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    setToken("");
    setPatientName("");
  }

  if (!token) {
    return <LoginPanel doctorId={doctorId} onLogin={handleLogin} />;
  }

  return (
    <RecordsPanel
      token={token}
      patientName={patientName}
      onLogout={handleLogout}
    />
  );
}
