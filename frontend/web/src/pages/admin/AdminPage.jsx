/** @route /admin, /admin/:section
 *  GitHub Dark sidebar admin shell
 */

import { Box, Typography } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import {
	getAdminRoutingMetrics,
	onAdminAuthError,
	setAdminToken,
} from "../../api";
import { adminTheme } from "../../theme";
import AdminDoctorDetail, { DoctorList } from "./AdminDoctorDetail";
import AdminOverview from "./AdminOverview";
import AdminRawData, { TABLE_GROUPS } from "./AdminRawData";
import AdminPageV3 from "./v3";
import { setPageTitle } from "../../lib/pageTitle";

const ADMIN_TOKEN_KEY = "adminToken";
const DEV_MODE = import.meta.env.DEV;

// In dev mode, set token synchronously before any component renders
if (DEV_MODE) setAdminToken("dev");

// ── GitHub Dark palette ──────────────────────────────────────────────────────
import { GH } from "./adminTheme";
export { GH };

// All DB table keys (flat)
const ALL_TABLE_KEYS = Object.values(TABLE_GROUPS).flat();

// ── Sidebar nav definition ───────────────────────────────────────────────────
const NAV_SECTIONS = [
	{
		label: "数据",
		items: [
			{ key: "overview", label: "总览" },
			{ key: "doctors", label: "医生" },
			{ key: "cleanup", label: "数据清理" },
		],
	},
	...Object.entries(TABLE_GROUPS).map(([groupName, keys]) => ({
		label: `数据库 · ${groupName}`,
		items: keys.map((key) => ({ key, label: key })),
	})),
];

// ── Sidebar component ────────────────────────────────────────────────────────
function Sidebar({ activeKey, onSelect, doctorCount }) {
	return (
		<Box
			sx={{
				width: 200,
				minWidth: 200,
				height: "100vh",
				position: "fixed",
				top: 0,
				left: 0,
				background: GH.card,
				borderRight: `1px solid ${GH.border}`,
				display: "flex",
				flexDirection: "column",
				overflowY: "auto",
				zIndex: 10,
				"&::-webkit-scrollbar": { width: 6 },
				"&::-webkit-scrollbar-thumb": { background: GH.border, borderRadius: 3 },
			}}
		>
			{/* Logo / title */}
			<Box sx={{ px: 1.5, py: 1.5, borderBottom: `1px solid ${GH.border}` }}>
				<Typography
					sx={{ fontSize: 13, fontWeight: 700, color: "#fff", lineHeight: 1.3 }}
				>
					鲸鱼随行 Admin
				</Typography>
				{doctorCount != null && (
					<Typography sx={{ fontSize: 10, color: GH.textMuted, mt: 0.25 }}>
						{doctorCount} 位医生
					</Typography>
				)}
			</Box>

			{/* Nav sections */}
			<Box sx={{ flex: 1, py: 0.5 }}>
				{NAV_SECTIONS.map((section) => (
					<Box key={section.label} sx={{ mb: 0.5 }}>
						<Typography
							sx={{
								fontSize: 10.5,
								fontWeight: 600,
								color: GH.textMuted,
								textTransform: "uppercase",
								letterSpacing: "0.5px",
								px: 1.5,
								pt: 1,
								pb: 0.25,
								userSelect: "none",
							}}
						>
							{section.label}
						</Typography>
						{section.items.map((item) => {
							const isActive = activeKey === item.key;
							return (
								<Box
									key={item.key}
									onClick={() => onSelect(item.key)}
									sx={{
										px: 1.5,
										py: 0.5,
										fontSize: 12,
										color: isActive ? "#fff" : GH.text,
										background: isActive ? GH.hoverBg : "transparent",
										borderLeft: isActive
											? `2px solid ${GH.orange}`
											: "2px solid transparent",
										cursor: "pointer",
										userSelect: "none",
										fontFamily:
											ALL_TABLE_KEYS.includes(item.key)
												? "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
												: "inherit",
										"&:hover": {
											background: GH.hoverBg,
											color: "#fff",
										},
									}}
								>
									{item.label}
								</Box>
							);
						})}
					</Box>
				))}
			</Box>

			{/* Bottom link */}
			<Box
				sx={{
					px: 1.5,
					py: 1.25,
					borderTop: `1px solid ${GH.border}`,
				}}
			>
				<a
					href="/debug"
					style={{
						color: GH.blue,
						textDecoration: "none",
						fontSize: 11,
					}}
				>
					&larr; Debug Dashboard
				</a>
			</Box>
		</Box>
	);
}

