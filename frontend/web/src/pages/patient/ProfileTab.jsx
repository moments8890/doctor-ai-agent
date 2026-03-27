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
import ListCard from "../../components/ListCard";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import { TYPE, COLOR } from "../../theme";

export default function ProfileTab({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  return (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
      {/* Doctor info card */}
      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <Box sx={{ bgcolor: COLOR.white }}>
            <ListCard
              avatar={<PatientAvatar name={doctorName} size={42} />}
              title={doctorName}
              subtitle={doctorSpecialty || ""}
            />
          </Box>
        </>
      )}

      {/* Patient info card */}
      <SectionLabel>我的信息</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <ListCard
          avatar={<PatientAvatar name={patientName || "?"} size={42} />}
          title={patientName || "患者"}
          subtitle={doctorId || ""}
        />
      </Box>

      {/* Logout */}
      <Box sx={{ mt: 1 }}>
        <Box onClick={onLogout}
          sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
        </Box>
      </Box>
    </Box>
  );
}
