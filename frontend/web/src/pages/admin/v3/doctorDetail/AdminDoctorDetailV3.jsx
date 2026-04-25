// AdminDoctorDetailV3 — top-level component for the doctor detail surface.
// Renders header + KPI strip + 4 tabs and dispatches each tab's content.

import { useState } from "react";
import useDoctorDetail from "../hooks/useDoctorDetail";
import DoctorHeader from "./DoctorHeader";
import KpiStrip from "./KpiStrip";
import Tabs from "./Tabs";
import OverviewTab from "./OverviewTab";
import PatientsTab from "./PatientsTab";
import ChatTab from "./ChatTab";
import AiTab from "./AiTab";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";

export default function AdminDoctorDetailV3({ doctorId }) {
  const { doctor, loading, error, related } = useDoctorDetail(doctorId);
  const [tab, setTab] = useState("overview");

  if (loading) return <SectionLoading />;
  if (error) return <SectionError message={error} />;
  if (!doctor) {
    return (
      <EmptyState
        icon="person_off"
        title="未找到该医生"
        desc="该 doctor_id 不存在或已被清理"
      />
    );
  }

  return (
    <>
      <DoctorHeader doctor={doctor} />
      <KpiStrip stats={doctor.stats_7d} />
      <Tabs value={tab} onChange={setTab} related={related} />
      {tab === "overview" && <OverviewTab doctor={doctor} related={related} />}
      {tab === "patients" && <PatientsTab patients={related?.patients?.items || []} />}
      {tab === "chat"     && <ChatTab related={related} />}
      {tab === "ai"       && <AiTab related={related} />}
    </>
  );
}
