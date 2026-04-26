import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import SubpageBackHome from "../SubpageBackHome";
import * as navDirection from "../../../hooks/useNavDirection";

function HostedRoutes({ initialPath = "/start" }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/start" element={<SubpageBackHome />} />
        <Route path="/doctor/my-ai" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SubpageBackHome", () => {
  beforeEach(() => {
    vi.spyOn(navDirection, "markIntentionalBack").mockImplementation(() => {});
  });

  test("renders back arrow and home icon", () => {
    render(<HostedRoutes />);
    expect(screen.getByLabelText("返回")).toBeInTheDocument();
    expect(screen.getByLabelText("回到首页")).toBeInTheDocument();
  });

  test("home icon click navigates to /doctor/my-ai and marks intentional back", () => {
    render(<HostedRoutes />);
    fireEvent.click(screen.getByLabelText("回到首页"));
    expect(navDirection.markIntentionalBack).toHaveBeenCalled();
    expect(screen.getByText("HOME")).toBeInTheDocument();
  });

  test("home icon click does NOT bubble to parent (stopPropagation)", () => {
    const parentClick = vi.fn();
    render(
      <MemoryRouter initialEntries={["/start"]}>
        <div onClick={parentClick} data-testid="parent">
          <Routes>
            <Route path="/start" element={<SubpageBackHome />} />
          </Routes>
        </div>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByLabelText("回到首页"));
    expect(parentClick).not.toHaveBeenCalled();
  });
});
