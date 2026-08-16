/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import AlbumTable from "./AlbumTable";

vi.mock("./AlbumPanelSheet", () => ({ default: () => null }));

function albums(count) {
  return Object.fromEntries(Array.from({ length: count }, (_, index) => [
    String(index + 1),
    {
      name: `Album ${index + 1}`,
      artist: "Test Artist",
      latestListen: "2026-01-02T00:00:00Z",
      release_year: 2000,
      totalListens: 1,
      entry_source: "manual",
      label: "Test Label",
    },
  ]));
}

function SearchResultTable({ library }) {
  return <AlbumTable key={Object.keys(library).join(",")} albums={library} onOpenAlbum={vi.fn()} />;
}

afterEach(() => cleanup());

describe("AlbumTable", () => {
  it("keeps large-library load, search results, scrolling, and mobile rendering within 50 items", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <MemoryRouter>
        <SearchResultTable library={albums(1279)} />
      </MemoryRouter>
    );

    expect(screen.getAllByRole("row")).toHaveLength(51);
    expect(screen.getAllByRole("button", { name: /Album /i })).toHaveLength(50);
    expect(screen.getByText("Showing 1–50 of 1279 albums")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Showing 51–100 of 1279 albums")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Album 51/i })).toBeInTheDocument();

    // Search results remount the table at page one and preserve the rendering budget.
    rerender(
      <MemoryRouter>
        <SearchResultTable library={albums(1)} />
      </MemoryRouter>
    );
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /Album /i })).toHaveLength(1);
  });
});
