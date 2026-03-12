/**
 * 首页仪表盘：展示患者总数、待处理任务、最近病历及快捷操作入口。
 */
import { useEffect, useState } from "react";
import { Box, CircularProgress, Stack, Typography } from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import TransferWithinAStationOutlinedIcon from "@mui/icons-material/TransferWithinAStationOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import EventAvailableOutlinedIcon from "@mui/icons-material/EventAvailableOutlined";
import { getPatients, getTasks, getRecords } from "../../api";
import { TASK_TYPE_LABEL } from "./constants";
import PatientAvatar from "./PatientAvatar";

const TASK_ICON_MAP = {
  follow_up: EventRepeatOutlinedIcon, medication: MedicationOutlinedIcon,
  lab_review: BiotechOutlinedIcon, referral: TransferWithinAStationOutlinedIcon,
  imaging: MonitorHeartOutlinedIcon, appointment: EventAvailableOutlinedIcon,
  general: AssignmentOutlinedIcon,
};

const TASK_COLOR_MAP = {
  follow_up: "#07C160", medication: "#5b9bd5", lab_review: "#e8833a",
  referral: "#9b59b6", imaging: "#1890ff", appointment: "#16a085", general: "#8e44ad",
};

function StatCard({ label, value, color = "primary.main", onClick }) {
  return (
    <Box onClick={onClick} sx={{ flex: 1, minWidth: 100, textAlign: "center", py: 2.5, px: 1,
      bgcolor: "#fff", borderRadius: 1.5, cursor: onClick ? "pointer" : "default",
      "&:active": onClick ? { bgcolor: "#f5f5f5" } : {} }}>
      <Typography variant="h4" sx={{ fontWeight: 800, color, lineHeight: 1 }}>{value ?? "—"}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>{label}</Typography>
    </Box>
  );
}

function PendingTaskRow({ task, idx, total }) {
  const isOverdue = task.due_at && new Date(task.due_at) < new Date();
  const TaskIcon = TASK_ICON_MAP[task.task_type] || AssignmentOutlinedIcon;
  const iconColor = TASK_COLOR_MAP[task.task_type] || "#999";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, borderBottom: idx < total - 1 ? "1px solid #f2f2f2" : "none" }}>
      <Box sx={{ width: 32, height: 32, borderRadius: "8px", bgcolor: iconColor, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <TaskIcon sx={{ color: "#fff", fontSize: 18 }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
        </Typography>
        {task.due_at && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.4, mt: 0.2 }}>
            {isOverdue
              ? <WarningAmberOutlinedIcon sx={{ fontSize: 12, color: "error.main" }} />
              : <CalendarTodayOutlinedIcon sx={{ fontSize: 12, color: "text.secondary" }} />}
            <Typography variant="caption" sx={{ color: isOverdue ? "error.main" : "text.secondary" }}>
              {isOverdue ? "已逾期 " : ""}{task.due_at.slice(0, 10)}
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

function RecentRecordRow({ record, idx, total, navigate }) {
  return (
    <Box onClick={() => record.patient_id && navigate(`/doctor/patients/${record.patient_id}`)}
      sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2,
        borderBottom: idx < total - 1 ? "1px solid #f2f2f2" : "none",
        cursor: record.patient_id ? "pointer" : "default",
        "&:active": record.patient_id ? { bgcolor: "#f5f5f5" } : {} }}>
      <PatientAvatar name={record.patient_name || "?"} size={36} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>{record.patient_name || "未知患者"}</Typography>
        <Typography variant="caption" color="text.secondary" noWrap>
          {record.content ? (record.content.length > 40 ? record.content.slice(0, 40) + "…" : record.content) : "无记录"} · {record.created_at?.slice(0, 10)}
        </Typography>
      </Box>
      <Typography sx={{ color: "#ccc", fontSize: 18, lineHeight: 1 }}>›</Typography>
    </Box>
  );
}

const QUICK_ACTIONS = [
  { label: "进入对话", sub: "记录病历、查询患者", path: "/doctor/chat" },
  { label: "患者列表", sub: "查看所有患者", path: "/doctor/patients" },
  { label: "任务列表", sub: "待办随访提醒", path: "/doctor/tasks" },
];

function QuickActionsBlock({ navigate }) {
  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 1.5, mx: 2, mb: 2, overflow: "hidden" }}>
      {QUICK_ACTIONS.map((item, idx) => (
        <Box key={item.path} onClick={() => navigate(item.path)}
          sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: "pointer",
            borderBottom: idx < QUICK_ACTIONS.length - 1 ? "1px solid #f2f2f2" : "none",
            "&:active": { bgcolor: "#f5f5f5" } }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>{item.label}</Typography>
            <Typography variant="caption" color="text.secondary">{item.sub}</Typography>
          </Box>
          <Typography sx={{ color: "#ccc", fontSize: 18, lineHeight: 1 }}>›</Typography>
        </Box>
      ))}
    </Box>
  );
}

function SectionBlock({ title, viewAllLabel, onViewAll, children }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 0.8 }}>
        <Typography variant="caption" sx={{ color: "#888", fontWeight: 600, fontSize: 12 }}>{title}</Typography>
        <Typography variant="caption" sx={{ color: "#07C160", cursor: "pointer" }} onClick={onViewAll}>{viewAllLabel}</Typography>
      </Stack>
      <Box sx={{ bgcolor: "#fff", borderRadius: 1.5, mx: 2, overflow: "hidden" }}>{children}</Box>
    </Box>
  );
}

export default function HomeSection({ doctorId, navigate }) {
  const [stats, setStats] = useState(null);
  const [pendingTasks, setPendingTasks] = useState([]);
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getPatients(doctorId, {}, 200), getTasks(doctorId, "pending"), getRecords({ doctorId, limit: 5 })])
      .then(([pData, tData, rData]) => {
        const tasks = Array.isArray(tData) ? tData : (tData.items || []);
        setStats({ patients: (pData.items || []).length, pendingTasks: tasks.length });
        setPendingTasks(tasks.slice(0, 5));
        setRecentRecords((rData.items || []).slice(0, 5));
      }).catch(() => {}).finally(() => setLoading(false));
  }, [doctorId]);

  if (loading) return <Box sx={{ p: 4, textAlign: "center" }}><CircularProgress /></Box>;

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#f7f7f7" }}>
      <Stack direction="row" spacing={0} sx={{ mx: 2, mt: 2, mb: 2, gap: 1 }}>
        <StatCard label="患者总数" value={stats?.patients} onClick={() => navigate("/doctor/patients")} />
        <StatCard label="待处理任务" value={stats?.pendingTasks} color={stats?.pendingTasks > 0 ? "warning.main" : "success.main"} onClick={() => navigate("/doctor/tasks")} />
      </Stack>
      <QuickActionsBlock navigate={navigate} />
      {pendingTasks.length > 0 && (
        <SectionBlock title="待处理任务" viewAllLabel="查看全部 ›" onViewAll={() => navigate("/doctor/tasks")}>
          {pendingTasks.map((task, idx) => <PendingTaskRow key={task.id} task={task} idx={idx} total={pendingTasks.length} />)}
        </SectionBlock>
      )}
      {recentRecords.length > 0 && (
        <SectionBlock title="最近病历" viewAllLabel="查看患者 ›" onViewAll={() => navigate("/doctor/patients")}>
          {recentRecords.map((r, idx) => <RecentRecordRow key={r.id} record={r} idx={idx} total={recentRecords.length} navigate={navigate} />)}
        </SectionBlock>
      )}
    </Box>
  );
}
