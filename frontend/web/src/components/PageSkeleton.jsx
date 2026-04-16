/**
 * PageSkeleton — mobile page layout for all sections.
 *
 * Layout: SubpageHeader (back|title|actions) | content | SlideOverlay for subpages
 *
 * Subpages slide in from the right on forward navigation (PUSH).
 * Back navigation (tap-back, swipe-back, browser back) is instant: iOS
 * Safari renders its own swipe-back visual during the gesture and
 * animating on top of that causes a visible double play.
 *
 * Direction comes from useNavDirection(), which diffs react-router's
 * history.state.idx across renders. On "forward" the entry animation
 * plays; on "none" (first render / back-nav / deep-link) no animation
 * runs and the overlay appears / disappears instantly.
 */
import { Box } from "@mui/material";
import { COLOR } from "../theme";
import SubpageHeader from "./SubpageHeader";
import SlideOverlay from "./SlideOverlay";

export default function PageSkeleton({
  title, headerRight, onBack, listPane,
  mobileView,
  subpageKey = "subpage",
}) {
  return (
    <Box sx={{ position: "relative", height: "100%", overflow: "hidden" }}>
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column", bgcolor: COLOR.surface }}>
        <SubpageHeader title={title} onBack={onBack} right={headerRight} />
        <Box sx={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {listPane}
        </Box>
      </Box>
      <SlideOverlay show={!!mobileView} stackKey={subpageKey}>
        {mobileView}
      </SlideOverlay>
    </Box>
  );
}
