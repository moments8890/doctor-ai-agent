/**
 * @route /patient/profile/privacy
 */
import { SafeArea, NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import PrivacyContent from "../PrivacyContent";

export default function PatientPrivacySubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <SafeArea position="top" />
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        隐私政策
      </NavBar>
      <div style={scrollable}>
        <PrivacyContent />
      </div>
    </div>
  );
}
