/**
 * Shared icon badge configs used by both doctor and patient apps.
 * Extracted from doctor/constants.jsx to avoid cross-app imports.
 */
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import { COLOR } from "../theme";

export const SHARED_ICON_BADGES = {
  // Chat avatars
  ai:           { icon: SmartToyOutlinedIcon, bg: COLOR.primary },
  patient:      { icon: PersonOutlineIcon, bg: COLOR.accent },
  notification: { icon: NotificationsNoneOutlinedIcon, bg: COLOR.borderLight, color: COLOR.text4 },

  // Record types
  rec_visit:     { icon: LocalHospitalOutlinedIcon, bg: COLOR.primary },
  rec_dictation: { icon: MicNoneOutlinedIcon, bg: COLOR.recordDoc },
  rec_import:    { icon: FileUploadOutlinedIcon, bg: COLOR.recordDoc },
  rec_lab:       { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  rec_imaging:   { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
  rec_surgery:   { icon: LocalHospitalOutlinedIcon, bg: COLOR.danger },
  rec_interview: { icon: ChatOutlinedIcon, bg: COLOR.primary },

  // Task types
  task_follow_up:  { icon: EventRepeatOutlinedIcon, bg: COLOR.primary },
  task_medication: { icon: MedicationOutlinedIcon, bg: COLOR.accent },
  task_checkup:    { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  task_general:    { icon: AssignmentOutlinedIcon, bg: COLOR.recordDoc },
  task_imaging:    { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
};

export const RECORD_TYPE_BADGE = {
  visit:             SHARED_ICON_BADGES.rec_visit,
  dictation:         SHARED_ICON_BADGES.rec_dictation,
  import:            SHARED_ICON_BADGES.rec_import,
  lab:               SHARED_ICON_BADGES.rec_lab,
  imaging:           SHARED_ICON_BADGES.rec_imaging,
  surgery:           SHARED_ICON_BADGES.rec_surgery,
  interview_summary: SHARED_ICON_BADGES.rec_interview,
};

export const TASK_TYPE_BADGE = {
  follow_up:  SHARED_ICON_BADGES.task_follow_up,
  medication: SHARED_ICON_BADGES.task_medication,
  checkup:    SHARED_ICON_BADGES.task_checkup,
  general:    SHARED_ICON_BADGES.task_general,
  imaging:    SHARED_ICON_BADGES.task_imaging,
};
