/**
 * Decide where ReviewPage should navigate after a successful finalize.
 *
 * Returns:
 *   { kind: "next", nextId, remaining } — go to the next pending record
 *   { kind: "done" }                    — queue empty after this one, send to home
 *
 * Pure / no React deps so it's trivially unit-testable.
 */
export function computeNextNav(reviewQueue, currentId) {
  const pending = reviewQueue?.pending || [];
  const others = pending.filter((item) => item.record_id !== currentId);
  const next = others[0];
  if (next) {
    return { kind: "next", nextId: next.record_id, remaining: others.length };
  }
  return { kind: "done" };
}
