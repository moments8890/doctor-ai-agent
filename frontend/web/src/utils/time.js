/** Format current time as HH:MM (24-hour). */
export function nowTs() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/**
 * Format patient age from year_of_birth.
 * - missing / zero → null (caller filters)
 * - negative (future DOB or bad data) → "年龄未知"
 * - valid → "N岁"
 */
export function formatAge(yearOfBirth) {
  if (!yearOfBirth) return null;
  const age = new Date().getFullYear() - yearOfBirth;
  if (age < 0) return "年龄未知";
  return `${age}岁`;
}

/**
 * Unified relative timestamp for all list/feed views — calendar-day buckets.
 *
 * Doctors think in days ("did this happen today, yesterday, or earlier?"),
 * not in elapsed hours. Calendar boundaries win over elapsed time. So an
 * event at 23:00 last night viewed at 09:00 this morning reads as "昨天",
 * even though only 10 hours elapsed.
 *
 *   < 1 hour AND same calendar day → 刚刚
 *   same calendar day              → 今天
 *   prev calendar day              → 昨天
 *   2-6 calendar days              → N天前
 *   7-27 days                      → N周前
 *   ≥ 28 days                      → 更早
 *
 * Trade-off: same-day items don't distinguish "30 min ago" from "18 hours
 * ago" — both read as "今天" (or "刚刚" if < 1 hour). If you need that
 * precision later, append HH:MM ("今天 14:30").
 *
 * Future dates delegate to `relativeFuture` below.
 * For HH:MM-only precision (chat bubbles), use `nowTs()`.
 */
export function relativeDate(dateStr) {
  if (!dateStr) return "";
  // Append 'Z' if no timezone info — backend stores UTC without suffix,
  // and new Date("...T...") without 'Z' is parsed as local time by JS.
  const normalized = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const diffMs = now - d;

  // Future dates → separate helper.
  if (diffMs < 0) return relativeFuture(dateStr);

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());

  if (dt.getTime() === today.getTime()) {
    // Same calendar day. Sub-hour items get "刚刚" as a freshness cue;
    // anything else just reads "今天".
    return diffMs < 60 * 60 * 1000 ? "刚刚" : "今天";
  }
  if (dt.getTime() === yesterday.getTime()) return "昨天";
  const diffDays = Math.floor((today - dt) / 86400000);
  if (diffDays < 7) return `${diffDays}天前`;
  if (diffDays < 28) return `${Math.floor(diffDays / 7)}周前`;
  return "更早";
}

/**
 * Alias for relativeDate. Historically `relativeTime` had finer-grained
 * buckets (N分钟前 / N小时前) and `relativeDate` had day+ buckets; both now
 * collapse to the same scheme: 刚刚 / 今天 / 昨天 / N天前 / N周前 / 更早.
 *
 * Kept as a separate export so call sites that currently import
 * `relativeTime` don't need to be rewritten.
 */
export function relativeTime(dateStr) {
  return relativeDate(dateStr);
}

/**
 * Relative timestamp for future dates (deadlines, due dates).
 * 明天, N天后, N周后, N个月后
 */
export function relativeFuture(dateStr) {
  if (!dateStr) return "";
  const normalized = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (dt.getTime() === today.getTime()) return "今天";
  if (dt.getTime() === tomorrow.getTime()) return "明天";
  const diffDays = Math.floor((dt - today) / 86400000);
  if (diffDays < 0) {
    const overdue = Math.abs(diffDays);
    return overdue < 30 ? `已过期${overdue}天` : `已过期${Math.floor(overdue / 30)}个月`;
  }
  if (diffDays < 7) return `${diffDays}天后`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周后`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}个月后`;
  return `${Math.floor(diffDays / 365)}年后`;
}
