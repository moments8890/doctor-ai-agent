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
 * Unified relative timestamp for all list views.
 * Past: 今天, 昨天, N天前, N周前, N个月前, N年前
 */
export function relativeDate(dateStr) {
  if (!dateStr) return "";
  // Append 'Z' if no timezone info — backend stores UTC without suffix,
  // and new Date("...T...") without 'Z' is parsed as local time by JS.
  const normalized = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (dt.getTime() === today.getTime()) return "今天";
  if (dt.getTime() === yesterday.getTime()) return "昨天";
  const diffDays = Math.floor((today - dt) / 86400000);
  if (diffDays < 0) return relativeFuture(dateStr);
  if (diffDays < 7) return `${diffDays}天前`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}个月前`;
  return `${Math.floor(diffDays / 365)}年前`;
}

/**
 * Fine-grained relative time (includes minutes/hours).
 * 刚刚, N分钟前, N小时前, 今天, 昨天, N天前, N周前, N个月前, N年前
 */
export function relativeTime(dateStr) {
  if (!dateStr) return "";
  const normalized = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const diffMs = now - d;
  if (diffMs < 0) return "刚刚";
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}小时前`;
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
