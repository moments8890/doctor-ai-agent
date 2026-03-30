/**
 * SettingsListSubpage — shared presentational settings menu.
 *
 * Displays doctor avatar + account info, tool navigation rows (template,
 * knowledge), general section (about), and logout button.
 * Used by both real SettingsPage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → 设置
 */
import { Box, CircularProgress, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";
import AccountCard from "../../../components/AccountCard";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLabel from "../../../components/SectionLabel";
import { TYPE, ICON, COLOR, RADIUS } from "../../../theme";

/* ── SettingsRow — icon-adorned navigation row ── */

function SettingsRow({ icon, label, sublabel, onClick, danger }) {
  return (
    <Box onClick={onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: onClick ? "pointer" : "default",
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:active": onClick ? { bgcolor: COLOR.surface } : {},
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: RADIUS.sm,
        bgcolor: danger ? COLOR.dangerLight : COLOR.primaryLight,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: danger ? COLOR.danger : COLOR.text1 }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && !danger && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: COLOR.text4, transform: "rotate(180deg)" }} />}
    </Box>
  );
}


/* ── BulkExportRow — shows spinner + progress while generating ── */

function BulkExportRow({ status, progress, onClick }) {
  const generating = status === "generating";
  const failed = status === "failed";

  const sublabel = generating ? progress
    : failed ? progress || "导出失败"
    : "下载所有患者病历 (ZIP)";

  return (
    <Box onClick={generating ? undefined : onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: generating ? "default" : "pointer",
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:active": generating ? {} : { bgcolor: COLOR.surface },
      opacity: generating ? 0.75 : 1,
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: RADIUS.sm,
        bgcolor: failed ? COLOR.dangerLight : "#f0f0fa",
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
        {generating
          ? <CircularProgress size={18} sx={{ color: "#7b61ff" }} />
          : <FileDownloadOutlinedIcon sx={{ color: failed ? COLOR.danger : "#7b61ff", fontSize: ICON.lg }} />
        }
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: failed ? COLOR.danger : COLOR.text1 }}>导出全部数据</Typography>
        <Typography variant="caption" color="text.secondary">{sublabel}</Typography>
      </Box>
      {!generating && !failed && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: COLOR.text4, transform: "rotate(180deg)" }} />}
    </Box>
  );
}

/* ── Main ── */

export default function SettingsListSubpage({
  doctorId,
  doctorName,
  specialty,
  clinicName,
  bio,
  onClinicTap,
  onBioTap,
  onTemplate,
  onKnowledge,
  onQRCode,
  onBulkExport,
  bulkExportStatus = "idle",
  bulkExportProgress = "",
  onAbout,
  onPrivacy,
  onLogout,
  isMobile = true,
  children,
}) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt }}>
      <SectionLabel>账户</SectionLabel>
      <AccountCard
        name={doctorName || doctorId}
        subtitle={doctorId}
        rows={[
          { label: "昵称", value: doctorName },
          { label: "科室专业", value: specialty },
          { label: "诊所/医院", value: clinicName, onClick: onClinicTap },
          { label: "简介", value: bio, onClick: onBioTap },
        ]}
      />

      <SectionLabel>工具</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <SettingsRow icon={<UploadFileOutlinedIcon sx={{ color: COLOR.primary, fontSize: ICON.lg }} />}
          label="报告模板" sublabel="自定义门诊病历报告格式" onClick={onTemplate} />
        <SettingsRow icon={<MenuBookOutlinedIcon sx={{ color: COLOR.recordBlue, fontSize: ICON.lg }} />}
          label="知识库" sublabel="管理 AI 助手参考资料" onClick={onKnowledge} />
        <SettingsRow icon={<QrCode2OutlinedIcon sx={{ color: COLOR.orange, fontSize: ICON.lg }} />}
          label="我的二维码" sublabel="扫码登录其他设备" onClick={onQRCode} />
        <BulkExportRow status={bulkExportStatus} progress={bulkExportProgress} onClick={onBulkExport} />
      </Box>

      <SectionLabel>通用</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <SettingsRow icon={<InfoOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="关于" sublabel="版本信息" onClick={onAbout} />
        <SettingsRow icon={<PolicyOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="隐私政策" sublabel="数据使用与保护" onClick={onPrivacy} />
      </Box>

      {onLogout && (
        <>
          <SectionLabel>账户操作</SectionLabel>
          <Box onClick={onLogout} sx={{
            bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer",
            borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:active": { bgcolor: COLOR.surface },
          }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
          </Box>
        </>
      )}
      <Box sx={{ height: 32 }} />
      {children}
    </Box>
  );

  return content;
}
