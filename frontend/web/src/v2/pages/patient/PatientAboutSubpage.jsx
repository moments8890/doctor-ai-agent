/**
 * @route /patient/profile/about
 */
import { SafeArea, NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, TintedIconRow } from "../../components";
import { APP_VERSION, BUILD_HASH } from "../../version";

function SectionHeader({ title }) {
  return (
    <div style={{ padding: "16px 20px 8px", fontSize: FONT.sm, color: APP.text4, fontWeight: 500 }}>
      {title}
    </div>
  );
}

export default function PatientAboutSubpage() {
  const navigate = useNavigate();

  return (
    <div style={pageContainer}>
      <SafeArea position="top" />
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        关于
      </NavBar>
      <div style={scrollable}>
        <SectionHeader title="应用信息" />
        <Card>
          <div style={{ padding: "14px 16px" }}>
            <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>患者助手</div>
            <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 4 }}>
              版本 {APP_VERSION}{BUILD_HASH ? ` · ${BUILD_HASH}` : ""}
            </div>
          </div>
        </Card>

        <SectionHeader title="法律信息" />
        <Card>
          <TintedIconRow
            Icon={LockOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="隐私政策"
            onClick={() => navigate("/patient/profile/privacy")}
            isFirst
          />
          <TintedIconRow
            Icon={DescriptionOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="服务条款"
            onClick={() => window.open("https://example.com/terms", "_blank")}
          />
        </Card>
      </div>
    </div>
  );
}
