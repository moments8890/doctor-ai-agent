// useDoctorDetail — fetches profile + related data for one doctor.
// Returns { doctor, related, loading, error }.
//
// Endpoints (existing, do not duplicate):
//   GET /api/admin/doctors/{id}        → { profile, setup, stats_7d }
//   GET /api/admin/doctors/{id}/related → { patients, messages, suggestions, ... }
//
// Auth: X-Admin-Token from localStorage("adminToken"); falls back to "dev"
// in import.meta.env.DEV so local development works without setup.

import { useEffect, useState } from "react";
import { getAdminDoctorRelated } from "../../../../api";

const ADMIN_TOKEN_KEY = "adminToken";

async function fetchJson(url) {
  const token =
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export default function useDoctorDetail(doctorId) {
  const [state, setState] = useState({
    doctor: null,
    related: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!doctorId) {
      setState({ doctor: null, related: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.all([
      fetchJson(`/api/admin/doctors/${encodeURIComponent(doctorId)}`),
      getAdminDoctorRelated(doctorId),
    ])
      .then(([doc, rel]) => {
        if (cancelled) return;
        setState({
          doctor: {
            ...doc.profile,
            setup: doc.setup,
            stats_7d: doc.stats_7d,
          },
          related: rel,
          loading: false,
          error: null,
        });
      })
      .catch((e) => {
        if (cancelled) return;
        setState({
          doctor: null,
          related: null,
          loading: false,
          error: e.message || String(e),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [doctorId]);

  return state;
}
