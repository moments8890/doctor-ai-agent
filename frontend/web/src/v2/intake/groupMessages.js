/**
 * groupPastIntakes — collapse messages belonging to any non-active intake
 * session into a single placeholder. The patient's ChatTab gets cluttered
 * with stale Q&A turns after a session has been submitted, abandoned, or
 * expired. Only the CURRENT active session's messages render verbatim.
 *
 * Predicate: a message belongs to a "past" session iff
 *   msg.intake_session_id is set AND it differs from `currentSessionId`.
 *
 * Active session messages and non-intake messages (no session_id) pass
 * through. This way:
 *   - mid-intake conversation renders normally
 *   - prior submitted/canceled sessions collapse without needing the
 *     frontend to know each session's exact status (status surfaces
 *     opportunistically via sessionStatusMap for label decoration)
 *
 * Returned shape: a flat array of items, each either:
 *   { kind: "message", message }                                 pass-through
 *   { kind: "collapsed_intake", session_id, status, messages }   collapsed run
 *
 * Consecutive messages with the same past session_id collapse into one
 * card. A different / no session_id breaks the run; doctor replies
 * interleaved into a past intake produce two cards — intentional.
 */

export function groupPastIntakes(messages, sessionStatusMap, currentSessionId) {
  if (!Array.isArray(messages) || messages.length === 0) return [];
  const statusMap = sessionStatusMap || {};

  const out = [];
  let currentGroup = null;

  for (const msg of messages) {
    const sid = msg?.intake_session_id || null;
    const isPast = sid && sid !== currentSessionId;

    if (isPast) {
      if (currentGroup && currentGroup.session_id === sid) {
        currentGroup.messages.push(msg);
      } else {
        if (currentGroup) out.push(currentGroup);
        currentGroup = {
          kind: "collapsed_intake",
          session_id: sid,
          status: statusMap[sid] || null,
          messages: [msg],
        };
      }
    } else {
      if (currentGroup) {
        out.push(currentGroup);
        currentGroup = null;
      }
      out.push({ kind: "message", message: msg });
    }
  }

  if (currentGroup) out.push(currentGroup);
  return out;
}

// Backwards-compat alias — old name kept until call sites migrate.
export const groupConfirmedIntakes = groupPastIntakes;
