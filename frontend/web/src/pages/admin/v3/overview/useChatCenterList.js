// useChatCenterList — fetches the admin v3 cross-doctor chat inbox.
//
// Endpoint:
//   GET /api/admin/messages/recent?limit=&offset=&filter=&doctor_id=&q=
//
// Returns { items, total, loading, error, refetch }. Mirrors usePatientList.js
// so the chat-center page shares auth + retry conventions with the patients
// page.

import { useCallback, useEffect, useState } from "react";

const ADMIN_TOKEN_KEY = "adminToken";

function getToken() {
  return (
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "")
  );
}

function buildUrl({ limit, offset, filter, doctorId, q }) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  if (filter) params.set("filter", filter);
  if (doctorId) params.set("doctor_id", doctorId);
  if (q && q.trim()) params.set("q", q.trim());
  return `/api/admin/messages/recent?${params.toString()}`;
}

export default function useChatCenterList({
  limit = 50,
  offset = 0,
  filter = "all",
  doctorId = null,
  q = "",
} = {}) {
  const [state, setState] = useState({
    items: [],
    total: 0,
    loading: true,
    error: null,
  });
  const [reloadTick, setReloadTick] = useState(0);

  const refetch = useCallback(() => setReloadTick((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    const url = buildUrl({ limit, offset, filter, doctorId, q });
    const token = getToken();

    fetch(url, {
      headers: token ? { "X-Admin-Token": token } : {},
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      })
      .then((body) => {
        if (cancelled) return;
        setState({
          items: Array.isArray(body.items) ? body.items : [],
          total: Number.isFinite(body.total) ? body.total : 0,
          loading: false,
          error: null,
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setState({
          items: [],
          total: 0,
          loading: false,
          error: e.message || String(e),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [limit, offset, filter, doctorId, q, reloadTick]);

  return { ...state, refetch };
}
