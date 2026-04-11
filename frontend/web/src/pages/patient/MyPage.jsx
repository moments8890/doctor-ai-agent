/**
 * MyPage — patient "我的" settings page.
 *
 * Follows SettingsListSubpage pattern from doctor app.
 * Sections: patient info, doctor info, general (about/privacy), logout.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import AccountCard from "../../components/AccountCard";
import SectionLabel from "../../components/SectionLabel";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageSkeleton from "../../components/PageSkeleton";
import SheetDialog from "../../components/SheetDialog";
import AppButton from "../../components/AppButton";
import { TYPE, ICON, COLOR, RADIUS, applyFontScale } from "../../theme";
import { useFontScaleStore, triggerFontScaleRerender } from "../../store/fontScaleStore";
import { ONBOARDING_DONE_KEY_PREFIX } from "./constants";
import AboutSubpage from "../doctor/subpages/AboutSubpage";
import PrivacySubpage from "../PrivacyPage";

function SettingsRow({ icon, label, sublabel, onClick }) {
  return (
    <Box onClick={onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: onClick ? "pointer" : "default",
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:active": onClick ? { bgcolor: COLOR.surface } : {},
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: RADIUS.sm,
        bgcolor: COLOR.primaryLight,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.text1 }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: COLOR.text4, transform: "rotate(180deg)" }} />}
    </Box>
  );
}

export default function MyPage({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  const [subpage, setSubpage] = useState(null);
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const fontScale = useFontScaleStore(s => s.fontScale);
  const [showFontScale, setShowFontScale] = useState(false);
  const FONT_SCALE_OPTIONS = [
    { key: "standard", label: "标准" },
    { key: "large", label: "大" },
    { key: "extraLarge", label: "特大" },
  ];

  function handleFontScaleChange(level) {
    useFontScaleStore.getState().setFontScale(level);
    applyFontScale(level);
    triggerFontScaleRerender();
    setShowFontScale(false);
  }

  function handleReplayOnboarding() {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.removeItem(ONBOARDING_DONE_KEY_PREFIX + patientId);
    window.location.reload();
  }

  const subpageContent = subpage === "about"
    ? <AboutSubpage onBack={() => setSubpage(null)} isMobile />
    : subpage === "privacy"
    ? <PageSkeleton title="隐私政策" onBack={() => setSubpage(null)} isMobile listPane={<PrivacySubpage />} />
    : null;

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt }}>
      <SectionLabel>我的信息</SectionLabel>
      <AccountCard
        name={patientName || "患者"}
        subtitle="患者"
        color={COLOR.primary}
      />

      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <AccountCard
            name={doctorName}
            subtitle={doctorSpecialty || ""}
            color={COLOR.accent}
          />
        </>
      )}

      <SectionLabel>通用</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <SettingsRow
          icon={<InfoOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="关于"
          sublabel="版本信息"
          onClick={() => setSubpage("about")}
        />
        <SettingsRow
          icon={<PolicyOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="隐私政策"
          sublabel="数据使用与保护"
          onClick={() => setSubpage("privacy")}
        />
        <SettingsRow
          icon={<TextFieldsOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="字体大小"
          sublabel={FONT_SCALE_OPTIONS.find(o => o.key === fontScale)?.label || "标准"}
          onClick={() => setShowFontScale(true)}
        />
        <SettingsRow
          icon={<ReplayOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="重新查看引导"
          onClick={handleReplayOnboarding}
        />
      </Box>

      <SectionLabel>账户操作</SectionLabel>
      <Box onClick={() => setShowLogoutDialog(true)} sx={{
        bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer",
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        "&:active": { bgcolor: COLOR.surface },
      }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
      </Box>

      <Box sx={{ height: 32 }} />

      <ConfirmDialog
        open={showLogoutDialog}
        onClose={() => setShowLogoutDialog(false)}
        onCancel={() => setShowLogoutDialog(false)}
        onConfirm={onLogout}
        title="退出登录"
        message="确定要退出登录吗？"
        cancelLabel="取消"
        confirmLabel="退出"
        confirmTone="danger"
      />

      <SheetDialog open={showFontScale} onClose={() => setShowFontScale(false)} title="字体大小">
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, p: 1 }}>
          {FONT_SCALE_OPTIONS.map(o => (
            <AppButton
              key={o.key}
              variant={fontScale === o.key ? "primary" : "secondary"}
              size="md"
              fullWidth
              onClick={() => handleFontScaleChange(o.key)}
            >
              {o.label}
            </AppButton>
          ))}
        </Box>
      </SheetDialog>
    </Box>
  );

  return (
    <PageSkeleton
      title="我的"
      isMobile
      mobileView={subpageContent}
      listPane={listContent}
    />
  );
}
