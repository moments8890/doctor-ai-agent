/** AdminDoctorDetail — drill-down view for a single doctor */

import { Box } from "@mui/material";
import { useEffect, useState } from "react";

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

// ── Dense shared styles (mirrors AdminOverview) ────────────────────────────────
const PANEL = {
	background: "#fff",
	border: "1px solid #e0e0e0",
	borderRadius: 4,
	overflow: "hidden",
	marginBottom: 10,
};
const PANEL_HEAD = {
	padding: "6px 10px",
	fontSize: 11,
	fontWeight: 600,
	color: "#333",
	borderBottom: "1px solid #f0f0f0",
	display: "flex",
	justifyContent: "space-between",
	alignItems: "center",
	background: "#fafafa",
};
const TH = {
	textAlign: "left",
	padding: "4px 8px",
	fontSize: 10,
	color: "#888",
	fontWeight: 500,
	textTransform: "uppercase",
	letterSpacing: "0.3px",
	background: "#f9f9f9",
	borderBottom: "1px solid #eee",
	whiteSpace: "nowrap",
};
const TD = {
	padding: "4px 8px",
	borderBottom: "1px solid #f5f5f5",
	whiteSpace: "nowrap",
	fontSize: 11,
};

// ── Dense chip ─────────────────────────────────────────────────────────────────
function DenseChip({ label, color = "gray" }) {
	const MAP = {
		green: { bg: "#e8f5e9", fg: "#2e7d32" },
		red: { bg: "#fce4ec", fg: "#c62828" },
		amber: { bg: "#fff3e0", fg: "#e65100" },
		blue: { bg: "#e3f2fd", fg: "#1565c0" },
		purple: { bg: "#f3e5f5", fg: "#6a1b9a" },
		gray: { bg: "#f5f5f5", fg: "#888" },
	};
	const { bg, fg } = MAP[color] || MAP.gray;
	return (
		<span
			style={{
				display: "inline-block",
				padding: "1px 5px",
				borderRadius: 3,
				fontSize: 10,
				fontWeight: 500,
				background: bg,
				color: fg,
			}}
		>
			{label}
		</span>
	);
}

// ── Format timestamp ───────────────────────────────────────────────────────────
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

// ── Setup checklist inline ─────────────────────────────────────────────────────
function SetupChecklist({ setup }) {
	if (!setup) return null;
	const items = [
		{ label: `KB×${setup.kb_count ?? 0}`, ok: (setup.kb_count ?? 0) > 0 },
		{ label: "首患者", ok: !!setup.has_patients },
		{ label: "首AI", ok: !!setup.has_ai_usage },
		{ label: "首病历", ok: !!setup.has_records },
	];
	return (
		<span
			style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11 }}
		>
			{items.map((item, i) => (
				<span
					key={i}
					style={{ color: item.ok ? "#2e7d32" : "#c62828", fontWeight: 500 }}
				>
					{item.ok ? "✓" : "✗"}&nbsp;{item.label}
				</span>
			))}
		</span>
	);
}

// ── Doctor header ──────────────────────────────────────────────────────────────
function DoctorHeader({ doctor, onBack }) {
	if (!doctor) return null;
	return (
		<Box
			sx={{
				p: 1,
				px: 1.5,
				display: "flex",
				justifyContent: "space-between",
				alignItems: "center",
				background: "#fff",
				border: "1px solid #e0e0e0",
				borderRadius: 1,
				mb: 1.25,
			}}
		>
			<Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
				<span
					style={{
						color: "#1565c0",
						cursor: "pointer",
						fontSize: 11,
						userSelect: "none",
					}}
					onClick={onBack}
				>
					← 返回
				</span>
				<span style={{ fontSize: 13, fontWeight: 700 }}>
					{doctor.name || doctor.doctor_id}
				</span>
				{doctor.department && (
					<span style={{ fontSize: 11, color: "#666" }}>
						{doctor.department}
					</span>
				)}
				<span style={{ fontSize: 10, color: "#888", fontFamily: "monospace" }}>
					· ID:&nbsp;{doctor.doctor_id}
					&nbsp;· 注册&nbsp;{fmtDate(doctor.created_at)}
					&nbsp;· 最后活跃&nbsp;{fmtTime(doctor.last_active)}
				</span>
			</Box>
			<SetupChecklist setup={doctor.setup} />
		</Box>
	);
}

