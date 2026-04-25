/** AdminDoctorDetail — drill-down view for a single doctor (GitHub Dark theme).
 *  Shows all related data across every table via tabs.
 *
 *  DEPRECATED 2026-04-24 — superseded by `./v3/doctorDetail/AdminDoctorDetailV3.jsx`.
 *  Kept available at /admin?v=1 as a fallback for one release.
 *  See docs/plans/2026-04-24-admin-modern-port.md.
 */

import { Box, Tab, Tabs } from "@mui/material";
import { useEffect, useState } from "react";
import { getAdminDoctorRelated } from "../../api";
import { GH } from "./adminTheme";

// ── API helper ─────────────────────────────────────────────────────────────────
async function fetchJson(url) {
	const token =
		localStorage.getItem("adminToken") || (import.meta.env.DEV ? "dev" : "");
	const res = await fetch(url, {
		headers: token ? { "X-Admin-Token": token } : {},
	});
	if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
	return res.json();
}

// ── Dense shared styles (dark) ────────────────────────────────────────────────
const PANEL = {
	background: GH.card,
	border: `1px solid ${GH.border}`,
	borderRadius: 6,
	overflow: "hidden",
	marginBottom: 10,
};
const PANEL_HEAD = {
	padding: "6px 10px",
	fontSize: 11,
	fontWeight: 600,
	color: GH.text,
	borderBottom: `1px solid ${GH.border}`,
	display: "flex",
	justifyContent: "space-between",
	alignItems: "center",
	background: GH.hoverBg,
};
const TH = {
	textAlign: "left",
	padding: "4px 8px",
	fontSize: 10,
	color: GH.textMuted,
	fontWeight: 500,
	textTransform: "uppercase",
	letterSpacing: "0.3px",
	background: GH.hoverBg,
	borderBottom: `1px solid ${GH.border}`,
	whiteSpace: "nowrap",
};
const TD = {
	padding: "4px 8px",
	borderBottom: `1px solid ${GH.border}`,
	whiteSpace: "nowrap",
	fontSize: 11,
	color: GH.text,
};

const ENUM_ZH = {
	pending: "待处理", completed: "已完成", cancelled: "已取消",
	confirmed: "已确认", rejected: "已拒绝", edited: "已修改",
	generated: "已生成", sent: "已发送", dismissed: "已忽略", stale: "已过期",
	inbound: "患者→", outbound: "→患者",
	follow_up: "随访", general: "通用",
	visit: "门诊", dictation: "语音", import: "导入", interview_summary: "问诊总结",
	male: "男", female: "女",
	active: "进行中", finished: "已完成", draft: "草稿",
	patient: "患者", ai: "AI", doctor: "医生", system: "系统",
	differential: "鉴别诊断", workup: "检查方案", treatment: "治疗方案",
	interview_active: "问诊中", pending_review: "待审核",
	diagnosis_failed: "诊断失败",
	custom: "自定义", diagnosis: "诊断", followup: "随访", medication: "用药",
	medium: "中", high: "高", low: "低",
	READ: "读取", WRITE: "写入", DELETE: "删除", LOGIN: "登录",
};

// ── Dense chip (dark) ─────────────────────────────────────────────────────────
function DenseChip({ label, color = "gray" }) {
	const MAP = {
		green: { bg: "rgba(63,185,80,0.15)", fg: GH.green },
		red: { bg: "rgba(248,81,73,0.15)", fg: GH.red },
		amber: { bg: "rgba(247,129,102,0.15)", fg: GH.orange },
		blue: { bg: "rgba(88,166,255,0.15)", fg: GH.blue },
		purple: { bg: "rgba(188,140,255,0.15)", fg: "#bc8cff" },
		gray: { bg: "rgba(139,148,158,0.15)", fg: GH.textMuted },
	};
	const { bg, fg } = MAP[color] || MAP.gray;
	return (
		<span style={{ display: "inline-block", padding: "1px 5px", borderRadius: 3,
			fontSize: 10, fontWeight: 500, background: bg, color: fg }}>
			{label}
		</span>
	);
}

