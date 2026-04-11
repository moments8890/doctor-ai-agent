/**
 * TeachByExampleSubpage — paste a sample response and let AI extract style rules.
 */
import { useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import AppButton from "../../../components/AppButton";
import { useApi } from "../../../api/ApiContext";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useDoctorStore } from "../../../store/doctorStore";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

export default function TeachByExampleSubpage({ onBack, isMobile }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [extracted, setExtracted] = useState(null); // null = not submitted yet

  async function handleSubmit() {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setExtracted(null);
    try {
      const result = await api.teachByExample(doctorId, text.trim());
      setExtracted(result.extracted || []);
      if (result.count > 0) {
        queryClient.invalidateQueries({ queryKey: QK.personaPending(doctorId) });
      }
    } catch {
      setError("分析失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageSkeleton title="教AI新偏好" onBack={onBack} isMobile={isMobile} listPane={
      <Box sx={{ px: 2, py: 2, flex: 1, overflowY: "auto" }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 1.5, lineHeight: 1.6 }}>
          粘贴一段你满意的回复，AI会自动分析其中的风格偏好，添加到待确认队列。
        </Typography>

        <TextField
          fullWidth
          multiline
          minRows={6}
          maxRows={12}
          placeholder="粘贴一段你满意的回复示例…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={loading}
          inputProps={{ maxLength: 2000 }}
          sx={{ mb: 0.5 }}
        />
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "right", mb: 1.5 }}>
          {text.length} / 2000
        </Typography>

        <AppButton
          variant="primary"
          size="md"
          fullWidth
          disabled={!text.trim() || loading}
          loading={loading}
          loadingLabel="分析中…"
          onClick={handleSubmit}
        >
          开始分析
        </AppButton>

        {error && (
          <Typography sx={{ color: COLOR.danger, fontSize: TYPE.secondary.fontSize, mt: 1.5 }}>
            {error}
          </Typography>
        )}

        {extracted !== null && (
          <Box sx={{ mt: 2 }}>
            {extracted.length === 0 ? (
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4, textAlign: "center", py: 2 }}>
                未发现明显的风格偏好，请尝试粘贴更完整的回复
              </Typography>
            ) : (
              <>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 1 }}>
                  发现 {extracted.length} 条偏好，已添加到待确认队列：
                </Typography>
                {extracted.map((r, i) => (
                  <Box key={i} sx={{ display: "flex", gap: 1.25, mb: 1, alignItems: "flex-start" }}>
                    <CheckCircleOutlinedIcon sx={{ fontSize: 18, color: COLOR.success, mt: 0.25, flexShrink: 0 }} />
                    <Box>
                      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                        {FIELD_LABELS[r.field] || r.field}
                      </Typography>
                      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>{r.text}</Typography>
                    </Box>
                  </Box>
                ))}
              </>
            )}
          </Box>
        )}
      </Box>
    } />
  );
}
