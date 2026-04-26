import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/doctorQueries", () => ({
  usePatients: () => ({ data: [], isLoading: false }),
  useReviewQueue: () => ({ data: [], isLoading: false }),
  usePersona: () => ({ data: {} }),
  useTodaySummary: () => ({ data: null, isLoading: false }),
  useKbPending: () => ({ data: [] }),
  useKnowledgeItems: () => ({ data: [] }),
  useAIAttention: () => ({ data: { patients: [] } }),
  useUnseenPatientCount: () => ({ data: 0 }),
}));
vi.mock("../../store/doctorStore", () => ({
  useDoctorStore: () => ({ doctorId: "doc1" }),
}));
vi.mock("../../api/ApiContext", () => ({
  useApi: () => ({
    fetchPatients: () => Promise.resolve([]),
    searchPatientsNL: () => Promise.resolve([]),
  }),
  ApiProvider: ({ children }) => children,
}));

import DoctorPage from "../pages/doctor/DoctorPage";

function Host({ initialPath = "/doctor/my-ai" }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <DoctorPage doctorId="doc1" />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Single-tab IA — TabBar absence", () => {
  test("DoctorPage renders no .adm-tab-bar element", () => {
    const { container } = render(<Host />);
    expect(container.querySelector(".adm-tab-bar")).toBeNull();
  });

  test("DoctorPage renders no element with role=tablist", () => {
    render(<Host />);
    expect(screen.queryByRole("tablist")).toBeNull();
  });
});

describe("Single-tab IA — base section is always my-ai", () => {
  test("at /doctor/patients, MyAIPage renders as base (hero banner present)", () => {
    render(<Host initialPath="/doctor/patients" />);
    // HeroBanner title is the stable MyAIPage marker
    expect(screen.queryByText(/您的专属医疗AI助手/)).toBeInTheDocument();
  });
});