function StatusChip({ value }) {
	const colors = {
		pending: "amber", completed: "green", done: "green",
		cancelled: "gray", confirmed: "green", rejected: "red",
		edited: "blue", generated: "blue", sent: "green",
		dismissed: "gray", stale: "gray", draft: "gray",
		interview_active: "blue", pending_review: "amber",
		active: "blue", finished: "green",
	};
	return <DenseChip label={ENUM_ZH[value] || value || "—"} color={colors[value] || "gray"} />;
}

// ── Format helpers ────────────────────────────────────────────────────────────
function fmtTime(ts) {
	if (!ts) return "—";
	const d = new Date(ts);
	if (Number.isNaN(d)) return String(ts).slice(0, 16);
	const now = new Date();
	const diffDays = Math.floor((now - d) / 86400000);
	if (diffDays === 0) return d.toTimeString().slice(0, 5);
	if (diffDays === 1) return `昨${d.toTimeString().slice(0, 5)}`;
	return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDate(ts) {
	if (!ts) return "—";
	const d = new Date(ts);
	if (Number.isNaN(d)) return String(ts).slice(0, 10);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtFull(ts) {
	if (!ts) return "—";
	const d = new Date(ts);
	if (Number.isNaN(d)) return String(ts).slice(0, 16);
	return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${d.toTimeString().slice(0, 5)}`;
}

function fmtTs(ts) {
	if (!ts) return "—";
	if (typeof ts === "string" && /^\d{4}-\d{2}-\d{2}T/.test(ts))
		return ts.slice(0, 16).replace("T", " ");
	return fmtFull(ts);
}

function fmtVal(v) {
	if (v === null || v === undefined || v === "") return "—";
	if (typeof v === "boolean") return v ? "是" : "否";
	if (ENUM_ZH[v]) return ENUM_ZH[v];
	if (typeof v === "object") return JSON.stringify(v, null, 2);
	return String(v);
}

// ── Setup checklist inline ────────────────────────────────────────────────────
function SetupChecklist({ setup }) {
	if (!setup) return null;
	const items = [
		{ label: `KB×${setup.kb_count ?? 0}`, ok: (setup.kb_count ?? 0) > 0 },
		{ label: "首患者", ok: !!setup.has_patients },
		{ label: "首AI", ok: !!setup.has_ai_usage },
		{ label: "首病历", ok: !!setup.has_records },
	];
	return (
		<span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11 }}>
			{items.map((item, i) => (
				<span key={i} style={{ color: item.ok ? GH.green : GH.red, fontWeight: 500 }}>
					{item.ok ? "✓" : "✗"}&nbsp;{item.label}
				</span>
			))}
		</span>
	);
}

// ── Doctor header (dark) ──────────────────────────────────────────────────────
function DoctorHeader({ doctor, onBack }) {
	if (!doctor) return null;
	return (
		<Box sx={{ p: 1, px: 1.5, display: "flex", justifyContent: "space-between",
			alignItems: "center", background: GH.card, border: `1px solid ${GH.border}`,
			borderRadius: 1.5, mb: 1.25 }}>
			<Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
				<span style={{ color: GH.blue, cursor: "pointer", fontSize: 11, userSelect: "none" }}
					onClick={onBack}>&larr; 返回</span>
				<span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
					{doctor.name || doctor.doctor_id}
				</span>
				{doctor.department && (
					<span style={{ fontSize: 11, color: GH.textMuted }}>{doctor.department}</span>
				)}
				<span style={{ fontSize: 10, color: GH.textMuted, fontFamily: "monospace" }}>
					&middot; ID:&nbsp;{doctor.doctor_id}
					&nbsp;&middot; 注册&nbsp;{fmtDate(doctor.created_at)}
					&nbsp;&middot; 最后活跃&nbsp;{fmtTime(doctor.last_active)}
				</span>
			</Box>
			<SetupChecklist setup={doctor.setup} />
		</Box>
	);
}

// ── Stat strip ──────────────────────────────────────────────────────────────
function DoctorStatStrip({ doctor }) {
	if (!doctor) return null;
	const s = doctor.stats_7d || {};
	const adoptionRate = s.ai_adoption != null ? Math.round(s.ai_adoption * 100) : null;
	const adoptionColor = adoptionRate == null ? GH.textMuted
		: adoptionRate >= 70 ? GH.green : adoptionRate >= 40 ? GH.orange : GH.red;
	const taskRate = (s.tasks_total ?? 0) > 0
		? Math.round(((s.tasks_done ?? 0) / s.tasks_total) * 100) : null;

	const cells = [
		{ label: "患者", value: s.patients ?? "—", sub: "7d", color: GH.text },
		{ label: "消息 7d", value: s.messages ?? "—", sub: "", color: GH.text },
		{ label: "AI采纳率", value: adoptionRate != null ? `${adoptionRate}%` : "—",
			sub: adoptionRate != null ? `采${s.ai_accepted ?? 0} 改${s.ai_edited ?? 0} 拒${s.ai_rejected ?? 0}` : "",
			color: adoptionColor },
		{ label: "病历 7d", value: s.records ?? "—", sub: "", color: GH.text },
		{ label: "任务完成率", value: taskRate != null ? `${taskRate}%` : "—",
			sub: taskRate != null ? `${s.tasks_done ?? 0}/${s.tasks_total ?? 0}` : "",
			color: taskRate == null ? GH.textMuted : taskRate >= 70 ? GH.green : GH.orange },
	];

	return (
		<div style={{ display: "flex", gap: 0, background: GH.card, border: `1px solid ${GH.border}`,
			borderRadius: 6, overflow: "hidden", marginBottom: 10 }}>
			{cells.map((c, i) => (
				<div key={i} style={{ flex: 1, padding: "8px 12px",
					borderRight: i < cells.length - 1 ? `1px solid ${GH.border}` : "none" }}>
					<div style={{ fontSize: 10, color: GH.textMuted, textTransform: "uppercase", letterSpacing: "0.3px" }}>
						{c.label}
					</div>
					<div style={{ fontSize: 18, fontWeight: 700, marginTop: 1, color: c.color }}>{c.value}</div>
					<div style={{ fontSize: 10, color: GH.textMuted }}>{c.sub || "\u00a0"}</div>
				</div>
			))}
		</div>
	);
}

// ── Generic data table ──────────────────────────────────────────────────────
function DataTable({ title, columns, rows, count, emptyText = "暂无数据" }) {
	return (
		<div style={PANEL}>
			<div style={PANEL_HEAD}>
				<span>{title}</span>
				<span style={{ fontSize: 10, color: GH.textMuted }}>{count ?? rows?.length ?? 0} 条</span>
			</div>
			{(!rows || rows.length === 0) ? (
				<div style={{ padding: "12px 10px", fontSize: 11, color: GH.textMuted, textAlign: "center" }}>
					{emptyText}
				</div>
			) : (
				<div style={{ maxHeight: 400, overflow: "auto" }}>
					<table style={{ width: "100%", borderCollapse: "collapse" }}>
						<thead>
							<tr>
								{columns.map((c) => (
									<th key={c.key} style={{ ...TH, minWidth: c.width || 80 }}>{c.label}</th>
								))}
							</tr>
						</thead>
						<tbody>
							{rows.map((row, i) => (
								<tr key={row.id ?? i} style={{ cursor: "default" }}>
									{columns.map((c) => (
										<td key={c.key} style={{ ...TD, maxWidth: c.maxWidth || 300,
											overflow: "hidden", textOverflow: "ellipsis" }}>
											{c.render ? c.render(row[c.key], row) : fmtVal(row[c.key])}
										</td>
									))}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	);
}

// ── Key-value display for single-item sections ──────────────────────────────
function KVPanel({ title, data }) {
	if (!data) {
		return (
			<div style={PANEL}>
				<div style={PANEL_HEAD}><span>{title}</span></div>
				<div style={{ padding: "12px 10px", fontSize: 11, color: GH.textMuted, textAlign: "center" }}>
					暂无数据
				</div>
			</div>
		);
	}
	return (
		<div style={PANEL}>
			<div style={PANEL_HEAD}><span>{title}</span></div>
			<div style={{ display: "grid", gridTemplateColumns: "1fr 1fr" }}>
				{Object.entries(data).map(([key, value]) => (
					<div key={key} style={{ display: "flex", padding: "4px 10px",
						borderBottom: `1px solid ${GH.border}` }}>
						<span style={{ fontSize: 10, fontWeight: 600, color: GH.textMuted,
							width: 130, flexShrink: 0 }}>{key}</span>
						<span style={{ fontSize: 10, color: GH.text, wordBreak: "break-all",
							fontFamily: "ui-monospace, monospace", whiteSpace: "pre-wrap",
							maxHeight: 100, overflow: "auto" }}>
							{fmtVal(value)}
						</span>
					</div>
				))}
			</div>
		</div>
	);
}

// ── Patient table with timeline ─────────────────────────────────────────────
function PatientsTab({ patients, doctorId }) {
	const [selectedPatient, setSelectedPatient] = useState(null);
	const [timeline, setTimeline] = useState(null);
	const [tlLoading, setTlLoading] = useState(false);

	useEffect(() => {
		if (!selectedPatient || !doctorId) { setTimeline(null); return; }
		setTlLoading(true);
		fetchJson(`/api/admin/doctors/${doctorId}/timeline?patient_id=${selectedPatient.patient_id || selectedPatient.id}`)
			.then((data) => setTimeline(data.events || data.items || []))
			.catch(() => setTimeline([]))
			.finally(() => setTlLoading(false));
	}, [selectedPatient, doctorId]);

	return (
		<>
			<div style={PANEL}>
				<div style={PANEL_HEAD}>
					<span>患者列表</span>
					<span style={{ fontSize: 10, color: GH.textMuted }}>{(patients || []).length} 人</span>
				</div>
				{(!patients || patients.length === 0) ? (
					<div style={{ padding: "12px 10px", fontSize: 11, color: GH.textMuted, textAlign: "center" }}>
						暂无患者
					</div>
				) : (
					<table style={{ width: "100%", borderCollapse: "collapse" }}>
						<thead>
							<tr>
								{["ID", "患者", "性别", "出生年", "手机", "创建时间", "最后活跃"].map((h) => (
									<th key={h} style={TH}>{h}</th>
								))}
							</tr>
						</thead>
						<tbody>
							{patients.map((p, i) => {
								const pid = p.patient_id || p.id;
								const isSelected = pid === (selectedPatient?.patient_id || selectedPatient?.id);
								return (
									<tr key={pid || i}
										style={{ background: isSelected ? "rgba(88,166,255,0.12)" : "transparent", cursor: "pointer" }}
										onClick={() => setSelectedPatient(isSelected ? null : p)}>
										<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>{pid}</td>
										<td style={{ ...TD, color: GH.blue }}>{p.name || "—"}</td>
										<td style={TD}>{ENUM_ZH[p.gender] || p.gender || "—"}</td>
										<td style={TD}>{p.year_of_birth || "—"}</td>
										<td style={TD}>{p.phone || "—"}</td>
										<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>{fmtTs(p.created_at)}</td>
										<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>{fmtTs(p.last_activity_at)}</td>
									</tr>
								);
							})}
						</tbody>
					</table>
				)}
			</div>
			{selectedPatient && (
				<div style={PANEL}>
					<div style={PANEL_HEAD}>
						<span>时间线 — {selectedPatient.name || selectedPatient.id}</span>
					</div>
					<div style={{ padding: "6px 10px" }}>
						{tlLoading && <div style={{ fontSize: 11, color: GH.textMuted }}>加载中...</div>}
						{!tlLoading && (!timeline || timeline.length === 0) && (
							<div style={{ fontSize: 11, color: GH.textMuted }}>暂无时间线数据</div>
						)}
						{!tlLoading && timeline?.map((ev, i) => (
							<div key={ev.id || i} style={{ display: "flex", alignItems: "center", gap: 8,
								paddingTop: 4, paddingBottom: 4,
								borderBottom: i < timeline.length - 1 ? `1px solid ${GH.border}` : "none" }}>
								<span style={{ fontFamily: "monospace", fontSize: 10, color: GH.textMuted,
									minWidth: 72, flexShrink: 0 }}>{fmtFull(ev.time)}</span>
								<span style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
									background: { message: GH.blue, ai_suggestion: "#bc8cff", record: GH.green,
										task: GH.orange }[ev.type] || GH.textMuted }} />
								<span style={{ fontSize: 10, color: GH.textMuted, minWidth: 42, flexShrink: 0 }}>
									{{ message: "消息", ai_suggestion: "AI建议", record: "病历", task: "任务" }[ev.type] || ev.type}
								</span>
								<span style={{ fontSize: 11, color: GH.text, flex: 1, overflow: "hidden",
									textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ev.detail || "—"}</span>
								{ev.status && <StatusChip value={ev.status} />}
							</div>
						))}
					</div>
				</div>
			)}
		</>
	);
}

// ── Column configs for each tab ──────────────────────────────────────────────
const COL = {
	records: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "patient_name", label: "患者", width: 80 },
		{ key: "record_type", label: "类型", width: 80, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "content", label: "内容", width: 200, maxWidth: 300 },
		{ key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
		{ key: "created_at", label: "时间", width: 140, render: (v) => fmtTs(v) },
	],
	tasks: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "patient_name", label: "患者", width: 80 },
		{ key: "task_type", label: "类型", width: 70, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "title", label: "标题", width: 200, maxWidth: 300 },
		{ key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
		{ key: "due_at", label: "截止", width: 130, render: (v) => fmtTs(v) },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	messages: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "patient_name", label: "患者", width: 80 },
		{ key: "direction", label: "方向", width: 60, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "source", label: "来源", width: 50, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "content", label: "内容", width: 240, maxWidth: 400 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	knowledge: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "title", label: "标题", width: 160 },
		{ key: "category", label: "分类", width: 70, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "content", label: "内容", width: 240, maxWidth: 400 },
		{ key: "reference_count", label: "引用", width: 50 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	suggestions: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "record_id", label: "病历", width: 60 },
		{ key: "section", label: "类别", width: 80, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "content", label: "内容", width: 240, maxWidth: 400 },
		{ key: "decision", label: "决策", width: 80, render: (v) => <StatusChip value={v} /> },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	interviews: [
		{ key: "id", label: "ID", width: 80 },
		{ key: "patient_id", label: "患者ID", width: 70 },
		{ key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
		{ key: "turn_count", label: "轮次", width: 60 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	chats: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "session_id", label: "会话", width: 100 },
		{ key: "role", label: "角色", width: 60, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "content", label: "内容", width: 300, maxWidth: 500 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	drafts: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "patient_id", label: "患者ID", width: 70 },
		{ key: "status", label: "状态", width: 80, render: (v) => <StatusChip value={v} /> },
		{ key: "draft_text", label: "草稿", width: 280, maxWidth: 400 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	edits: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "entity_type", label: "类型", width: 80 },
		{ key: "entity_id", label: "对象", width: 60 },
		{ key: "field_name", label: "字段", width: 80 },
		{ key: "original_text", label: "原文", width: 160, maxWidth: 200 },
		{ key: "edited_text", label: "修改后", width: 160, maxWidth: 200 },
		{ key: "rule_created", label: "规则", width: 50, render: (v) => v ? "✓" : "—" },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	kb_usage: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "knowledge_item_id", label: "知识ID", width: 70 },
		{ key: "usage_context", label: "场景", width: 100 },
		{ key: "patient_id", label: "患者ID", width: 70 },
		{ key: "record_id", label: "病历ID", width: 70 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	invite_codes: [
		{ key: "code", label: "邀请码", width: 120 },
		{ key: "active", label: "有效", width: 50, render: (v) => v ? "✓" : "✗" },
		{ key: "used_count", label: "使用", width: 50 },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	audit_log: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "action", label: "操作", width: 70, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "resource_type", label: "资源", width: 80 },
		{ key: "resource_id", label: "资源ID", width: 100 },
		{ key: "ok", label: "OK", width: 40, render: (v) => v ? "✓" : "✗" },
		{ key: "ip", label: "IP", width: 110 },
		{ key: "ts", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
	pending_persona: [
		{ key: "id", label: "ID", width: 50 },
		{ key: "field", label: "字段", width: 80 },
		{ key: "proposed_rule", label: "规则", width: 200, maxWidth: 300 },
		{ key: "summary", label: "摘要", width: 160, maxWidth: 200 },
		{ key: "confidence", label: "置信", width: 50, render: (v) => ENUM_ZH[v] || v || "—" },
		{ key: "status", label: "状态", width: 70, render: (v) => <StatusChip value={v} /> },
		{ key: "created_at", label: "时间", width: 130, render: (v) => fmtTs(v) },
	],
};

// Tab definitions with keys matching the API response
const TABS = [
	{ key: "overview", label: "总览" },
	{ key: "patients", label: "患者" },
	{ key: "records", label: "病历" },
	{ key: "tasks", label: "任务" },
	{ key: "messages", label: "消息" },
	{ key: "knowledge", label: "知识库" },
	{ key: "suggestions", label: "AI建议" },
	{ key: "interviews", label: "问诊" },
	{ key: "chats", label: "对话记录" },
	{ key: "drafts", label: "消息草稿" },
	{ key: "persona", label: "人设" },
	{ key: "preferences", label: "偏好" },
	{ key: "edits", label: "修改记录" },
	{ key: "kb_usage", label: "知识引用" },
	{ key: "wechat", label: "微信" },
	{ key: "invite_codes", label: "邀请码" },
	{ key: "audit_log", label: "审计" },
	{ key: "pending_persona", label: "待审人设" },
];

// Single-item (KV) tabs
const KV_TABS = new Set(["persona", "preferences", "wechat"]);

// ── Main export ────────────────────────────────────────────────────────────────
export default function AdminDoctorDetail({ doctorId, onBack }) {
	const [doctor, setDoctor] = useState(null);
	const [related, setRelated] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [tab, setTab] = useState(0);

	useEffect(() => {
		if (!doctorId) return;
		setLoading(true);
		setError("");
		setTab(0);
		Promise.all([
			fetchJson(`/api/admin/doctors/${doctorId}`),
			getAdminDoctorRelated(doctorId),
		])
			.then(([doc, rel]) => {
				const flat = { ...doc.profile, setup: doc.setup, stats_7d: doc.stats_7d };
				setDoctor(flat);
				setRelated(rel);
			})
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, [doctorId]);

	if (!doctorId) return null;
	if (loading) return <div style={{ padding: "20px 16px", fontSize: 12, color: GH.textMuted }}>加载中...</div>;
	if (error) return (
		<div style={{ padding: "12px 16px" }}>
			<div style={{ fontSize: 12, color: GH.red, background: "rgba(248,81,73,0.12)",
				borderRadius: 6, padding: "8px 12px" }}>加载失败: {error}</div>
			<span style={{ fontSize: 11, color: GH.blue, cursor: "pointer", marginTop: 8,
				display: "inline-block" }} onClick={onBack}>&larr; 返回</span>
		</div>
	);

	function renderTab(tabKey) {
		if (tabKey === "overview") {
			return <DoctorStatStrip doctor={doctor} />;
		}
		if (tabKey === "patients") {
			return <PatientsTab patients={related?.patients?.items || []} doctorId={doctorId} />;
		}
		if (KV_TABS.has(tabKey)) {
			const section = related?.[tabKey];
			return <KVPanel title={TABS.find((t) => t.key === tabKey)?.label || tabKey} data={section?.item} />;
		}
		// Table tabs
		const section = related?.[tabKey];
		const cols = COL[tabKey];
		if (!cols) return <KVPanel title={tabKey} data={section?.item || null} />;
		return (
			<DataTable
				title={TABS.find((t) => t.key === tabKey)?.label || tabKey}
				columns={cols}
				rows={section?.items || []}
				count={section?.count}
			/>
		);
	}

	function getTabCount(tabKey) {
		if (tabKey === "overview") return null;
		return related?.[tabKey]?.count ?? null;
	}

	return (
		<div style={{ padding: "10px 16px" }}>
			<DoctorHeader doctor={doctor} onBack={onBack} />
			<Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto"
				sx={{ background: GH.card, border: `1px solid ${GH.border}`, borderRadius: 1.5,
					mb: 1.25, minHeight: 36, px: 1,
					"& .MuiTab-root": { color: GH.textMuted, fontSize: 11, minHeight: 36, py: 0.5,
						textTransform: "none", minWidth: 50, px: 1.2 },
					"& .Mui-selected": { color: GH.blue },
					"& .MuiTabs-indicator": { backgroundColor: GH.blue } }}>
				{TABS.map((t) => {
					const count = getTabCount(t.key);
					const label = count != null ? `${t.label}(${count})` : t.label;
					return <Tab key={t.key} label={label} />;
				})}
			</Tabs>
			{renderTab(TABS[tab]?.key)}
		</div>
	);
}

// ── Doctor list (fallback when no doctor selected) ──────────────────────────
function DoctorList({ onDoctorClick }) {
	const [doctors, setDoctors] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");

	useEffect(() => {
		setLoading(true);
		fetchJson("/api/admin/doctors")
			.then((data) => setDoctors(data.doctors || data.items || []))
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, []);

	if (loading) return <div style={{ padding: "20px 16px", fontSize: 12, color: GH.textMuted }}>加载中...</div>;
	if (error) return <div style={{ padding: "12px 16px", fontSize: 12, color: GH.red }}>加载失败: {error}</div>;

	return (
		<div style={{ padding: "10px 16px" }}>
			<div style={PANEL}>
				<div style={PANEL_HEAD}>
					<span>选择医生</span>
					<span style={{ fontSize: 10, color: GH.textMuted }}>{(doctors || []).length} 人</span>
				</div>
				<table style={{ width: "100%", borderCollapse: "collapse" }}>
					<thead>
						<tr>
							{["医生", "科室", "患者", "最后活跃"].map((h) => (
								<th key={h} style={TH}>{h}</th>
							))}
						</tr>
					</thead>
					<tbody>
						{(doctors || []).map((d, i) => (
							<tr key={d.doctor_id || i} style={{ cursor: "pointer" }}
								onClick={() => onDoctorClick?.(d.doctor_id)}>
								<td style={{ ...TD, color: GH.blue }}>{d.name || d.doctor_id}</td>
								<td style={TD}>{d.specialty || d.department || "—"}</td>
								<td style={TD}>{d.patient_count ?? "—"}</td>
								<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>{fmtTime(d.last_active)}</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}

export { DoctorList };
