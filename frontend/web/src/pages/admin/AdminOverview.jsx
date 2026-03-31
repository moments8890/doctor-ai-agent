/** AdminOverview — 总览 tab for Admin dashboard (GitHub Dark theme) */

import { useEffect, useState } from "react";
import { GH } from "./adminTheme";

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

// ── Safe value helper ─────────────────────────────────────────────────────────
function safe(v, fallback = "—") {
	return v != null ? v : fallback;
}

// ── Trend Badge ───────────────────────────────────────────────────────────────
function TrendBadge({ pct }) {
	if (pct == null || pct === 0)
		return <span style={{ color: GH.textMuted }}>—</span>;
	const up = pct > 0;
	const color = up ? GH.green : GH.red;
	return (
		<span style={{ fontSize: 11, fontWeight: 600, color }}>
			{up ? "↑" : "↓"}
			{Math.abs(pct)}%
		</span>
	);
}

// ── Hero Card wrapper ─────────────────────────────────────────────────────────
function HeroCard({ label, bigNumber, bigColor, sub, trend, children }) {
	return (
		<div
			style={{
				flex: 1,
				minWidth: 0,
				background: GH.card,
				border: `1px solid ${GH.border}`,
				borderRadius: 8,
				padding: 16,
				display: "flex",
				flexDirection: "column",
				justifyContent: "space-between",
			}}
		>
			<div
				style={{
					fontSize: 10,
					textTransform: "uppercase",
					letterSpacing: "0.5px",
					color: GH.textMuted,
					marginBottom: 6,
				}}
			>
				{label}
			</div>
			{children || (
				<>
					<div
						style={{
							fontSize: 28,
							fontWeight: 700,
							color: bigColor || "#fff",
							lineHeight: 1.1,
						}}
					>
						{bigNumber}
					</div>
					<div
						style={{
							display: "flex",
							justifyContent: "space-between",
							alignItems: "flex-end",
							marginTop: 6,
						}}
					>
						<span style={{ fontSize: 11, color: GH.textMuted }}>{sub}</span>
						{trend !== undefined && <TrendBadge pct={trend} />}
					</div>
				</>
			)}
		</div>
	);
}

// ── Hero: 活跃医生 ────────────────────────────────────────────────────────────
function ActiveDoctorsCard({ d }) {
	if (!d) return <HeroCard label="活跃医生" bigNumber="—" sub="" />;
	return (
		<HeroCard
			label="活跃医生"
			bigNumber={safe(d.current)}
			bigColor="#fff"
			sub={`/${safe(d.total)} 位注册`}
			trend={d.change_pct}
		/>
	);
}

// ── Hero: 问诊 ────────────────────────────────────────────────────────────────
function InterviewsCard({ d }) {
	if (!d) return <HeroCard label="问诊" bigNumber="—" sub="" />;
	const rate = d.completion_rate != null ? Math.round(d.completion_rate * 100) : "—";
	return (
		<HeroCard
			label="问诊"
			bigNumber={safe(d.started)}
			bigColor="#fff"
			sub={`完成 ${safe(d.completed)} · 完成率 ${rate}%`}
			trend={d.change_pct}
		/>
	);
}

// ── Hero: AI采纳率 ────────────────────────────────────────────────────────────
function AiAcceptanceCard({ d }) {
	if (!d) return <HeroCard label="AI采纳率" bigNumber="—" sub="" />;
	const pct = d.rate != null ? Math.round(d.rate * 100) : null;
	const rateColor =
		pct == null
			? GH.textMuted
			: pct >= 60
				? GH.green
				: pct >= 30
					? GH.orange
					: GH.red;
	return (
		<HeroCard
			label="AI采纳率"
			bigNumber={pct != null ? `${pct}%` : "—"}
			bigColor={rateColor}
			sub={`采纳${safe(d.confirmed, 0)} 编辑${safe(d.edited, 0)} 拒绝${safe(d.rejected, 0)}`}
			trend={d.change_pct}
		/>
	);
}

