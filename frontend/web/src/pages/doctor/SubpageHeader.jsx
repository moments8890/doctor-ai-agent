/**
 * 统一的二级页面头部：← 返回 + 标题（居中）+ 右侧区域。
 * 标题使用绝对定位保证始终居中，不受左右内容宽度影响。
 * 用于：任务详情、审核详情、病历采集、患者详情等子页面。
 */
import { Box, Typography } from "@mui/material";

export default function SubpageHeader({ title, onBack, right }) {
  return (
    <Box sx={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between",
      height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
      <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3,
        cursor: "pointer", color: "#07C160", pr: 2, py: 1, zIndex: 1 }}>
        <Typography sx={{ fontSize: 15, color: "#07C160" }}>← 返回</Typography>
      </Box>
      <Typography sx={{ position: "absolute", left: 0, right: 0, textAlign: "center",
        fontWeight: 600, fontSize: 16, pointerEvents: "none" }}>
        {title}
      </Typography>
      {right && <Box sx={{ zIndex: 1 }}>{right}</Box>}
    </Box>
  );
}
