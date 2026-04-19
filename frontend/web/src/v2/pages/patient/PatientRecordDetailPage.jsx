/**
 * @route /patient/records/:id
 * Read-only patient record detail. Stub until Task 10.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientRecordDetailPage({ recordId }) {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        病历详情
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        病历 #{recordId} — 即将上线
      </div>
    </div>
  );
}
