// usePatientFilter — admin v3 患者 tab filter reducer.
//
// Filters: "all" | "danger" | "warn" | "silent" | "postop"
//   silent  = silentDays >= 7
//   postop  = isPostOp truthy
//
// applyFilter is exported separately so the reducer can be unit-tested
// without rendering React (see test/hooks/usePatientFilter.test.js).

import { useMemo, useState } from "react";

export function applyFilter(patients, filter) {
  switch (filter) {
    case "danger":
      return patients.filter((p) => p.risk === "danger");
    case "warn":
      return patients.filter((p) => p.risk === "warn");
    case "silent":
      return patients.filter((p) => (p.silentDays ?? 0) >= 7);
    case "postop":
      return patients.filter((p) => Boolean(p.isPostOp));
    case "all":
    default:
      return patients;
  }
}

export default function usePatientFilter(patients) {
  const [filter, setFilter] = useState("all");

  const counts = useMemo(
    () => ({
      all: patients.length,
      danger: patients.filter((p) => p.risk === "danger").length,
      warn: patients.filter((p) => p.risk === "warn").length,
      silent: patients.filter((p) => (p.silentDays ?? 0) >= 7).length,
      postop: patients.filter((p) => Boolean(p.isPostOp)).length,
    }),
    [patients]
  );

  const filtered = useMemo(() => applyFilter(patients, filter), [patients, filter]);

  return { filter, setFilter, filtered, counts };
}