// ── Stat strip for doctor ──────────────────────────────────────────────────────
function DoctorStatStrip({ doctor }) {
	if (!doctor) return null;
	const s = doctor.stats_7d || {};

	const adoptionRate =
		s.ai_adoption != null ? Math.round(s.ai_adoption * 100) : null;
	const adoptionColor =
		adoptionRate == null
			? "#888"
			: adoptionRate >= 70
				? "#2e7d32"
				: adoptionRate >= 40
					? "#e65100"
					: "#c62828";

	const taskRate =
		(s.tasks_total ?? 0) > 0
			? Math.round(((s.tasks_done ?? 0) / s.tasks_total) * 100)
			: null;

	const cells = [
		{
			label: "患者",
			value: s.patients ?? "—",
			sub: s.patients_delta != null ? `+${s.patients_delta} 本周` : "7d",
			color: "#1a1a1a",
		},
		{
			label: "消息 7d",
			value: s.messages ?? "—",
			sub: "",
			color: "#1a1a1a",
		},
		{
			label: "AI采纳率",
			value: adoptionRate != null ? `${adoptionRate}%` : "—",
			sub:
				adoptionRate != null
					? `采${s.ai_accepted ?? 0} 改${s.ai_edited ?? 0} 拒${s.ai_rejected ?? 0}`
					: "",
			color: adoptionColor,
		},
		{
			label: "病历 7d",
			value: s.records ?? "—",
			sub: "",
			color: "#1a1a1a",
		},
		{
			label: "任务完成率",
			value: taskRate != null ? `${taskRate}%` : "—",
			sub: taskRate != null ? `${s.tasks_done ?? 0}/${s.tasks_total ?? 0}` : "",
			color: taskRate == null ? "#888" : taskRate >= 70 ? "#2e7d32" : "#e65100",
		},
		{
			label: "平均响应",
			value: "—",
			sub: "",
			color: "#888",
		},
	];

	return (
		<div
			style={{
				display: "flex",
				gap: 0,
				background: "#fff",
				border: "1px solid #e0e0e0",
				borderRadius: 4,
				overflow: "hidden",
				marginBottom: 10,
			}}
		>
			{cells.map((c, i) => (
				<div
					key={i}
					style={{
						flex: 1,
						padding: "8px 12px",
						borderRight: i < cells.length - 1 ? "1px solid #f0f0f0" : "none",
					}}
				>
					<div
						style={{
							fontSize: 10,
							color: "#888",
							textTransform: "uppercase",
							letterSpacing: "0.3px",
						}}
					>
						{c.label}
					</div>
					<div
						style={{
							fontSize: 18,
							fontWeight: 700,
							marginTop: 1,
							color: c.color,
						}}
					>
						{c.value}
					</div>
					<div style={{ fontSize: 10, color: "#999" }}>{c.sub || "\u00a0"}</div>
				</div>
			))}
		</div>
	);
}

