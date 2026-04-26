/**
 * Shared back-arrow + home-icon cluster for any push subpage's NavBar.
 *
 * Usage:
 *   <NavBar
 *     backArrow={<SubpageBackHome />}
 *     onBack={() => navigate(-1)}
 *   >
 *     {title}
 *   </NavBar>
 *
 * The home icon stops propagation so tapping it does not also fire `onBack`.
 * Both interactions go through markIntentionalBack() so the slide-out
 * animation plays via useNavDirection.
 */
import { useNavigate } from "react-router-dom";
import { LeftOutline } from "antd-mobile-icons";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import { markIntentionalBack } from "../../hooks/useNavDirection";
import { APP, ICON } from "../theme";
import { dp } from "../../utils/doctorBasePath";

export default function SubpageBackHome() {
  const navigate = useNavigate();

  function handleHomeClick(e) {
    e.stopPropagation();
    markIntentionalBack();
    navigate(dp("my-ai"));
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span aria-label="返回" style={{ display: "inline-flex" }}>
        <LeftOutline />
      </span>
      <HomeOutlinedIcon
        aria-label="回到首页"
        role="button"
        tabIndex={0}
        onClick={handleHomeClick}
        sx={{ fontSize: ICON.sm, color: APP.text2, cursor: "pointer" }}
      />
    </span>
  );
}
