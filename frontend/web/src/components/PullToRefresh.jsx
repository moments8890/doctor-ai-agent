import { useCallback, useRef, useState } from "react";
import { Box, CircularProgress } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { COLOR } from "../theme";

const THRESHOLD = 60;     // px to pull before triggering refresh
const MAX_PULL = 100;     // max visual pull distance
const RESIST = 0.4;       // damping factor for overscroll feel

/**
 * Wrap a scrollable container to add WeChat-style pull-to-refresh.
 * Children must be the scrollable content — this component manages overflow.
 *
 *   <PullToRefresh sx={{ flex: 1 }} pb="80px">
 *     {content}
 *   </PullToRefresh>
 */
export default function PullToRefresh({ children, sx, pb, ...rest }) {
  const queryClient = useQueryClient();
  const scrollRef = useRef(null);
  const startY = useRef(0);
  const pulling = useRef(false);
  const [pullDist, setPullDist] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const onTouchStart = useCallback((e) => {
    if (refreshing) return;
    const el = scrollRef.current;
    if (!el || el.scrollTop > 0) return;
    startY.current = e.touches[0].clientY;
    pulling.current = true;
  }, [refreshing]);

  const onTouchMove = useCallback((e) => {
    if (!pulling.current || refreshing) return;
    const el = scrollRef.current;
    if (!el || el.scrollTop > 0) { pulling.current = false; setPullDist(0); return; }
    const dy = (e.touches[0].clientY - startY.current) * RESIST;
    if (dy <= 0) { setPullDist(0); return; }
    setPullDist(Math.min(dy, MAX_PULL));
  }, [refreshing]);

  const onTouchEnd = useCallback(async () => {
    if (!pulling.current) return;
    pulling.current = false;
    if (pullDist >= THRESHOLD) {
      setRefreshing(true);
      setPullDist(THRESHOLD);
      await queryClient.invalidateQueries();
      // Brief delay so spinner is visible
      await new Promise((r) => setTimeout(r, 300));
      setRefreshing(false);
    }
    setPullDist(0);
  }, [pullDist, queryClient]);

  const showIndicator = pullDist > 0 || refreshing;

  return (
    <Box
      ref={scrollRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      sx={{ overflow: "auto", WebkitOverflowScrolling: "touch", pb, ...sx }}
      {...rest}
    >
      {showIndicator && (
        <Box sx={{
          display: "flex", justifyContent: "center", alignItems: "center",
          height: refreshing ? THRESHOLD : pullDist,
          transition: refreshing ? "height 0.2s" : "none",
          overflow: "hidden", flexShrink: 0,
        }}>
          <CircularProgress
            size={22}
            thickness={3}
            sx={{ color: COLOR.text4 }}
            variant={refreshing ? "indeterminate" : "determinate"}
            value={Math.min((pullDist / THRESHOLD) * 100, 100)}
          />
        </Box>
      )}
      {children}
    </Box>
  );
}