// ── Patient table ──────────────────────────────────────────────────────────────
function PatientTable({ patients, selectedPatientId, onPatientClick }) {
	if (!patients) return null;
	return (
		<div style={{ ...PANEL, marginBottom: 10 }}>
			<div style={PANEL_HEAD}>
				<span>患者列表</span>
				<span style={{ fontSize: 10, color: "#888" }}>
					{patients.length} 人
				</span>
			</div>
			<table style={{ width: "100%", borderCollapse: "collapse" }}>
				<thead>
					<tr>
						{[
							"患者",
							"性别/年龄",
							"注册",
							"消息数",
							"病历",
							"待处理",
							"最后消息",
							"状态",
						].map((h) => (
							<th key={h} style={TH}>
								{h}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{patients.map((p, i) => {
						const hasPending = (p.pending_tasks ?? 0) > 0;
						const isSelected = p.patient_id === selectedPatientId;
						return (
							<tr
								key={p.patient_id || i}
								style={{
									background: isSelected
										? "#e3f2fd"
										: hasPending
											? "#fce4ec"
											: "transparent",
									cursor: "pointer",
								}}
								onClick={() => onPatientClick(p)}
							>
								<td style={{ ...TD, color: "#1565c0" }}>
									{p.name || p.patient_id}
								</td>
								<td style={TD}>
									{p.gender ? `${p.gender}` : "—"}
									{p.age != null ? `/${p.age}岁` : ""}
								</td>
								<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>
									{fmtDate(p.created_at)}
								</td>
								<td style={TD}>{p.msg_count ?? "—"}</td>
								<td style={TD}>{p.rec_count ?? "—"}</td>
								<td style={TD}>
									{hasPending ? (
										<DenseChip label={String(p.pending_tasks)} color="red" />
									) : (
										"—"
									)}
								</td>
								<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>
									{fmtTime(p.last_message)}
								</td>
								<td style={TD}>
									<DenseChip
										label={hasPending ? "关注" : "正常"}
										color={hasPending ? "red" : "green"}
									/>
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		</div>
	);
}

// ── Timeline dot color by event type ──────────────────────────────────────────
function dotColor(type) {
	switch (type) {
		case "message":
			return "#1565c0";
		case "ai_suggestion":
			return "#6a1b9a";
		case "record":
			return "#2e7d32";
		case "task":
			return "#e65100";
		default:
			return "#888";
	}
}

function typeLabel(type) {
	switch (type) {
		case "message":
			return "消息";
		case "ai_suggestion":
			return "AI建议";
		case "record":
			return "病历";
		case "task":
			return "任务";
		default:
			return type || "—";
	}
}

function statusColor(status) {
	if (!status) return "gray";
	const s = String(status).toLowerCase();
	if (["accepted", "completed", "已回复", "完成", "采纳"].includes(s))
		return "green";
	if (["pending", "draft", "待回复", "草稿"].includes(s)) return "amber";
	if (["rejected", "拒绝"].includes(s)) return "red";
	return "gray";
}

// ── Case timeline ──────────────────────────────────────────────────────────────
function CaseTimeline({ doctorId, patientId, patientName }) {
	const [events, setEvents] = useState(null);
	const [error, setError] = useState("");
	const [loading, setLoading] = useState(false);

	useEffect(() => {
		if (!doctorId || !patientId) return;
		setLoading(true);
		setError("");
		fetchJson(`/api/admin/doctors/${doctorId}/timeline?patient_id=${patientId}`)
			.then((data) => setEvents(data.events || data.items || []))
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, [doctorId, patientId]);

	return (
		<div style={PANEL}>
			<div style={PANEL_HEAD}>
				<span>案例时间线 — {patientName || patientId}</span>
				<a
					href={`/debug?doctor_id=${doctorId}&patient_id=${patientId}`}
					target="_blank"
					rel="noopener noreferrer"
					style={{ fontSize: 10, color: "#1565c0", textDecoration: "none" }}
				>
					查看LLM调用 →
				</a>
			</div>
			<div style={{ padding: "6px 10px" }}>
				{loading && <div style={{ fontSize: 11, color: "#888" }}>加载中…</div>}
				{error && (
					<div style={{ fontSize: 11, color: "#c62828" }}>
						加载失败: {error}
					</div>
				)}
				{!loading && !error && events && events.length === 0 && (
					<div style={{ fontSize: 11, color: "#888" }}>暂无时间线数据</div>
				)}
				{!loading &&
					!error &&
					events?.map((ev, i) => (
						<div
							key={ev.id || i}
							style={{
								display: "flex",
								alignItems: "center",
								gap: 8,
								paddingTop: 4,
								paddingBottom: 4,
								borderBottom:
									i < events.length - 1 ? "1px solid #f5f5f5" : "none",
							}}
						>
							{/* Timestamp */}
							<span
								style={{
									fontFamily: "monospace",
									fontSize: 10,
									color: "#888",
									minWidth: 72,
									flexShrink: 0,
								}}
							>
								{fmtFull(ev.time)}
							</span>
							{/* Colored dot */}
							<span
								style={{
									width: 8,
									height: 8,
									borderRadius: "50%",
									flexShrink: 0,
									background: dotColor(ev.type),
								}}
							/>
							{/* Type label */}
							<span
								style={{
									fontSize: 10,
									color: "#888",
									minWidth: 42,
									flexShrink: 0,
								}}
							>
								{typeLabel(ev.type)}
							</span>
							{/* Detail */}
							<span
								style={{
									fontSize: 11,
									color: "#333",
									flex: 1,
									overflow: "hidden",
									textOverflow: "ellipsis",
									whiteSpace: "nowrap",
								}}
							>
								{ev.detail || "—"}
							</span>
							{/* Status chip */}
							{ev.status && (
								<DenseChip label={ev.status} color={statusColor(ev.status)} />
							)}
						</div>
					))}
			</div>
		</div>
	);
}

// ── Doctor list (fallback when no doctor selected) ─────────────────────────────
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

	if (loading)
		return (
			<div style={{ padding: "20px 16px", fontSize: 12, color: "#888" }}>
				加载中…
			</div>
		);
	if (error)
		return (
			<div style={{ padding: "12px 16px", fontSize: 12, color: "#c62828" }}>
				加载失败: {error}
			</div>
		);

	return (
		<div style={{ padding: "10px 16px" }}>
			<div style={PANEL}>
				<div style={PANEL_HEAD}>
					<span>选择医生</span>
					<span style={{ fontSize: 10, color: "#888" }}>
						{(doctors || []).length} 人
					</span>
				</div>
				<table style={{ width: "100%", borderCollapse: "collapse" }}>
					<thead>
						<tr>
							{["医生", "科室", "患者", "最后活跃"].map((h) => (
								<th key={h} style={TH}>
									{h}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{(doctors || []).map((d, i) => (
							<tr
								key={d.doctor_id || i}
								style={{ cursor: "pointer" }}
								onClick={() => onDoctorClick?.(d.doctor_id)}
							>
								<td style={{ ...TD, color: "#1565c0" }}>
									{d.name || d.doctor_id}
								</td>
								<td style={TD}>{d.specialty || d.department || "—"}</td>
								<td style={TD}>{d.patient_count ?? "—"}</td>
								<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>
									{fmtTime(d.last_active)}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}

// ── Main export ────────────────────────────────────────────────────────────────
export default function AdminDoctorDetail({ doctorId, onBack }) {
	const [doctor, setDoctor] = useState(null);
	const [patients, setPatients] = useState(null);
	const [selectedPatient, setSelectedPatient] = useState(null); // { patient_id, name }
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");

	useEffect(() => {
		if (!doctorId) return;
		setLoading(true);
		setError("");
		setSelectedPatient(null);
		Promise.all([
			fetchJson(`/api/admin/doctors/${doctorId}`),
			fetchJson(`/api/admin/doctors/${doctorId}/patients`),
		])
			.then(([doc, pts]) => {
				// Flatten profile into top level for easier access
				const flat = { ...doc.profile, setup: doc.setup, stats_7d: doc.stats_7d };
				setDoctor(flat);
				setPatients(pts.patients || pts.items || []);
			})
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, [doctorId]);

	if (!doctorId) return null;

	if (loading) {
		return (
			<div style={{ padding: "20px 16px", fontSize: 12, color: "#888" }}>
				加载中…
			</div>
		);
	}
	if (error) {
		return (
			<div style={{ padding: "12px 16px" }}>
				<div
					style={{
						fontSize: 12,
						color: "#c62828",
						background: "#fce4ec",
						borderRadius: 4,
						padding: "8px 12px",
					}}
				>
					加载失败: {error}
				</div>
				<span
					style={{
						fontSize: 11,
						color: "#1565c0",
						cursor: "pointer",
						marginTop: 8,
						display: "inline-block",
					}}
					onClick={onBack}
				>
					← 返回
				</span>
			</div>
		);
	}

	return (
		<div style={{ padding: "10px 16px" }}>
			<DoctorHeader doctor={doctor} onBack={onBack} />
			<DoctorStatStrip doctor={doctor} />
			<PatientTable
				patients={patients}
				selectedPatientId={selectedPatient?.patient_id}
				onPatientClick={(p) =>
					setSelectedPatient((prev) =>
						prev?.patient_id === p.patient_id ? null : p,
					)
				}
			/>
			{selectedPatient && (
				<CaseTimeline
					doctorId={doctorId}
					patientId={selectedPatient.patient_id}
					patientName={selectedPatient.name}
				/>
			)}
		</div>
	);
}

// ── Named export for doctor list ───────────────────────────────────────────────
export { DoctorList };
