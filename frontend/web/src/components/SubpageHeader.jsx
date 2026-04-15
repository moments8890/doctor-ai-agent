/**
 * 统一的二级页面头部：← 返回 + 标题（居中）+ 右侧区域。
 * 标题使用绝对定位保证始终居中，不受左右内容宽度影响。
 * 用于：任务详情、审核详情、病历采集、患者详情等子页面。
 */
import { Box, Typography } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import { TYPE, ICON, COLOR } from "../theme";
import { markIntentionalBack } from "../hooks/useNavDirection";

export default function SubpageHeader({ title, onBack, right }) {
  // Wrap onBack so PageSkeleton's useNavDirection sees an "intentional" back
  // action (flag set right before navigate(-1) fires). Without this wrapper,
  // the hook can't tell a tap-back apart from a browser/swipe back, and the
  // slide-out animation is skipped.
  const handleBack = onBack
    ? (e) => { markIntentionalBack(); onBack(e); }
    : undefined;

  return (
    <Box sx={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between",
      height: 48, px: 0.5, bgcolor: COLOR.white, borderBottom: `1px solid ${COLOR.border}`, flexShrink: 0 }}>
      {onBack ? (
        <Box onClick={handleBack} sx={{ display: "flex", alignItems: "center",
          cursor: "pointer", color: COLOR.text2, px: 0.5, py: 1, zIndex: 1, "&:active": { opacity: 0.5 } }}>
          <ChevronLeftIcon sx={{ fontSize: ICON.hero, color: COLOR.text2 }} />
        </Box>
      ) : (
        <Box sx={{ minWidth: 48, zIndex: 1 }} />
      )}
      <Typography sx={{ position: "absolute", left: 0, right: 0, textAlign: "center",
        fontWeight: TYPE.title.fontWeight, fontSize: TYPE.title.fontSize, pointerEvents: "none" }}>
        {title}
      </Typography>
      {right ? <Box sx={{ zIndex: 1 }}>{right}</Box> : <Box sx={{ minWidth: 48 }} />}
    </Box>
  );
}