// ── Cleanup Panel ────────────────────────────────────────────────────────────
function AdminCleanup() {
	const [preview, setPreview] = useState(null);
	const [loading, setLoading] = useState(false);
	const [executing, setExecuting] = useState(false);
	const [result, setResult] = useState(null);
	const [error, setError] = useState("");

	const token = localStorage.getItem(ADMIN_TOKEN_KEY) || (DEV_MODE ? "dev" : "");
	const headers = { "X-Admin-Token": token };

	async function loadPreview() {
		setLoading(true);
		setError("");
		setResult(null);
		try {
			const res = await fetch("/api/admin/cleanup/preview", { headers });
			if (!res.ok) throw new Error(`${res.status}`);
			setPreview(await res.json());
		} catch (e) {
			setError(e.message);
		} finally {
			setLoading(false);
		}
	}

	async function executeCleanup(action) {
		if (!confirm(`确认执行清理: ${action}？此操作不可撤销。`)) return;
		setExecuting(true);
		setError("");
		try {
			const res = await fetch(`/api/admin/cleanup/execute?action=${action}`, {
				method: "POST",
				headers,
			});
			if (!res.ok) throw new Error(`${res.status}`);
			setResult(await res.json());
			loadPreview(); // refresh
		} catch (e) {
			setError(e.message);
		} finally {
			setExecuting(false);
		}
	}

	useEffect(() => { loadPreview(); }, []); // eslint-disable-line

	const S = {
		section: { background: GH.card, border: `1px solid ${GH.border}`, borderRadius: 8, marginBottom: 12, overflow: "hidden" },
		header: { padding: "8px 14px", fontSize: 12, fontWeight: 600, color: GH.text, borderBottom: `1px solid ${GH.border}`, background: GH.hoverBg, display: "flex", justifyContent: "space-between", alignItems: "center" },
		row: { padding: "6px 14px", fontSize: 11, color: GH.text, borderBottom: `1px solid ${GH.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" },
		badge: (color) => ({ fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 3, background: `${color}22`, color }),
		btn: { fontSize: 11, fontWeight: 600, padding: "4px 12px", borderRadius: 4, border: "none", cursor: "pointer" },
		btnDanger: { background: "rgba(248,81,73,0.15)", color: GH.red },
		btnPrimary: { background: "rgba(63,185,80,0.15)", color: GH.green },
	};

	return (
		<div style={{ padding: "10px 16px" }}>
			{error && <div style={{ padding: "8px 12px", fontSize: 12, color: GH.red, background: "rgba(248,81,73,0.12)", borderRadius: 6, marginBottom: 12 }}>错误: {error}</div>}
			{result && (
				<div style={{ padding: "8px 12px", fontSize: 12, color: GH.green, background: "rgba(63,185,80,0.12)", borderRadius: 6, marginBottom: 12 }}>
					清理完成: {Object.entries(result.deleted || {}).filter(([, v]) => v > 0).map(([k, v]) => `${k}: ${v}`).join(", ") || "无数据删除"}
				</div>
			)}
			{loading && <div style={{ fontSize: 12, color: GH.textMuted, padding: "10px 0" }}>扫描中...</div>}
			{preview && (
				<>
					{/* Summary */}
					<div style={{ ...S.section }}>
						<div style={S.header}>
							<span>扫描摘要</span>
							<button style={{ ...S.btn, ...S.btnPrimary }} onClick={loadPreview} disabled={loading}>重新扫描</button>
						</div>
						<div style={S.row}>
							<span>待清理总行数</span>
							<span style={{ fontSize: 18, fontWeight: 700, color: preview.summary.total_rows_to_delete > 0 ? GH.orange : GH.green }}>
								{preview.summary.total_rows_to_delete}
							</span>
						</div>
					</div>

					{/* Test doctors */}
					<div style={S.section}>
						<div style={S.header}>
							<span>测试医生 <span style={S.badge(GH.red)}>{preview.test_doctors.length}</span></span>
							{preview.test_doctors.length > 0 && (
								<button style={{ ...S.btn, ...S.btnDanger }} onClick={() => executeCleanup("test_doctors")} disabled={executing}>
									{executing ? "清理中..." : "清理测试数据"}
								</button>
							)}
						</div>
						{preview.test_doctors.map((d, i) => (
							<div key={i} style={S.row}>
								<span><span style={{ color: GH.blue }}>{d.doctor_id}</span> · {d.name}</span>
								<span style={{ color: GH.textMuted }}>{d.patient_count}患者 · {d.record_count}病历 · {d.reason}</span>
							</div>
						))}
						{preview.test_doctors.length === 0 && <div style={{ ...S.row, color: GH.textMuted }}>无测试医生</div>}
					</div>

					{/* Stale patients */}
					<div style={S.section}>
						<div style={S.header}>
							<span>过期患者 <span style={S.badge(GH.orange)}>{preview.stale_patients.length}</span></span>
							{preview.stale_patients.length > 0 && (
								<button style={{ ...S.btn, ...S.btnDanger }} onClick={() => executeCleanup("stale_patients")} disabled={executing}>清理</button>
							)}
						</div>
						{preview.stale_patients.map((p, i) => (
							<div key={i} style={S.row}>
								<span>#{p.id} · {p.name} · <span style={{ color: GH.textMuted }}>{p.doctor_id}</span></span>
								<span style={{ color: GH.textMuted }}>{p.created_at} · {p.reason}</span>
							</div>
						))}
						{preview.stale_patients.length === 0 && <div style={{ ...S.row, color: GH.textMuted }}>无过期患者</div>}
					</div>

					{/* Orphaned records */}
					<div style={S.section}>
						<div style={S.header}>
							<span>孤立记录 <span style={S.badge(GH.textMuted)}>{preview.orphaned_records.length}</span></span>
							{preview.orphaned_records.length > 0 && (
								<button style={{ ...S.btn, ...S.btnDanger }} onClick={() => executeCleanup("orphaned_records")} disabled={executing}>清理</button>
							)}
						</div>
						{preview.orphaned_records.length === 0 && <div style={{ ...S.row, color: GH.textMuted }}>无孤立记录</div>}
					</div>

					{/* Duplicate doctors */}
					<div style={S.section}>
						<div style={S.header}>
							<span>重复医生 <span style={S.badge(GH.blue)}>{preview.duplicate_doctors.length}</span></span>
							<span style={{ fontSize: 10, color: GH.textMuted }}>需人工审查</span>
						</div>
						{preview.duplicate_doctors.map((g, i) => (
							<div key={i} style={{ ...S.row, flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
								<span><strong>{g.name || "(空名称)"}</strong> × {g.count}</span>
								<div style={{ fontSize: 10, color: GH.textMuted, fontFamily: "ui-monospace, monospace", wordBreak: "break-all" }}>
									{g.doctor_ids.join(", ")}
								</div>
							</div>
						))}
						{preview.duplicate_doctors.length === 0 && <div style={{ ...S.row, color: GH.textMuted }}>无重复医生</div>}
					</div>

					{/* Clean all */}
					{preview.summary.total_rows_to_delete > 0 && (
						<button style={{ ...S.btn, ...S.btnDanger, padding: "8px 20px", fontSize: 13 }}
							onClick={() => executeCleanup("all")} disabled={executing}>
							{executing ? "清理中..." : `一键清理全部 (${preview.summary.total_rows_to_delete} 行)`}
						</button>
					)}
				</>
			)}
		</div>
	);
}

// ── Main dashboard (after auth) ───────────────────────────────────────────────
function AdminDashboard({ onLockout }) {
	const { section } = useParams();
	const navigate = useNavigate();

	// Derive active key from URL section
	function deriveKey() {
		if (!section || section === "overview") return "overview";
		if (section === "doctors") return "doctors";
		if (section === "cleanup") return "cleanup";
		if (ALL_TABLE_KEYS.includes(section)) return section;
		return "overview";
	}

	const [activeKey, setActiveKey] = useState(deriveKey);
	const [selectedDoctor, setSelectedDoctor] = useState(null);
	const [doctorCount, setDoctorCount] = useState(null);

	// Sync URL section → activeKey when URL changes externally
	useEffect(() => {
		setActiveKey(deriveKey());
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [section]);

	// Fetch doctor count for sidebar badge (best effort)
	useEffect(() => {
		fetch("/api/admin/doctors", {
			headers: DEV_MODE
				? { "X-Admin-Token": "dev" }
				: { "X-Admin-Token": localStorage.getItem(ADMIN_TOKEN_KEY) || "" },
		})
			.then((r) => (r.ok ? r.json() : null))
			.then((data) => {
				if (data) {
					const list = data.doctors || data.items || [];
					setDoctorCount(list.length);
				}
			})
			.catch(() => {});
	}, []);

	function handleSelect(key) {
		setActiveKey(key);
		if (key !== "doctors") setSelectedDoctor(null);
		// Update URL
		if (key === "overview") navigate("/admin/overview");
		else navigate(`/admin/${key}`);
	}

	function handleDoctorClick(doctorId) {
		setSelectedDoctor(doctorId);
		setActiveKey("doctors");
		navigate("/admin/doctors");
	}

	// Determine what content to show
	const isTableKey = ALL_TABLE_KEYS.includes(activeKey);

	return (
		<Box sx={{ minHeight: "100vh", background: GH.bg, color: GH.text }}>
			<Sidebar
				activeKey={activeKey}
				onSelect={handleSelect}
				doctorCount={doctorCount}
			/>

			{/* Main content area */}
			<Box sx={{ ml: "200px", minHeight: "100vh" }}>
				{/* Top bar */}
				<Box
					sx={{
						px: 2,
						py: 0.75,
						borderBottom: `1px solid ${GH.border}`,
						display: "flex",
						justifyContent: "space-between",
						alignItems: "center",
						background: GH.card,
					}}
				>
					<Typography sx={{ fontSize: 12, color: GH.text, fontWeight: 600 }}>
						{activeKey === "overview" && "总览"}
						{activeKey === "doctors" && "医生"}
						{isTableKey && activeKey}
					</Typography>
					<a
						href="/debug"
						style={{
							color: GH.blue,
							textDecoration: "none",
							fontSize: 11,
						}}
					>
						Debug Dashboard &rarr;
					</a>
				</Box>

				{/* Page content */}
				{activeKey === "overview" && (
					<AdminOverview onDoctorClick={handleDoctorClick} />
				)}
				{activeKey === "doctors" && selectedDoctor && (
					<AdminDoctorDetail
						doctorId={selectedDoctor}
						onBack={() => {
							setSelectedDoctor(null);
						}}
					/>
				)}
				{activeKey === "doctors" && !selectedDoctor && (
					<DoctorList onDoctorClick={(id) => setSelectedDoctor(id)} />
				)}
				{activeKey === "cleanup" && <AdminCleanup />}
				{isTableKey && <AdminRawData forcedTable={activeKey} />}
			</Box>
		</Box>
	);
}

// ── Token gate + auth wrapper ─────────────────────────────────────────────────
export default function AdminPage() {
	// v3 is the default admin surface as of 2026-04-24. The legacy GitHub Dark
	// dashboard (this file's body below) remains available at /admin?v=1 for
	// one release as a fallback. Remove after no regressions are reported.
	if (
		typeof window !== "undefined" &&
		new URLSearchParams(window.location.search).get("v") !== "1"
	) {
		return <AdminPageV3 />;
	}

	const location = useLocation();
	const [status, setStatus] = useState(() => {
		if (DEV_MODE) return "ok";
		return localStorage.getItem(ADMIN_TOKEN_KEY) ? "verifying" : "locked";
	});

	function handleLockout() {
		if (DEV_MODE) return;
		localStorage.removeItem(ADMIN_TOKEN_KEY);
		setAdminToken("");
		setStatus("locked");
	}

	useEffect(() => { setPageTitle("admin", ""); }, []);

	useEffect(() => {
		if (DEV_MODE) return;
		onAdminAuthError(handleLockout);
		const stored = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
		if (stored) {
			setAdminToken(stored);
			getAdminRoutingMetrics()
				.then(() => setStatus("ok"))
				.catch(() => {
					localStorage.removeItem(ADMIN_TOKEN_KEY);
					setAdminToken("");
					setStatus("locked");
				});
		}
		return () => onAdminAuthError(null);
	}, [handleLockout]);

	let content;
	if (DEV_MODE) {
		content = <AdminDashboard onLockout={() => {}} />;
	} else if (status === "verifying") {
		content = null;
	} else if (status === "locked") {
		content = (
			<Navigate
				to="/admin/login"
				replace
				state={{ next: location.pathname, error: "Token 不正确，请重新输入" }}
			/>
		);
	} else {
		content = <AdminDashboard onLockout={handleLockout} />;
	}

	return <ThemeProvider theme={adminTheme}>{content}</ThemeProvider>;
}
