import Box from "@mui/material/Box";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { onAuthExpired, setWebToken } from "./api";
import { ApiProvider } from "./api/ApiContext";
import { MockApiProvider } from "./api/MockApiProvider";
import { PatientApiProvider } from "./api/PatientApiContext";
import { PatientMockApiProvider } from "./api/PatientMockApiProvider";
import AdminLoginPage from "./pages/admin/AdminLoginPage";
import AdminPage from "./pages/admin/AdminPage";
import ComponentShowcasePage from "./pages/admin/ComponentShowcasePage";
import DoctorPage from "./pages/doctor/DoctorPage";
import OnboardingWizard from "./pages/doctor/OnboardingWizard";
import LoginPage from "./pages/LoginPage";
import PrivacyPage from "./pages/PrivacyPage";
import PatientPage from "./pages/patient/PatientPage";
import { useDoctorStore } from "./store/doctorStore";
import { RADIUS } from "./theme";
import { MOBILE_FRAME_CONTAINER_ID } from "./utils/dialogContainer";
import { isMiniApp } from "./utils/env";

const DEV_MODE = import.meta.env.DEV; // true in `vite dev`, false in `vite build`

/**
 * On wide screens (>520px), constrains the app to a phone-shaped container
 * with 9:19.5 aspect ratio. Uses CSS min() to pick whichever dimension
 * is the binding constraint — width or height — so it always fits.
 * On actual mobile (<520px), renders full-screen.
 */
function MobileFrame({ children }) {
	// Aspect ratio: 9 / 19.5 ≈ 0.4615
	// Height from width: h = w / 0.4615 = w * 2.167
	// Width from height: w = h * 0.4615
	return (
		<Box
			sx={{
				width: "100vw",
				height: "100vh",
				display: "flex",
				justifyContent: "center",
				alignItems: "center",
				bgcolor: "transparent",
				"@media (min-width: 520px)": { bgcolor: "#e8e8e8" },
			}}
		>
			<Box
				sx={{
					width: "100%",
					height: "100%",
					overflow: "hidden",
					position: "relative",
					"@media (min-width: 520px)": {
						// Pick the smaller of: height-driven width vs width-driven width
						width: "min(calc(95vh * 9 / 19.5), 90vw)",
						// Pick the smaller of: width-driven height vs height-driven height
						height: "min(calc(90vw * 19.5 / 9), 95vh)",
						maxWidth: 480,
						borderRadius: RADIUS.pill,
						boxShadow: "0 4px 24px rgba(0,0,0,0.12)",
						// Creates a new containing block for position:fixed children
						// so they stay inside the frame instead of viewport
						transform: "translateZ(0)",
					},
				}}
				id={MOBILE_FRAME_CONTAINER_ID}
			>
				{children}
			</Box>
		</Box>
	);
}
const DEV_DOCTOR_ID = import.meta.env.VITE_DEV_DOCTOR_ID || "test_doctor";
const DEV_DOCTOR_NAME = import.meta.env.VITE_DEV_DOCTOR_NAME || "";

function applySyntheticDevSession(setAuth) {
	setAuth(DEV_DOCTOR_ID, DEV_DOCTOR_NAME, "dev-token");
}

function RequireAuth({ children }) {
	const { accessToken } = useDoctorStore();
	if (DEV_MODE) return children; // Skip auth gate in dev
	if (!accessToken) return <Navigate to="/login" replace />;
	return children;
}

const DOCTOR_PATH_SUFFIXES = [
	"",
	"/patients/:patientId",
	"/review/:recordId",
	"/:section",
	"/:section/:subpage",
	"/:section/:subpage/:subId",
];

function doctorRoutes(prefix, Provider) {
	return DOCTOR_PATH_SUFFIXES.map((suffix) => (
		<Route
			key={prefix + suffix}
			path={`${prefix}${suffix}`}
			element={
				<MobileFrame>
					<RequireAuth>
						<Provider>
							<DoctorPage />
						</Provider>
					</RequireAuth>
				</MobileFrame>
			}
		/>
	));
}

const PATIENT_PATH_SUFFIXES = ["", "/:tab", "/:tab/:subpage"];

function patientRoutes(prefix, Provider) {
	return PATIENT_PATH_SUFFIXES.map((suffix) => (
		<Route
			key={prefix + suffix}
			path={`${prefix}${suffix}`}
			element={
				<MobileFrame>
					<Provider>
						<PatientPage />
					</Provider>
				</MobileFrame>
			}
		/>
	));
}

