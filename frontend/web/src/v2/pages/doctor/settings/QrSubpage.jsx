/**
 * @route /doctor/settings/qr
 *
 * QrSubpage — show this doctor's permanent patient-attach code + QR.
 *
 * Patients scan the QR (which deep-links to the patient registration page
 * with the code pre-filled) or type the 4-char code manually. The code is
 * permanent: there is no rotation endpoint by design (beta acceptance per
 * the security review).
 */
import { useEffect, useState } from "react";
import { NavBar, Button, Toast } from "antd-mobile";
import { QRCodeSVG } from "qrcode.react";
import { useNavigate } from "react-router-dom";
import { useDoctorStore } from "../../../../store/doctorStore";
import { getDoctorAttachCode } from "../../../../api";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";

export default function QrSubpage() {
  const navigate = useNavigate();
  const { doctorId, doctorName, token } = useDoctorStore();
  const [code, setCode] = useState("");
  const [qrUrl, setQrUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!doctorId) return;
    getDoctorAttachCode(token, doctorId)
      .then((data) => {
        setCode(data.code || "");
        setQrUrl(data.qr_url || "");
      })
      .catch((err) => setError(err.message || "加载失败"));
  }, [doctorId, token]);

  function copyCode() {
    if (!code) return;
    navigator.clipboard?.writeText(code);
    Toast.show({ content: "已复制", position: "bottom" });
  }

  return (
    <div style={pageContainer}>
      <NavBar onBack={() => navigate(-1)} style={navBarStyle}>
        我的患者邀请码
      </NavBar>

      <div
        style={{
          ...scrollable,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 32,
        }}
      >
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text3,
            marginBottom: 20,
            textAlign: "center",
            padding: "0 32px",
            lineHeight: 1.6,
          }}
        >
          患者扫描下方二维码，或手动输入这个 4 位邀请码就可以加入您的患者列表。
          这个码是永久有效的，建议保存或打印张贴。
        </div>

        {/* Big code display */}
        <div
          onClick={copyCode}
          style={{
            fontSize: 44,
            fontWeight: 600,
            letterSpacing: 8,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            color: APP.primary,
            padding: "16px 32px",
            background: APP.white,
            borderRadius: RADIUS.lg,
            border: `1px solid ${APP.borderLight}`,
            cursor: "pointer",
            userSelect: "all",
            marginBottom: 8,
          }}
        >
          {code || "····"}
        </div>
        <Button size="small" fill="none" color="primary" onClick={copyCode} disabled={!code}>
          复制邀请码
        </Button>

        {/* QR */}
        {qrUrl && (
          <div
            style={{
              marginTop: 24,
              display: "inline-block",
              padding: 20,
              background: APP.white,
              borderRadius: RADIUS.lg,
              border: `1px solid ${APP.borderLight}`,
            }}
          >
            <QRCodeSVG value={qrUrl} size={200} level="M" />
          </div>
        )}

        {doctorName && (
          <div style={{ marginTop: 16, fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
            {doctorName} 医生
          </div>
        )}
        <div style={{ marginTop: 4, fontSize: FONT.sm, color: APP.text4, textAlign: "center", padding: "0 32px" }}>
          扫码或输入邀请码即可加入您的患者列表
        </div>

        {error && (
          <div style={{ marginTop: 16, fontSize: FONT.sm, color: APP.danger || "#e74c3c" }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
