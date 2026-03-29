/**
 * ProfileTab — patient profile screen.
 *
 * Sections:
 *  1. "我的医生" — doctor card (only shown when doctorName is truthy)
 *  2. "我的信息" — patient info card
 *  3. Logout button
 *
 * Props:
 *  - patientName: string
 *  - doctorName: string | null
 *  - doctorSpecialty: string | null
 *  - doctorId: string | null
 *  - onLogout: () => void
 */
import { Box, Typography } from "@mui/material";
import AccountCard from "../../components/AccountCard";
import SectionLabel from "../../components/SectionLabel";
import { TYPE, COLOR } from "../../theme";

export default function ProfileTab({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  return (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
      {/* Doctor info card */}
      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <AccountCard
            name={doctorName}
            subtitle={doctorSpecialty || ""}
            color="#5b9bd5"
          />
        </>
      )}

      {/* Patient info card */}
      <SectionLabel>我的信息</SectionLabel>
      <AccountCard
        name={patientName || "患者"}
        subtitle={doctorId || ""}
        color={COLOR.primary}
      />

      {/* Logout */}
      <Box sx={{ mt: 1 }}>
        <Box onClick={onLogout}
          sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
        </Box>
      </Box>
    </Box>
  );
}
