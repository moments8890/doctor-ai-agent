/**
 * @route /patient/tasks/:id
 * Task detail with complete/undo. Stub until Task 11.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientTaskDetailPage({ taskId }) {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        任务详情
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        任务 #{taskId} — 即将上线
      </div>
    </div>
  );
}
