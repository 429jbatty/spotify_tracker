/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReleaseDateChart from "./ReleaseDateChart";

vi.mock("@/hooks/useElementSize", () => ({
  useElementSize: () => ({ width: 390, height: 0 }),
}));

function albumsForYears(years) {
  return Object.fromEntries(
    years.map((year) => [year, { name: `Album ${year}`, release_date: `${year}-01-01` }]),
  );
}

describe("ReleaseDateChart", () => {
  const commonProps = {
    onReset: vi.fn(),
    onToggle: vi.fn(),
    selectedFilter: { decade: null, year: null },
  };

  it("fits the decade chart to a narrow container and supports keyboard selection", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <ReleaseDateChart
        {...commonProps}
        albums={albumsForYears([1972, 1984, 1996, 2008, 2020])}
        chartMode="decade"
        onSelect={onSelect}
      />,
    );

    expect(container.querySelector("svg")).toHaveAttribute("width", "390");

    const decade = screen.getByRole("button", { name: "Decade 1970: 1 album" });
    fireEvent.keyDown(decade, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledWith(1970, null);
  });

  it("uses an intentional horizontal scroll model when decade bars need touch space", () => {
    const { container } = render(
      <ReleaseDateChart
        {...commonProps}
        albums={albumsForYears([1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010])}
        chartMode="decade"
        onSelect={vi.fn()}
      />,
    );

    expect(container.querySelector("svg")).toHaveAttribute("width", "460");
    expect(screen.getByText(/Scroll horizontally to browse every decade/i)).toBeInTheDocument();
  });

  it("provides a clearly labeled horizontal year view with reachable bar controls", () => {
    const onSelect = vi.fn();
    const years = Array.from({ length: 12 }, (_, index) => 2000 + index);
    const { container } = render(
      <ReleaseDateChart
        {...commonProps}
        albums={albumsForYears(years)}
        chartMode="year"
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText(/Scroll horizontally to browse every year/i)).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("width", "652");

    fireEvent.keyDown(screen.getByRole("button", { name: "Year 2011: 1 album" }), { key: " " });
    expect(onSelect).toHaveBeenCalledWith(2010, 2011);
  });
});
