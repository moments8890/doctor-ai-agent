/**
 * @route /doctor/settings/qr
 *
 * QrSubpage — generate a patient pre-interview QR code.
 * Patients scan this to start a new pre-interview session with this doctor.
 */
import { useState, useMemo } from "react";
import { NavBar, Button } from "antd-mobile";
import { QRCodeSVG } from "qrcode.react";
import { useNavigate } from "react-router-dom";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";

export default function QrSubpage() {
  const navigate = useNavigate();
  const { doctorId, doctorName } = useDoctorStore();

  // Build a patient registration URL with doctor_id pre-filled.
  // When the patient scans this, they land on /login with doctor context
  // and can register + start a pre-interview immediately.
  const url = useMemo(() => {
    const base = window.location.origin;
    const params = new URLSearchParams({ doctor_id: doctorId });
    if (doctorName) params.set("doctor_name", doctorName);
    return `${base}/login?${params.toString()}`;
  }, [doctorId, doctorName]);

  return (
    <div style={pageContainer}>
      <NavBar onBack={() => navigate(-1)} style={navBarStyle}>
        预问诊码
      </NavBar>

      <div style={{ ...scrollable, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 40 }}>
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text3,
            marginBottom: 24,
            textAlign: "center",
            padding: "0 32px",
            lineHeight: 1.6,
          }}
        >
          患者扫码后可注册并开始AI预问诊，问诊结果将自动关联到您的账号。
        </div>

        <div
          style={{
            display: "inline-block",
            padding: 20,
            background: APP.white,
            borderRadius: RADIUS.lg,
            border: `1px solid ${APP.borderLight}`,
          }}
        >
          <QRCodeSVG value={url} size={200} level="M" />
        </div>

        {doctorName && (
          <div style={{ marginTop: 16, fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
            {doctorName} 医生
          </div>
        )}

        <div style={{ marginTop: 4, fontSize: FONT.sm, color: APP.text4 }}>
          扫码注册后即可开始预问诊
        </div>
      </div>
    </div>
  );
}
