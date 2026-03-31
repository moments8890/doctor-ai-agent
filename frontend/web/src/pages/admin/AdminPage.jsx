/** @route /admin, /admin/:section
 *  3-tab admin shell: 总览 | 医生 | 原始数据
 */

import { Box } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import { useEffect, useState } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import {
	getAdminRoutingMetrics,
	onAdminAuthError,
	setAdminToken,
} from "../../api";
import { adminTheme } from "../../theme";
import AdminDoctorDetail, { DoctorList } from "./AdminDoctorDetail";
import AdminOverview from "./AdminOverview";
import AdminRawData from "./AdminRawData";

const ADMIN_TOKEN_KEY = "adminToken";
const DEV_MODE = import.meta.env.DEV;

// In dev mode, set token synchronously before any component renders
if (DEV_MODE) setAdminToken("dev");

// ── Tab bar ────────────────────────────────────────────────────────────────────
const TABS = [
	{ key: "overview", label: "总览" },
	{ key: "doctors", label: "医生" },
	{ key: "raw", label: "原始数据" },
];

function TopBar({ doctorCount }) {
	return (
		<Box
			sx={{
				background: "#1a1a2e",
				color: "#ccc",
				px: 2,
				py: 0.75,
				display: "flex",
				justifyContent: "space-between",
				alignItems: "center",
				fontSize: 11,
			}}
		>
			<span>
				<strong style={{ color: "#fff", fontSize: 12 }}>Doctor AI Admin</strong>{" "}
				· beta
				{doctorCount != null && (
					<span style={{ marginLeft: 6, color: "#888" }}>
						· {doctorCount} 医生
					</span>
				)}
			</span>
			<a
				href="/debug"
				style={{ color: "#64b5f6", textDecoration: "none", fontSize: 11 }}
			>
				Debug Dashboard →
			</a>
		</Box>
	);
}

function TabBar({ active, onSelect, doctorCount }) {
	return (
		<Box
			sx={{
				background: "#fff",
				borderBottom: "1px solid #ddd",
				px: 2,
				display: "flex",
				gap: 0,
			}}
		>
			{TABS.map((tab) => {
				const isActive = active === tab.key;
				return (
					<Box
						key={tab.key}
						onClick={() => onSelect(tab.key)}
						sx={{
							px: 1.75,
							py: 1,
							fontSize: 12,
							fontWeight: isActive ? 600 : 500,
							color: isActive ? "#1565c0" : "#666",
							borderBottom: isActive
								? "2px solid #1565c0"
								: "2px solid transparent",
							cursor: "pointer",
							userSelect: "none",
							"&:hover": { color: "#1565c0" },
						}}
					>
						{tab.label}
						{tab.key === "doctors" && doctorCount != null && (
							<span style={{ fontSize: 10, color: "#999", marginLeft: 3 }}>
								{doctorCount}
							</span>
						)}
					</Box>
				);
			})}
		</Box>
	);
}

// ── Main dashboard (after auth) ───────────────────────────────────────────────
function AdminDashboard({ onLockout }) {
	const { section } = useParams();

	// Derive initial tab from URL section
	function initialTab() {
		if (!section || section === "overview") return "overview";
		if (section === "doctors") return "doctors";
		// Raw data tables
		return "raw";
	}

	const [activeTab, setActiveTab] = useState(initialTab);
	const [selectedDoctor, setSelectedDoctor] = useState(null);
	const [doctorCount, setDoctorCount] = useState(null);

	// Fetch doctor count for tab badge (best effort)
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

	function handleDoctorClick(doctorId) {
		setSelectedDoctor(doctorId);
		setActiveTab("doctors");
	}

	return (
		<Box sx={{ minHeight: "100vh", background: "#f8f8f8" }}>
			<TopBar doctorCount={doctorCount} />
			<TabBar
				active={activeTab}
				onSelect={(tab) => {
					setActiveTab(tab);
					if (tab !== "doctors") setSelectedDoctor(null);
				}}
				doctorCount={doctorCount}
			/>

			{activeTab === "overview" && (
				<AdminOverview onDoctorClick={handleDoctorClick} />
			)}
			{activeTab === "doctors" && selectedDoctor && (
				<AdminDoctorDetail
					doctorId={selectedDoctor}
					onBack={() => {
						setSelectedDoctor(null);
						setActiveTab("overview");
					}}
				/>
			)}
			{activeTab === "doctors" && !selectedDoctor && (
				<DoctorList onDoctorClick={(id) => setSelectedDoctor(id)} />
			)}
			{activeTab === "raw" && <AdminRawData />}
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
