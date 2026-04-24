/**
 * useLastViewed — localStorage-backed rolling list of recently viewed items.
 *
 * Feeds the "最近使用" card on MyAIPage. Pages call `recordView(item)` on
 * mount after their data loads; the hook's subscribers re-render.
 *
 * Entry schema:
 *   Patient:   { type: "patient",   id, name, gender?, yearOfBirth?, lastVisitAt?, viewedAt, pinnedAt? }
 *   Knowledge: { type: "knowledge", id, title, category?, updatedAt?, viewedAt, pinnedAt? }
 *
 * Sort order: pinned entries (newest-pinned first), then unpinned by viewedAt desc.
 * MAX cap only applies to unpinned entries — pinned are never dropped.
 */
import { useSyncExternalStore, useCallback } from "react";

const KEY = "doctor_last_viewed_v1";
const MAX = 20;

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function write(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // storage full / private mode — silently drop, this is best-effort
  }
}

const listeners = new Set();
function emit() {
  listeners.forEach((l) => l());
}

function subscribe(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

// Apply sort + rolling cap. Pinned go first (newest pinnedAt first), then
// unpinned by viewedAt desc, capped at MAX unpinned entries.
function normalize(list) {
  const pinned = list
    .filter((e) => e.pinnedAt)
    .sort((a, b) => (b.pinnedAt || "").localeCompare(a.pinnedAt || ""));
  const unpinned = list
    .filter((e) => !e.pinnedAt)
    .sort((a, b) => (b.viewedAt || "").localeCompare(a.viewedAt || ""))
    .slice(0, MAX);
  return [...pinned, ...unpinned];
}

let snapshot = normalize(read());
function getSnapshot() {
  return snapshot;
}

function commit(list) {
  snapshot = normalize(list);
  write(snapshot);
  emit();
}

function findIndex(list, type, id) {
  return list.findIndex((e) => e.type === type && String(e.id) === String(id));
}

export function recordView(entry) {
  if (!entry || !entry.type || entry.id == null) return;
  const idx = findIndex(snapshot, entry.type, entry.id);
  const prev = idx >= 0 ? snapshot[idx] : null;
  const merged = {
    ...prev,
    ...entry,
    viewedAt: new Date().toISOString(),
    // Preserve pin state — recordView shouldn't unpin on every mount.
    pinnedAt: prev?.pinnedAt || null,
  };
  const rest = snapshot.filter((_, i) => i !== idx);
  commit([merged, ...rest]);
}

export function togglePin(type, id) {
  const idx = findIndex(snapshot, type, id);
  if (idx < 0) return;
  const entry = snapshot[idx];
  const next = [...snapshot];
  next[idx] = {
    ...entry,
    pinnedAt: entry.pinnedAt ? null : new Date().toISOString(),
  };
  commit(next);
}

export function removeView(type, id) {
  const idx = findIndex(snapshot, type, id);
  if (idx < 0) return;
  commit(snapshot.filter((_, i) => i !== idx));
}

export function clearLastViewed() {
  commit([]);
}

// Drop stale entries whose referenced server row no longer exists.
// Pass id arrays only for the types you have live data for; types with
// `undefined` ids are left untouched (partial-load safe).
export function reconcileLastViewed({ patientIds, knowledgeIds } = {}) {
  const pSet = patientIds ? new Set(patientIds.map(String)) : null;
  const kSet = knowledgeIds ? new Set(knowledgeIds.map(String)) : null;
  if (!pSet && !kSet) return;
  const next = snapshot.filter((e) => {
    if (e.type === "patient" && pSet) return pSet.has(String(e.id));
    if (e.type === "knowledge" && kSet) return kSet.has(String(e.id));
    return true;
  });
  if (next.length !== snapshot.length) commit(next);
}

export function useLastViewed(limit = MAX) {
  const items = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const record = useCallback(recordView, []);
  const pin = useCallback(togglePin, []);
  const remove = useCallback(removeView, []);
  return { items: items.slice(0, limit), record, pin, remove };
}