// ── Hero: 待回复消息 ──────────────────────────────────────────────────────────
function UnansweredCard({ d }) {
	if (!d) return <HeroCard label="待回复消息" bigNumber="—" sub="" />;
	const count = safe(d.count, 0);
	const hasMessages = count > 0;
	const bigColor = hasMessages ? GH.red : GH.green;
	const oldest =
		d.oldest_hours != null ? `最早 ${d.oldest_hours}h 前` : "\u00A0";
	return (
		<HeroCard
			label="待回复消息"
			bigNumber={count}
			bigColor={bigColor}
			sub={hasMessages ? oldest : "全部已回复"}
		/>
	);
}

// ── Hero: 系统健康 ────────────────────────────────────────────────────────────
function SystemHealthCard({ d }) {
	if (!d) return <HeroCard label="系统健康" bigNumber="—" sub="" />;
	const rate = d.error_rate ?? 1;
	let dotColor, statusText;
	if (rate < 0.05) {
		dotColor = GH.green;
		statusText = "正常";
	} else if (rate < 0.1) {
		dotColor = "#e3b341";
		statusText = "注意";
	} else {
		dotColor = GH.red;
		statusText = "异常";
	}
	return (
		<HeroCard label="系统健康">
			<div
				style={{
					display: "flex",
					alignItems: "center",
					gap: 8,
					marginBottom: 6,
				}}
			>
				<span
					style={{
						display: "inline-block",
						width: 10,
						height: 10,
						borderRadius: "50%",
						background: dotColor,
						flexShrink: 0,
					}}
				/>
				<span style={{ fontSize: 28, fontWeight: 700, color: "#fff", lineHeight: 1.1 }}>
					{statusText}
				</span>
			</div>
			<div style={{ fontSize: 11, color: GH.textMuted }}>
				P95 {safe(d.p95_latency_ms)}ms · {safe(d.calls_24h)}调用 · {safe(d.errors_24h)}错误 (24h)
			</div>
		</HeroCard>
	);
}

// ── Secondary Card ────────────────────────────────────────────────────────────
function SecondaryCard({ label, value, valueColor, suffix, trend }) {
	return (
		<div
			style={{
				background: GH.card,
				border: `1px solid ${GH.border}`,
				borderRadius: 8,
				padding: "10px 14px",
				display: "flex",
				flexDirection: "column",
				gap: 2,
			}}
		>
			<div
				style={{
					fontSize: 10,
					textTransform: "uppercase",
					letterSpacing: "0.5px",
					color: GH.textMuted,
				}}
			>
				{label}
			</div>
			<div
				style={{
					display: "flex",
					alignItems: "baseline",
					justifyContent: "space-between",
				}}
			>
				<span>
					<span style={{ fontSize: 18, fontWeight: 700, color: valueColor || GH.text }}>
						{value}
					</span>
					{suffix && (
						<span style={{ fontSize: 12, color: GH.textMuted, marginLeft: 2 }}>
							{suffix}
						</span>
					)}
				</span>
				{trend !== undefined && <TrendBadge pct={trend} />}
			</div>
		</div>
	);
}

// ── Secondary Metrics Grid ────────────────────────────────────────────────────
function SecondaryGrid({ s }) {
	if (!s) return null;

	// response_gap color
	const gapHours = s.response_gap_p50_hours;
	const gapColor =
		gapHours == null
			? GH.text
			: gapHours > 24
				? GH.red
				: gapHours > 12
					? GH.orange
					: GH.text;

	const overdueColor =
		(s.overdue_tasks ?? 0) > 0 ? GH.red : GH.text;

	const cards = [
		{
			label: "病历",
			value: safe(s.new_records?.current),
			trend: s.new_records?.change_pct,
		},
		{
			label: "AI回复",
			value: safe(s.ai_replies?.current),
			trend: s.ai_replies?.change_pct,
		},
		{
			label: "患者消息",
			value: safe(s.patient_messages?.current),
			trend: s.patient_messages?.change_pct,
		},
		{
			label: "新患者",
			value: safe(s.new_patients?.current),
			trend: s.new_patients?.change_pct,
		},
		{
			label: "知识条目",
			value: safe(s.new_knowledge?.current),
			trend: s.new_knowledge?.change_pct,
		},
		{
			label: "对话轮次",
			value: s.avg_interview_turns != null ? s.avg_interview_turns : "—",
			suffix: s.avg_interview_turns != null ? "轮" : undefined,
		},
		{
			label: "逾期任务",
			value: safe(s.overdue_tasks, 0),
			valueColor: overdueColor,
		},
		{
			label: "回复时效 P50",
			value: gapHours != null ? gapHours : "—",
			suffix: gapHours != null ? "h" : undefined,
			valueColor: gapColor,
		},
	];

	return (
		<div
			style={{
				display: "grid",
				gridTemplateColumns: "repeat(4, 1fr)",
				gap: 10,
			}}
		>
			{cards.map((c, i) => (
				<SecondaryCard key={i} {...c} />
			))}
		</div>
	);
}

