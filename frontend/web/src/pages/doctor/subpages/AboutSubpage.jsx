/**
 * AboutSubpage — version info page extracted from SettingsPage.
 */
import { Box, Typography } from "@mui/material";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import PageSkeleton from "../../../components/PageSkeleton";
import { TYPE, ICON, COLOR } from "../../../theme";

export default function AboutSubpage({ onBack, isMobile }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 3, textAlign: "center" }}>
      <Box sx={{ width: 64, height: 64, borderRadius: "16px", bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center", mx: "auto", mb: 2 }}>
        <LocalHospitalOutlinedIcon sx={{ color: COLOR.white, fontSize: ICON.display }} />
      </Box>
      <Typography sx={{ fontWeight: 700, fontSize: TYPE.title.fontSize, mb: 0.5 }}>AI 医疗助手</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 3 }}>版本 1.0.0</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
        智能医疗助手为医生提供 AI 辅助病历记录、患者管理和任务跟踪功能，帮助提升诊疗效率。
      </Typography>
    </Box>
  );

  return <PageSkeleton title="关于" onBack={onBack} isMobile={isMobile} listPane={content} />;
}
