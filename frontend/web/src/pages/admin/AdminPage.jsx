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

// ── Main dashboard (after auth) ───────────────────────────────────────────────
function AdminDashboard({ onLockout }) {
	const { section } = useParams();
	const navigate = useNavigate();

	// Derive active key from URL section
	function deriveKey() {
		if (!section || section === "overview") return "overview";
		if (section === "doctors") return "doctors";
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
				{isTableKey && <AdminRawData forcedTable={activeKey} />}
			</Box>
		</Box>
	);
}

// ── Token gate + auth wrapper ─────────────────────────────────────────────────
export default function AdminPage() {
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

	useEffect(() => { document.title = "[admin] 鲸鱼随行"; }, []);

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