// ── Activity Timeline ────────────────────────────────────────────────────────

const EVENT_META = {
	record: { label: "病历", color: GH.blue, icon: "📋" },
	ai_suggestion: { label: "AI诊断", color: GH.green, icon: "🤖" },
	task: { label: "任务", color: GH.orange, icon: "📌" },
	message: { label: "消息", color: "#c9d1d9", icon: "💬" },
};

const STATUS_BADGE = {
	confirmed: { label: "采纳", bg: "rgba(63,185,80,0.15)", fg: GH.green },
	edited: { label: "编辑", bg: "rgba(88,166,255,0.15)", fg: GH.blue },
	rejected: { label: "拒绝", bg: "rgba(248,81,73,0.15)", fg: GH.red },
	pending: { label: "待处理", bg: "rgba(247,129,102,0.12)", fg: GH.orange },
	done: { label: "完成", bg: "rgba(63,185,80,0.15)", fg: GH.green },
	completed: { label: "完成", bg: "rgba(63,185,80,0.15)", fg: GH.green },
};

function StatusBadge({ status }) {
	const s = String(status || "").toLowerCase();
	const meta = STATUS_BADGE[s];
	if (!meta) return status ? <span style={{ fontSize: 10, color: GH.textMuted }}>{status}</span> : null;
	return (
		<span style={{
			fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 3,
			background: meta.bg, color: meta.fg,
		}}>
			{meta.label}
		</span>
	);
}