export default function App() {
	const { accessToken, doctorId, setAuth } = useDoctorStore();

	// Dev mode: restore real login session if current session is synthetic (dev/mock)
	const SYNTHETIC_TOKENS = ["dev-token", "mock-token"];
	const SYNTHETIC_IDS = [DEV_DOCTOR_ID, "mock_doctor"];

	function restoreRealSession() {
		const state = useDoctorStore.getState();
		const isSynthetic =
			!state.doctorId ||
			!state.accessToken ||
			SYNTHETIC_TOKENS.includes(state.accessToken) ||
			SYNTHETIC_IDS.includes(state.doctorId);
		if (!isSynthetic) return; // real session, don't touch

		const savedId = localStorage.getItem("unified_auth_doctor_id");
		const savedToken = localStorage.getItem("unified_auth_token");
		const savedName = localStorage.getItem("unified_auth_name");
		const savedIsSynthetic =
			Boolean(savedId && savedToken) &&
			(SYNTHETIC_TOKENS.includes(savedToken) ||
				SYNTHETIC_IDS.includes(savedId));
		if (savedId && savedToken && !savedIsSynthetic) {
			state.setAuth(savedId, savedName || savedId, savedToken);
		} else {
			applySyntheticDevSession(state.setAuth);
		}
	}

	useEffect(() => {
		if (!DEV_MODE) return;
		const unsub = useDoctorStore.persist.onFinishHydration(restoreRealSession);
		if (useDoctorStore.persist.hasHydrated()) restoreRealSession();
		return unsub;
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	// Keep the old useState initializer as a sync fallback for first render
	useState(() => {
		if (DEV_MODE && !doctorId) {
			const savedId = localStorage.getItem("unified_auth_doctor_id");
			const savedToken = localStorage.getItem("unified_auth_token");
			const savedName = localStorage.getItem("unified_auth_name");
			const savedIsSynthetic =
				Boolean(savedId && savedToken) &&
				(SYNTHETIC_TOKENS.includes(savedToken) ||
					SYNTHETIC_IDS.includes(savedId));
			if (savedId && savedToken && !savedIsSynthetic) {
				setAuth(savedId, savedName || savedId, savedToken);
			} else {
				applySyntheticDevSession(setAuth);
			}
		}
	});

	// Absorb token handed off from WeChat Mini Program web-view via URL params.
	useState(() => {
		const params = new URLSearchParams(window.location.search);
		const token = params.get("token");
		const did = params.get("doctor_id");
		const name = params.get("name");
		if (token && did) {
			setAuth(did, name || did, token);
			setWebToken(token);
			const url = new URL(window.location.href);
			["token", "doctor_id", "name"].forEach((k) => url.searchParams.delete(k));
			window.history.replaceState({}, "", url.toString());
		}
	});

	// Restore token into api module on page reload
	useEffect(() => {
		if (accessToken) setWebToken(accessToken);
	}, [accessToken]);

	// Handle 401 token expiry — Mini App shows message, web redirects to login
	useEffect(() => {
		onAuthExpired(() => {
			if (isMiniApp()) {
				useDoctorStore.getState().clearAuth();
				alert("会话已过期，请关闭后重新打开小程序");
				// eslint-disable-next-line no-undef
				wx.miniProgram?.navigateBack?.();
			} else {
				useDoctorStore.getState().clearAuth();
				window.location.href = "/login";
			}
		});
	}, []);

	return (
		<Routes>
			{/* Mobile-framed routes (doctor, patient, login) */}
			<Route
				path="/privacy"
				element={
					<MobileFrame>
						<PrivacyPage />
					</MobileFrame>
				}
			/>
			<Route
				path="/login"
				element={
					<MobileFrame>
						<LoginPage />
					</MobileFrame>
				}
			/>
			<Route path="/" element={<Navigate to="/doctor" replace />} />
			{/* Onboarding wizard — outside DoctorPage shell (no bottom nav) */}
			<Route
				path="/doctor/onboarding"
				element={
					<MobileFrame>
						<RequireAuth>
							<ApiProvider>
								<OnboardingWizard />
							</ApiProvider>
						</RequireAuth>
					</MobileFrame>
				}
			/>
			{doctorRoutes("/doctor", ApiProvider)}
			{patientRoutes("/patient", PatientApiProvider)}
			{/* Admin — full desktop layout, no MobileFrame */}
			<Route path="/admin/login" element={<AdminLoginPage />} />
			<Route path="/admin" element={<AdminPage />} />
			<Route path="/admin/:section" element={<AdminPage />} />
			{/* Component showcases — specific routes BEFORE debug wildcard */}
			<Route
				path="/debug/components"
				element={
					<MobileFrame>
						<MockApiProvider>
							<ComponentShowcasePage />
						</MockApiProvider>
					</MobileFrame>
				}
			/>
			{/* Mock doctor app — same DoctorPage, mock API, auth required in prod */}
			{doctorRoutes("/debug/doctor", MockApiProvider)}
			{/* Mock patient app — same PatientPage, mock API */}
			{patientRoutes("/debug/patient", PatientMockApiProvider)}
			<Route
				path="/debug/doctor-pages"
				element={<Navigate to="/debug/doctor" replace />}
			/>
			<Route path="*" element={<Navigate to="/" replace />} />
		</Routes>
	);
}
