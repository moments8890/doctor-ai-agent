/**
 * PageSkeleton — unified page layout for all sections.
 *
 * Desktop (3-column): DoctorPage sidebar | list pane (resizable) | detail pane (flex)
 * Mobile:             SubpageHeader (back|title|actions) | content | bottom nav
 *
 * Mobile subpages slide in from the right on forward navigation (PUSH).
 * Back navigation (tap-back, swipe-back, browser back) is instant: iOS
 * Safari renders its own swipe-back visual during the gesture and
 * animating on top of that causes a visible double play. Tap-on-←-arrow
 * is also instant on iOS Safari by convention, so making all back nav
 * instant matches native behaviour without needing to distinguish
 * between tap-back and swipe-back.
 *
 * Direction comes from useNavDirection(), which diffs react-router's
 * history.state.idx across renders. On "forward" the entry animation
 * plays; on "none" (first render / back-nav / deep-link) no animation
 * runs and the overlay appears / disappears instantly.
 */
import { useCallback, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { COLOR } from "../theme";
import SubpageHeader from "./SubpageHeader";
import SlideOverlay from "./SlideOverlay";

function DragHandle({ onDrag }) {
  const dragging = useRef(false);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    const move = (ev) => { if (dragging.current) onDrag(ev.clientX); };
    const up = () => { dragging.current = false; window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }, [onDrag]);

  return (
    <Box
      onMouseDown={onMouseDown}
      sx={{
        width: 5, flexShrink: 0, cursor: "col-resize",
        bgcolor: "transparent", "&:hover": { bgcolor: COLOR.border },
        transition: "background-color 0.15s",
      }}
    />
  );
}

export default function PageSkeleton({
  title, headerRight, onBack, listPane, detailPane,
  mobileView, isMobile,
  subpageKey = "subpage",
}) {
  const containerRef = useRef(null);
  const [listWidth, setListWidth] = useState(() => {
    const saved = localStorage.getItem("pageskeleton_list_width");
    return saved ? Number(saved) : 300;
  });

  const handleDrag = useCallback((clientX) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const w = Math.max(200, Math.min(clientX - rect.left, 500));
    setListWidth(w);
    localStorage.setItem("pageskeleton_list_width", String(w));
  }, []);

  if (isMobile) {
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

  // Desktop: list (resizable) | drag handle | detail (flex)
  return (
    <Box ref={containerRef} sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      <Box sx={{ width: listWidth, flexShrink: 0, display: "flex", flexDirection: "column", bgcolor: COLOR.surface }}>
        {listPane}
      </Box>
      <DragHandle onDrag={handleDrag} />
      <Box sx={{ flex: 1, overflow: "hidden", display: "flex" }}>
        <Box sx={{ width: "100%", height: "100%", overflow: "hidden" }}>
          {detailPane || (
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
              <Typography color="text.disabled">请选择一项查看详情</Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