function ActivityTimeline({ items }) {
	if (!items || items.length === 0) return null;
	return (
		<div style={{
			background: GH.card, border: `1px solid ${GH.border}`,
			borderRadius: 8, overflow: "hidden", marginTop: 16,
		}}>
			<div style={{
				padding: "8px 14px", fontSize: 11, fontWeight: 600, color: GH.text,
				borderBottom: `1px solid ${GH.border}`, background: GH.hoverBg,
				display: "flex", justifyContent: "space-between", alignItems: "center",
			}}>
				<span>最近活动 (7d)</span>
				<span style={{ fontSize: 10, color: GH.textMuted }}>{items.length} 条</span>
			</div>
			<table style={{ width: "100%", borderCollapse: "collapse" }}>
				<thead>
					<tr>
						{["时间", "类型", "医生", "详情", "状态"].map(h => (
							<th key={h} style={{
								textAlign: "left", padding: "5px 10px", fontSize: 10,
								color: GH.textMuted, fontWeight: 500, textTransform: "uppercase",
								letterSpacing: "0.3px", background: GH.hoverBg,
								borderBottom: `1px solid ${GH.border}`, whiteSpace: "nowrap",
							}}>{h}</th>
						))}
					</tr>
				</thead>
				<tbody>
					{items.map((a, i) => {
						const meta = EVENT_META[a.event_type] || { label: a.event_type, color: GH.textMuted };
						return (
							<tr key={i} style={{ borderBottom: `1px solid ${GH.border}` }}>
								<td style={{
									padding: "5px 10px", fontSize: 11, color: GH.textMuted,
									fontFamily: "ui-monospace, monospace", whiteSpace: "nowrap",
								}}>
									{a.created_at || "—"}
								</td>
								<td style={{ padding: "5px 10px" }}>
									<span style={{
										fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 3,
										background: `${meta.color}22`, color: meta.color,
									}}>
										{meta.label}
									</span>
								</td>
								<td style={{
									padding: "5px 10px", fontSize: 11, color: GH.blue,
									whiteSpace: "nowrap", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis",
								}}>
									{a.doctor_id || "—"}
								</td>
								<td style={{
									padding: "5px 10px", fontSize: 11, color: GH.text,
									maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
								}}>
									{a.detail || "—"}
								</td>
								<td style={{ padding: "5px 10px" }}>
									<StatusBadge status={a.status} />
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		</div>
	);
}

// ── Alert Strip ──────────────────────────────────────────────────────────────
function AlertStrip({ alerts }) {
	if (!alerts || alerts.length === 0) return null;
	return (
		<div style={{ marginTop: 16 }}>
			{alerts.map((a, i) => {
				const isErr = a.level === "error";
				return (
					<div
						key={i}
						style={{
							display: "flex",
							alignItems: "center",
							gap: 8,
							padding: "6px 12px",
							fontSize: 12,
							borderRadius: 6,
							marginBottom: 4,
							background: isErr
								? "rgba(248,81,73,0.12)"
								: "rgba(247,129,102,0.10)",
							color: isErr ? GH.red : GH.orange,
						}}
					>
						<span
							style={{
								width: 7,
								height: 7,
								borderRadius: "50%",
								flexShrink: 0,
								background: isErr ? GH.red : GH.orange,
							}}
						/>
						<span>
							<strong>{a.label}:</strong>&nbsp;{a.detail}
						</span>
					</div>
				);
			})}
		</div>
	);
}

// ── Main export ──────────────────────────────────────────────────────────────
export default function AdminOverview({ onDoctorClick }) {
	const [data, setData] = useState(null);
	const [activity, setActivity] = useState(null);
	const [error, setError] = useState("");
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		Promise.all([
			fetchJson("/api/admin/overview"),
			fetchJson("/api/admin/activity?limit=30").catch(() => ({ items: [] })),
		])
			.then(([ov, act]) => {
				setData(ov);
				setActivity(act.items || act.activities || []);
			})
			.catch((e) => setError(e.message))
			.finally(() => setLoading(false));
	}, []);

	if (loading) {
		return (
			<div style={{ padding: "20px 16px", fontSize: 12, color: GH.textMuted }}>
				加载中...
			</div>
		);
	}
	if (error) {
		return (
			<div
				style={{
					padding: "12px 16px",
					fontSize: 12,
					color: GH.red,
					background: "rgba(248,81,73,0.12)",
					borderRadius: 6,
					margin: "10px 16px",
				}}
			>
				加载失败: {error}
			</div>
		);
	}

	// Support both new shape (hero/secondary) and old shape (stats)
	const hero = data?.hero || null;
	const secondary = data?.secondary || null;
	const alerts = data?.alerts || [];

	// Fallback: if backend returns old shape, show a message
	if (!hero && data?.stats) {
		return (
			<div style={{ padding: "20px 16px", fontSize: 12, color: GH.textMuted }}>
				<div style={{
					background: "rgba(88,166,255,0.12)", color: GH.blue,
					padding: "8px 12px", borderRadius: 6, marginBottom: 12,
				}}>
					后端 API 需要重启以加载新版概览数据。当前显示旧版格式。
				</div>
				<div style={{ background: GH.card, border: `1px solid ${GH.border}`, borderRadius: 8, padding: 16 }}>
					<pre style={{ fontSize: 11, color: GH.text, whiteSpace: "pre-wrap" }}>
						{JSON.stringify(data.stats, null, 2)}
					</pre>
				</div>
				<ActivityTimeline items={activity} />
			</div>
		);
	}

	return (
		<div style={{ padding: "10px 16px" }}>
			{/* Hero Cards — 5 in a row */}
			<div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
				<ActiveDoctorsCard d={hero?.active_doctors} />
				<InterviewsCard d={hero?.interviews} />
				<AiAcceptanceCard d={hero?.ai_acceptance} />
				<UnansweredCard d={hero?.unanswered_messages} />
				<SystemHealthCard d={hero?.system_health} />
			</div>

			{/* Secondary Metrics — 4-column grid */}
			<SecondaryGrid s={secondary} />

			{/* Alerts */}
			<AlertStrip alerts={alerts} />

			{/* Activity Timeline */}
			<ActivityTimeline items={activity} />
		</div>
	);
}
