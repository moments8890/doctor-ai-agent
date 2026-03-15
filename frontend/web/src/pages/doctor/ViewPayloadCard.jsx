/**
 * Structured data card for view_payload in chat messages.
 * Renders records_list, patients_list, and task_created payloads.
 */
import { Box, Typography } from "@mui/material";

export default function ViewPayloadCard({ payload }) {
  if (!payload || !payload.data) return null;
  const { type, data } = payload;

  if (type === "records_list" && Array.isArray(data)) {
    return (
      <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 1.5, bgcolor: "#f6f8fa", border: "1px solid #d0d7de" }}>
        <Typography variant="subtitle2" sx={{ color: "#0969da", mb: 1, fontSize: 12 }}>
          {data.length === 0 ? "暂无记录" : `${data.length} 条病历记录`}
        </Typography>
        {data.slice(0, 5).map((r, i) => (
          <Box key={r.id || i} sx={{ py: 0.5, borderBottom: i < Math.min(data.length, 5) - 1 ? "1px solid #eee" : "none" }}>
            <Typography variant="caption" sx={{ color: "#57606a", fontSize: 11 }}>
              {r.created_at ? new Date(r.created_at).toLocaleDateString("zh-CN") : ""} {r.record_type || ""}
            </Typography>
            <Typography variant="body2" sx={{ fontSize: 13, lineHeight: 1.6, mt: 0.3 }}>
              {(r.content || "").slice(0, 80)}{(r.content || "").length > 80 ? "..." : ""}
            </Typography>
          </Box>
        ))}
      </Box>
    );
  }

  if (type === "patients_list" && Array.isArray(data)) {
    return (
      <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 1.5, bgcolor: "#f6f8fa", border: "1px solid #d0d7de" }}>
        <Typography variant="subtitle2" sx={{ color: "#0969da", mb: 1, fontSize: 12 }}>
          {data.length === 0 ? "暂无患者" : `${data.length} 位患者`}
        </Typography>
        {data.map((p, i) => (
          <Typography key={p.id || i} variant="body2" sx={{ fontSize: 13, py: 0.3 }}>
            {p.name}{p.gender ? ` (${p.gender})` : ""}
          </Typography>
        ))}
      </Box>
    );
  }

  if (type === "task_created" && data) {
    return (
      <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 1.5, bgcolor: "#f0fdf4", border: "1px solid #bbf7d0" }}>
        <Typography variant="subtitle2" sx={{ color: "#16a34a", fontSize: 12 }}>
          {data.task_label || "任务"} 已创建
        </Typography>
        {data.datetime_display && (
          <Typography variant="body2" sx={{ fontSize: 13, mt: 0.3 }}>
            时间：{data.datetime_display}
          </Typography>
        )}
      </Box>
    );
  }

  return null;
}
