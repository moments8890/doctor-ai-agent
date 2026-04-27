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
  // Backend returns record_id as an integer; URL gives currentId as a string.
  // Stringify both sides so the current record gets filtered out.
  const current = currentId == null ? "" : String(currentId);
  const pending = reviewQueue?.pending || [];
  const others = pending.filter((item) => String(item.record_id) !== current);
  const next = others[0];
  if (next) {
    return { kind: "next", nextId: next.record_id, remaining: others.length };
  }
  return { kind: "done" };
}
