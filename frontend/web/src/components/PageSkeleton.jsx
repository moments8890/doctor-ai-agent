/**
 * PageSkeleton — unified page layout for all sections.
 *
 * Desktop (3-column): DoctorPage sidebar | list pane (resizable) | detail pane (flex)
 * Mobile:             SubpageHeader (back|title|actions) | content | bottom nav
 */
import { useCallback, useRef, useState } from "react";
import { Box, Slide, Typography } from "@mui/material";
import { COLOR } from "../theme";
import SubpageHeader from "./SubpageHeader";

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

export default function PageSkeleton({ title, headerRight, onBack, listPane, detailPane, mobileView, isMobile }) {
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

  // Mobile: list stays mounted; subpage slides in from the right when active
  if (isMobile) {
    return (
      <Box sx={{ position: "relative", height: "100%", overflow: "hidden" }}>
        {/* List — hidden (but mounted) when subpage is showing */}
        <Box sx={{ height: "100%", display: mobileView ? "none" : "flex", flexDirection: "column", bgcolor: COLOR.surface }}>
          <SubpageHeader title={title} onBack={onBack} right={headerRight} />
          <Box sx={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {listPane}
          </Box>
        </Box>
        {/* Subpage — slides in from right (WeChat push convention) */}
        <Slide direction="left" in={!!mobileView} timeout={300} mountOnEnter unmountOnExit>
          <Box sx={{ position: "absolute", inset: 0, zIndex: 2, bgcolor: COLOR.surface }}>
            {mobileView}
          </Box>
        </Slide>
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
