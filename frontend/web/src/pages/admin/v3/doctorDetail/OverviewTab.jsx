// OverviewTab — 总览 tab content for the doctor detail surface.
// Composes:
//   row-3-1 grid (2fr 1fr): AiAdoptionPanel + AlertList
//   full-width: TimelinePanel
//
// Reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html lines ~1380-1540.

import AiAdoptionPanel from "./AiAdoptionPanel";
import AlertList from "./AlertList";
import TimelinePanel from "./TimelinePanel";

export default function OverviewTab({ doctor, related }) {
  const doctorId = doctor?.doctor_id;
  return (
    <div style={{ paddingTop: 16 }}>
      <div
        data-v3="row-3-1"
        style={{
          display: "grid",
          gridTemplateColumns: "2fr 1fr",
          gap: 16,
          marginBottom: 14,
        }}
      >
        <AiAdoptionPanel doctor={doctor} />
        <AlertList related={related} />
      </div>
      <TimelinePanel doctorId={doctorId} doctorName={doctor?.name} />
    </div>
  );
}
