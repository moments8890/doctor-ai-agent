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
 * Both icons share the same family (MUI outlined), size (ICON.sm), color
 * (APP.text2), and weight so the cluster reads as a single visual unit.
 * The home icon stops propagation so tapping it does not also fire `onBack`.
 * Both interactions go through markIntentionalBack() so the slide-out
 * animation plays via useNavDirection.
 */
import { useNavigate } from "react-router-dom";
import ChevronLeftOutlinedIcon from "@mui/icons-material/ChevronLeft";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import { markIntentionalBack } from "../../hooks/useNavDirection";
import { APP, ICON } from "../theme";
import { dp } from "../../utils/doctorBasePath";

const ICON_SX = { fontSize: ICON.md, color: APP.text1, cursor: "pointer" };

export default function SubpageBackHome() {
  const navigate = useNavigate();

  function handleHomeClick(e) {
    e.stopPropagation();
    markIntentionalBack();
    navigate(dp("my-ai"));
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 14 }}>
      <ChevronLeftOutlinedIcon aria-label="返回" sx={ICON_SX} />
      <HomeOutlinedIcon
        aria-label="回到首页"
        role="button"
        tabIndex={0}
        onClick={handleHomeClick}
        sx={ICON_SX}
      />
    </span>
  );
}
