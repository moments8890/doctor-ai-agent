/**
 * usePullToRefresh — adds pull-to-refresh gesture to a scrollable container.
 *
 * Usage:
 *   const { bind, refreshing } = usePullToRefresh(onRefresh);
 *   <Box {...bind} sx={{ overflowY: "auto" }}>
 *     {refreshing && <Spinner />}
 *     ...
 *   </Box>
 */
import { useCallback, useRef, useState } from "react";

export default function usePullToRefresh(onRefresh, { threshold = 60 } = {}) {
  const pullRef = useRef(null);
  const startY = useRef(null);
  const [refreshing, setRefreshing] = useState(false);

  const handleTouchStart = useCallback((e) => {
    const el = pullRef.current;
    if (!el || el.scrollTop > 0 || refreshing) return;
    startY.current = e.touches[0].clientY;
  }, [refreshing]);

  const handleTouchEnd = useCallback((e) => {
    if (startY.current === null || refreshing) return;
    const dy = e.changedTouches[0].clientY - startY.current;
    startY.current = null;
    if (dy > threshold) {
      setRefreshing(true);
      Promise.resolve(onRefresh()).finally(() => setRefreshing(false));
    }
  }, [onRefresh, threshold, refreshing]);

  const bind = {
    ref: pullRef,
    onTouchStart: handleTouchStart,
    onTouchEnd: handleTouchEnd,
  };

  return { bind, refreshing };
}
