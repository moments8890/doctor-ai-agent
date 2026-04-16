/** AdminRelatedDialog — shows all related data for a doctor or patient */
import { useEffect, useState } from "react";
import {
  Box,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tooltip,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { getAdminDoctorRelated, getAdminPatientRelated } from "../../api";
import { TYPE } from "../../theme";
import { GH } from "./adminTheme";

const ENUM_ZH = {
  pending: "待处理", done: "已完成", completed: "已完成", cancelled: "已取消",
  confirmed: "已确认", rejected: "已拒绝", edited: "已修改",
  generated: "已生成", sent: "已发送", dismissed: "已忽略", stale: "已过期",
  inbound: "患者→", outbound: "→患者",
  follow_up: "随访", general: "通用",
  visit: "门诊", dictation: "语音", import: "导入", interview_summary: "问诊总结",
  male: "男", female: "女",
  active: "进行中", finished: "已完成",
  patient: "患者", ai: "AI", doctor: "医生", system: "系统",
  differential: "鉴别诊断", workup: "检查方案", treatment: "治疗方案",
  interview_active: "问诊中", pending_review: "待审核",
  diagnosis_failed: "诊断失败", draft: "草稿",
  custom: "自定义", diagnosis: "���断", followup: "随访", medication: "用药",
  medium: "中", high: "高", low: "低",
  READ: "读取", WRITE: "写入", DELETE: "删除", LOGIN: "登录",
};

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "是" : "否";
  if (ENUM_ZH[v]) return ENUM_ZH[v];
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v))
    return v.slice(0, 16).replace("T", " ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// Shared table styles
const thSx = {
  fontWeight: 700, color: GH.textMuted, whiteSpace: "nowrap",
  backgroundColor: GH.hoverBg, borderBottom: `1px solid ${GH.border}`,
  px: 1, py: 0.6, fontSize: TYPE.caption.fontSize,
};
const tdSx = {
  borderBottom: `1px solid ${GH.border}`, py: 0.4, px: 1,
  fontSize: TYPE.caption.fontSize, color: GH.text, whiteSpace: "nowrap",
  overflow: "hidden", textOverflow: "ellipsis", maxWidth: 240,
};

function MiniTable({ columns, rows, emptyText = "暂无数据" }) {
  if (!rows.length) {
    return (
      <Typography sx={{ color: GH.textMuted, fontSize: 12, py: 2, textAlign: "center" }}>
        {emptyText}
      </Typography>
    );
  }
  return (
    <TableContainer sx={{ maxHeight: 360 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {columns.map((c) => (
              <TableCell key={c.key} sx={{ ...thSx, minWidth: c.width || 80 }}>
                {c.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={row.id ?? i} sx={{ "&:hover": { backgroundColor: GH.hoverBg } }}>
              {columns.map((c) => (
                <TableCell key={c.key} sx={{ ...tdSx, maxWidth: c.width || 240 }}>
                  {c.render ? c.render(row[c.key], row) : (
                    <Tooltip
                      title={String(row[c.key] ?? "").length > 40 ? String(row[c.key]) : ""}
                      placement="top"
                    >
                      <span>{fmt(row[c.key])}</span>
                    </Tooltip>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

/** Key-value display for single-item data (profile, persona, preferences, wechat, auth) */
function KVSection({ data, emptyText = "暂无数据" }) {
  if (!data) {
    return (
      <Typography sx={{ color: GH.textMuted, fontSize: 12, py: 2, textAlign: "center" }}>
        {emptyText}
      </Typography>
    );
  }
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
      {Object.entries(data).map(([key, value]) => (
        <Box key={key} sx={{ display: "flex", py: 0.6, px: 1, borderBottom: `1px solid ${GH.border}` }}>
          <Typography sx={{ fontSize: 11, fontWeight: 600, color: GH.textMuted, width: 140, flexShrink: 0 }}>
            {key}
          </Typography>
          <Typography sx={{ fontSize: 11, color: GH.text, wordBreak: "break-all",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto" }}>
            {fmt(value)}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function StatusChip({ value }) {
  const colors = {
    pending: GH.orange, completed: GH.green, done: GH.green,
    cancelled: GH.textMuted, confirmed: GH.green, rejected: GH.red,
    edited: GH.blue, generated: GH.blue, sent: GH.green,
    dismissed: GH.textMuted, stale: GH.textMuted,
    interview_active: GH.blue, pending_review: GH.orange,
    active: GH.blue, finished: GH.green, draft: GH.textMuted,
  };
  const color = colors[value] || GH.textMuted;
  return (
    <Chip size="small" label={ENUM_ZH[value] || value || "—"}
      sx={{ height: 18, fontSize: 10, color, borderColor: color,
        background: `${color}18` }} />
  );
}

function BoolChip({ value }) {
  return (
    <Chip size="small" label={value ? "是" : "否"}
      sx={{ height: 18, fontSize: 10,
        color: value ? GH.green : GH.textMuted,
        borderColor: value ? GH.green : GH.textMuted,
        background: value ? `${GH.green}18` : `${GH.textMuted}18` }} />
  );
}

// --- Tab definitions ---
const DOCTOR_TABS = [
  { key: "profile", label: "基本信息", kind: "kv" },
  { key: "patients", label: "患者" },
  { key: "records", label: "病历" },
  { key: "tasks", label: "任务" },
  { key: "messages", label: "消息" },
  { key: "knowledge", label: "知识库" },
  { key: "suggestions", label: "AI建议" },
  { key: "interviews", label: "问诊" },
  { key: "chats", label: "对话记录" },
  { key: "drafts", label: "消息草稿" },
  { key: "persona", label: "人设", kind: "kv" },
  { key: "preferences", label: "偏好设置", kind: "kv" },
  { key: "edits", label: "修改记录" },
  { key: "kb_usage", label: "知识引用" },
  { key: "wechat", label: "微信绑定", kind: "kv" },
  { key: "invite_codes", label: "邀请码" },
  { key: "audit_log", label: "审计日志" },
  { key: "pending_persona", label: "待审人设" },
];

const PATIENT_TABS = [
  { key: "profile", label: "基本信息", kind: "kv" },
  { key: "records", label: "病历" },
  { key: "messages", label: "消息" },
  { key: "tasks", label: "任务" },
  { key: "suggestions", label: "AI建议" },
  { key: "interviews", label: "问诊" },
  { key: "drafts", label: "消息草稿" },
  { key: "auth", label: "认证信息", kind: "kv" },
  { key: "kb_usage", label: "知识引用" },
];

// --- Column definitions ---
const COLUMNS = {
  patients: [
    { key: "id", label: "ID", width: 60 },
    { key: "name", label: "姓名", width: 100 },
    { key: "gender", label: "性别", width: 60 },
    { key: "year_of_birth", label: "出生年", width: 70 },
    { key: "phone", label: "手机", width: 110 },
    { key: "created_at", label: "创建时间", width: 140 },
    { key: "last_activity_at", label: "最后活跃", width: 140 },
  ],
  records: [
    { key: "id", label: "ID", width: 50 },
    { key: "patient_name", label: "患者", width: 80 },
    { key: "record_type", label: "类型", width: 80 },
    { key: "content", label: "内容", width: 240 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  records_patient: [
    { key: "id", label: "ID", width: 50 },
    { key: "record_type", label: "类型", width: 80 },
    { key: "content", label: "内容", width: 200 },
    { key: "diagnosis", label: "诊断", width: 160 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  tasks: [
    { key: "id", label: "ID", width: 50 },
    { key: "patient_name", label: "患者", width: 80 },
    { key: "task_type", label: "类型", width: 70 },
    { key: "title", label: "标题", width: 200 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "due_at", label: "截止", width: 140 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  tasks_patient: [
    { key: "id", label: "ID", width: 50 },
    { key: "task_type", label: "类型", width: 70 },
    { key: "title", label: "标题", width: 200 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "due_at", label: "截止", width: 140 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  messages: [
    { key: "id", label: "ID", width: 50 },
    { key: "patient_name", label: "患者", width: 80 },
    { key: "direction", label: "方向", width: 70 },
    { key: "source", label: "来源", width: 60 },
    { key: "content", label: "内容", width: 240 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  messages_patient: [
    { key: "id", label: "ID", width: 50 },
    { key: "direction", label: "方向", width: 70 },
    { key: "source", label: "来源", width: 60 },
    { key: "content", label: "内容", width: 300 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  knowledge: [
    { key: "id", label: "ID", width: 50 },
    { key: "title", label: "标题", width: 160 },
    { key: "category", label: "分类", width: 80 },
    { key: "content", label: "内容", width: 240 },
    { key: "reference_count", label: "引用", width: 50 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  suggestions: [
    { key: "id", label: "ID", width: 50 },
    { key: "record_id", label: "病历ID", width: 60 },
    { key: "section", label: "类别", width: 80 },
    { key: "content", label: "内容", width: 240 },
    { key: "decision", label: "决策", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "created_at", label: "时间", width: 140 },
  ],
  interviews: [
    { key: "id", label: "ID", width: 80 },
    { key: "patient_id", label: "患者ID", width: 70 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "turn_count", label: "轮次", width: 60 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  interviews_patient: [
    { key: "id", label: "ID", width: 80 },
    { key: "doctor_id", label: "医生ID", width: 120 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "turn_count", label: "轮次", width: 60 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  chats: [
    { key: "id", label: "ID", width: 50 },
    { key: "session_id", label: "会话", width: 100 },
    { key: "role", label: "角色", width: 60 },
    { key: "content", label: "内容", width: 300 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  drafts: [
    { key: "id", label: "ID", width: 50 },
    { key: "patient_id", label: "患者ID", width: 70 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "draft_text", label: "草稿内容", width: 280 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  drafts_patient: [
    { key: "id", label: "ID", width: 50 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "draft_text", label: "草稿内容", width: 320 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  edits: [
    { key: "id", label: "ID", width: 50 },
    { key: "entity_type", label: "对象类型", width: 80 },
    { key: "entity_id", label: "对象ID", width: 60 },
    { key: "field_name", label: "字段", width: 80 },
    { key: "original_text", label: "原文", width: 160 },
    { key: "edited_text", label: "修改后", width: 160 },
    { key: "rule_created", label: "生成规则", width: 70, render: (v) => <BoolChip value={v} /> },
    { key: "created_at", label: "���间", width: 140 },
  ],
  kb_usage: [
    { key: "id", label: "ID", width: 50 },
    { key: "knowledge_item_id", label: "知识ID", width: 70 },
    { key: "usage_context", label: "使用场景", width: 100 },
    { key: "patient_id", label: "患者ID", width: 70 },
    { key: "record_id", label: "病历ID", width: 70 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  kb_usage_patient: [
    { key: "id", label: "ID", width: 50 },
    { key: "knowledge_item_id", label: "知识ID", width: 70 },
    { key: "usage_context", label: "使用场景", width: 100 },
    { key: "record_id", label: "病历ID", width: 70 },
    { key: "created_at", label: "时间", width: 140 },
  ],
  invite_codes: [
    { key: "code", label: "邀请码", width: 120 },
    { key: "active", label: "状态", width: 60, render: (v) => <BoolChip value={v} /> },
    { key: "used_count", label: "使用次数", width: 70 },
    { key: "created_at", label: "创建时间", width: 140 },
  ],
  audit_log: [
    { key: "id", label: "ID", width: 50 },
    { key: "action", label: "操作", width: 70 },
    { key: "resource_type", label: "资源类型", width: 80 },
    { key: "resource_id", label: "资源ID", width: 100 },
    { key: "ok", label: "成功", width: 50, render: (v) => <BoolChip value={v} /> },
    { key: "ip", label: "IP", width: 110 },
    { key: "ts", label: "时间", width: 140 },
  ],
  pending_persona: [
    { key: "id", label: "ID", width: 50 },
    { key: "field", label: "字段", width: 80 },
    { key: "proposed_rule", label: "规则", width: 200 },
    { key: "summary", label: "摘要", width: 160 },
    { key: "confidence", label: "置信", width: 60 },
    { key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
    { key: "created_at", label: "时间", width: 140 },
  ],
};

export default function AdminRelatedDialog({ type, id, open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(0);

  const tabs = type === "doctors" ? DOCTOR_TABS : PATIENT_TABS;
  const isPatient = type === "patients";

  useEffect(() => {
    if (!open || !id) return;
    setLoading(true);
    setError("");
    setTab(0);
    const fetcher = type === "doctors"
      ? getAdminDoctorRelated(id)
      : getAdminPatientRelated(id);
    fetcher
      .then((d) => setData(d))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [open, id, type]);

  function getTabContent(tabKey) {
    if (!data) return null;
    const tabDef = tabs.find((t) => t.key === tabKey);

    // Profile and other KV-display tabs
    if (tabDef?.kind === "kv") {
      if (tabKey === "profile") return <KVSection data={data.profile} />;
      const section = data[tabKey];
      if (!section) return <KVSection data={null} />;
      // Single-item sections (persona, preferences, wechat, auth)
      return <KVSection data={section.item} />;
    }

    // List sections
    const section = data[tabKey];
    if (!section) return <Typography sx={{ color: GH.textMuted, py: 2, textAlign: "center" }}>暂无数据</Typography>;
    const colKey = isPatient && COLUMNS[`${tabKey}_patient`] ? `${tabKey}_patient` : tabKey;
    const cols = COLUMNS[colKey] || [];
    return <MiniTable columns={cols} rows={section.items || []} />;
  }

  function getTabCount(tabKey) {
    if (!data || tabKey === "profile") return null;
    const section = data[tabKey];
    return section?.count ?? null;
  }

  const title = type === "doctors"
    ? `医生: ${data?.profile?.name || id}`
    : `患者: ${data?.profile?.name || id}`;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth
      PaperProps={{ sx: {
        borderRadius: 2, background: GH.card, color: GH.text,
        border: `1px solid ${GH.border}`, minHeight: 500,
      } }}>
      <DialogTitle sx={{ fontWeight: 700, pb: 0.5, color: "#fff", pr: 5 }}>
        {loading ? "加载中..." : title}
        <IconButton onClick={onClose} sx={{ position: "absolute", right: 8, top: 8, color: GH.textMuted }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ p: 0 }}>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={28} sx={{ color: GH.blue }} />
          </Box>
        )}
        {error && (
          <Typography sx={{ color: GH.red, p: 2, fontSize: 12 }}>
            错误: {error}
          </Typography>
        )}
        {data && !loading && (
          <>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto"
              sx={{
                borderBottom: `1px solid ${GH.border}`, minHeight: 36, px: 1,
                "& .MuiTab-root": {
                  color: GH.textMuted, fontSize: 12, minHeight: 36, py: 0.5,
                  textTransform: "none",
                },
                "& .Mui-selected": { color: GH.blue },
                "& .MuiTabs-indicator": { backgroundColor: GH.blue },
              }}>
              {tabs.map((t) => {
                const count = getTabCount(t.key);
                const label = count != null ? `${t.label} (${count})` : t.label;
                return <Tab key={t.key} label={label} />;
              })}
            </Tabs>
            <Box sx={{ p: 1.5 }}>
              {getTabContent(tabs[tab]?.key)}
            </Box>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
