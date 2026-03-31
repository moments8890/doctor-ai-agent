/** AdminOverview — 总览 tab for Admin dashboard */

import { useEffect, useState } from "react";

// ── API helpers ────────────────────────────────────────────────────────────────
async function fetchJson(url) {
	const token =
		localStorage.getItem("adminToken") || (import.meta.env.DEV ? "dev" : "");
	const res = await fetch(url, {
		headers: token ? { "X-Admin-Token": token } : {},
	});
	if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
	return res.json();
}

// ── Dense shared styles ────────────────────────────────────────────────────────
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

// ── Chip helper ────────────────────────────────────────────────────────────────
function DenseChip({ label, color = "gray" }) {
	const MAP = {
		green: { bg: "#e8f5e9", fg: "#2e7d32" },
		red: { bg: "#fce4ec", fg: "#c62828" },
		amber: { bg: "#fff3e0", fg: "#e65100" },
		blue: { bg: "#e3f2fd", fg: "#1565c0" },
		yellow: { bg: "#fffde7", fg: "#f57f17" },
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

// ── Status → chip color map ────────────────────────────────────────────────────
function statusColor(status) {
	if (!status) return "gray";
	const s = String(status).toLowerCase();
	if (["accepted", "completed", "已回复", "完成", "采纳"].includes(s))
		return "green";
	if (["pending", "draft", "待回复", "草稿"].includes(s)) return "amber";
	if (["rejected", "拒绝"].includes(s)) return "red";
	if (["complete", "完整"].includes(s)) return "blue";
	return "gray";
}

// ── AI adoption chip ───────────────────────────────────────────────────────────
function AdoptionChip({ rate }) {
	if (rate == null) return <DenseChip label="—" color="gray" />;
	const pct = Math.round(rate * 100);
	const color = pct >= 70 ? "green" : pct >= 40 ? "amber" : "gray";
	return <DenseChip label={`${pct}%`} color={color} />;
}

// ── Format timestamp compactly ─────────────────────────────────────────────────
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

// ── Stat Strip ─────────────────────────────────────────────────────────────────
function StatStrip({ stats }) {
	if (!stats) return null;

	const cells = [
		{
			label: "活跃医生",
			value: `${stats.active_doctors ?? "—"}`,
			valueSuffix: stats.total_doctors != null ? `/${stats.total_doctors}` : "",
			sub: stats.inactive_doctor_note || "",
			color:
				(stats.active_doctors ?? 0) >= (stats.total_doctors ?? 1)
					? "#2e7d32"
					: "#e65100",
		},
		{
			label: "患者消息 24h",
			value: stats.messages_24h ?? "—",
			sub: stats.messages_24h_detail || "",
			color: "#1a1a1a",
		},
		{
			label: "病历 24h",
			value: stats.records_24h ?? "—",
			sub: stats.records_24h_detail || "",
			color: "#1a1a1a",
		},
		{
			label: "AI建议",
			value: stats.suggestions_24h ?? "—",
			sub: stats.suggestions_detail || "",
			color: "#1a1a1a",
		},
		{
			label: "任务",
			value: stats.pending_tasks ?? "—",
			sub: stats.tasks_detail || "",
			color: (stats.overdue_tasks ?? 0) > 0 ? "#e65100" : "#1a1a1a",
		},
		{
			label: "LLM调用 1h",
			value: stats.llm_calls_1h ?? "—",
			sub: stats.llm_detail || "",
			color: "#1a1a1a",
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
						{c.valueSuffix && (
							<span style={{ fontSize: 12, color: "#999" }}>
								{c.valueSuffix}
							</span>
						)}
					</div>
					<div style={{ fontSize: 10, color: "#999" }}>
						{c.sub || "\u00A0"}
					</div>
				</div>
			))}
		</div>
	);
}

// ── Alert Strip ────────────────────────────────────────────────────────────────
function AlertStrip({ alerts }) {
	if (!alerts || alerts.length === 0) return null;
	return (
		<div style={{ marginBottom: 10 }}>
			{alerts.map((a, i) => {
				const isErr = a.level === "error";
				return (
					<div
						key={i}
						style={{
							display: "flex",
							alignItems: "center",
							gap: 6,
							padding: "4px 10px",
							fontSize: 11,
							borderRadius: 3,
							marginBottom: 3,
							background: isErr ? "#fce4ec" : "#fff8e1",
							color: isErr ? "#b71c1c" : "#e65100",
						}}
					>
						<span
							style={{
								width: 6,
								height: 6,
								borderRadius: "50%",
								flexShrink: 0,
								background: isErr ? "#d32f2f" : "#ff9800",
							}}
						/>
						<strong>{a.label}:</strong>&nbsp;{a.detail}
					</div>
				);
			})}
		</div>
	);
}

