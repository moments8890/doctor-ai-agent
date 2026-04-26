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
 * Unified relative timestamp for all list/feed views.
 *
 * Hybrid scheme: elapsed-time wins for the first 24h (so "23:00 last night"
 * viewed at "09:00 today" reads as "10 小时前", not "昨天" — fixes the
 * calendar-edge ambiguity). Calendar buckets take over after 24h.
 *
 * Past:
 *   < 60 min           → 刚刚
 *   1-23 hours         → N小时前
 *   ≥ 24h, prev day    → 昨天
 *   2-6 calendar days  → N天前
 *   7-27 days          → N周前
 *   ≥ 28 days          → 更早
 *
 * Future dates delegate to `relativeFuture` below.
 * For HH:MM precision (chat bubbles, etc.) use `nowTs()` instead.
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

  // First 24h: use elapsed time, NOT calendar day. Avoids the 23:00 → 09:00
  // edge case where calendar comparison would misleadingly say "昨天".
  // Sub-hour granularity collapses to "刚刚" — minute precision is noise
  // for a doctor scanning a list (8分钟前 vs 23分钟前 doesn't change action).
  const diffHours = Math.floor(diffMs / (60 * 60 * 1000));
  if (diffHours < 1) return "刚刚";
  if (diffHours < 24) return `${diffHours}小时前`;

  // ≥ 24h: switch to calendar buckets — at this scale the day matters more
  // than the hour, and elapsed-hours becomes hard to scan ("47 小时前").
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
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
