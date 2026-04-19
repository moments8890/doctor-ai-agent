/**
 * @route /patient/profile/privacy
 * Privacy policy — subpage frame. Stub until Task 12.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientPrivacySubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        隐私政策
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        即将上线
      </div>
    </div>
  );
}