// ── Doctor Table ───────────────────────────────────────────────────────────────
function DoctorTable({ doctors, onDoctorClick }) {
	if (!doctors) return null;
	return (
		<div style={PANEL}>
			<div style={PANEL_HEAD}>
				<span>医生</span>
				<span
					style={{ fontSize: 10, color: "#1565c0", cursor: "pointer" }}
					onClick={() => onDoctorClick?.(null)}
				>
					详情 →
				</span>
			</div>
			<table style={{ width: "100%", borderCollapse: "collapse" }}>
				<thead>
					<tr>
						{[
							"医生",
							"科室",
							"患者",
							"今日消息",
							"AI采纳",
							"待处理",
							"最后活跃",
							"KB",
						].map((h) => (
							<th key={h} style={TH}>
								{h}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{doctors.map((d, i) => {
						const inactive = d.inactive_days > 3;
						return (
							<tr
								key={d.doctor_id || i}
								style={inactive ? { background: "#fffde7" } : {}}
							>
								<td
									style={{ ...TD, color: "#1565c0", cursor: "pointer" }}
									onClick={() => onDoctorClick?.(d.doctor_id)}
								>
									{d.name || d.doctor_id}
								</td>
								<td style={TD}>{d.specialty || "—"}</td>
								<td style={TD}>{d.patient_count ?? "—"}</td>
								<td style={TD}>{d.messages_today ?? "—"}</td>
								<td style={TD}>
									<AdoptionChip rate={d.ai_adoption_rate} />
								</td>
								<td style={TD}>
									{d.overdue_tasks > 0 ? (
										<DenseChip label={`${d.overdue_tasks}逾期`} color="red" />
									) : d.pending_messages > 0 ? (
										<DenseChip
											label={`${d.pending_messages}消息`}
											color="amber"
										/>
									) : (
										"—"
									)}
								</td>
								<td style={{ ...TD, fontFamily: "monospace" }}>
									{fmtTime(d.last_active)}
								</td>
								<td style={TD}>
									{d.kb_count != null && d.kb_count < 3 ? (
										<DenseChip label={String(d.kb_count)} color="red" />
									) : (
										(d.kb_count ?? "—")
									)}
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		</div>
	);
}

// ── Activity Feed ──────────────────────────────────────────────────────────────
const STATUS_ZH = {
	accepted: "采纳",
	pending: "待回复",
	rejected: "拒绝",
	completed: "完成",
	draft: "草稿",
	complete: "完整",
};

function ActivityFeed({ activities }) {
	if (!activities) return null;
	return (
		<div style={PANEL}>
			<div style={PANEL_HEAD}>
				<span>最近活动</span>
			</div>
			<table style={{ width: "100%", borderCollapse: "collapse" }}>
				<thead>
					<tr>
						{["时间", "医生", "类型", "详情", "状态"].map((h) => (
							<th key={h} style={TH}>
								{h}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{activities.map((a, i) => {
						const statusLabel = STATUS_ZH[a.status] || a.status || "—";
						const color = statusColor(a.status);
						const isPending = ["pending", "待回复"].includes(a.status);
						return (
							<tr key={i} style={isPending ? { background: "#fff3e0" } : {}}>
								<td style={{ ...TD, fontFamily: "monospace", fontSize: 10 }}>
									{fmtTime(a.created_at)}
								</td>
								<td style={TD}>{a.doctor_name || a.doctor_id || "—"}</td>
								<td style={TD}>{a.event_type || "—"}</td>
								<td
									style={{
										...TD,
										maxWidth: 160,
										overflow: "hidden",
										textOverflow: "ellipsis",
									}}
								>
									{a.detail || "—"}
								</td>
								<td style={TD}>
									<DenseChip label={statusLabel} color={color} />
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		</div>
	);
}

// ── Main export ────────────────────────────────────────────────────────────────
export default function AdminOverview({ onDoctorClick }) {
	const [overview, setOverview] = useState(null);
	const [doctors, setDoctors] = useState(null);
	const [activity, setActivity] = useState(null);
	const [error, setError] = useState("");
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		setLoading(true);
		setError("");
		Promise.all([
			fetchJson("/api/admin/overview"),
			fetchJson("/api/admin/doctors"),
			fetchJson("/api/admin/activity?limit=15"),
		])
			.then(([ov, dr, act]) => {
				setOverview(ov);
				setDoctors(dr.doctors || dr.items || []);
				setActivity(act.activities || act.items || []);
			})
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, []);

	if (loading) {
		return (
			<div style={{ padding: "20px 16px", fontSize: 12, color: "#888" }}>
				加载中…
			</div>
		);
	}
	if (error) {
		return (
			<div
				style={{
					padding: "12px 16px",
					fontSize: 12,
					color: "#c62828",
					background: "#fce4ec",
					borderRadius: 4,
					margin: "10px 0",
				}}
			>
				加载失败: {error}
			</div>
		);
	}

	return (
		<div style={{ padding: "10px 16px" }}>
			<StatStrip stats={overview?.stats} />
			<AlertStrip alerts={overview?.alerts} />
			<div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
				<DoctorTable doctors={doctors} onDoctorClick={onDoctorClick} />
				<ActivityFeed activities={activity} />
			</div>
		</div>
	);
}
