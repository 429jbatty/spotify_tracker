/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import AlbumMobileList from "./AlbumMobileList";

function albums(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: String(index + 1),
    name: `Album ${index + 1}`,
    artist: "Test Artist",
    latestListen: "2026-01-02T00:00:00Z",
    release_year: 2000 + index,
    totalListens: index + 1,
    entry_source: "manual",
    label: "Test Label",
  }));
}

afterEach(() => cleanup());

describe("AlbumMobileList", () => {
  it("renders the current library page supplied by the shared paginator", () => {
    render(
      <AlbumMobileList
        albums={albums(50)}
        sortBy="latestListen"
        ascending={false}
        onSortChange={vi.fn()}
        onOpenAlbum={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /Album 50/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Album 51/i })).not.toBeInTheDocument();
  });

  it("uses an accessible sort control and opens a card on click", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const onOpenAlbum = vi.fn();
    const library = albums(1);
    render(
      <AlbumMobileList
        albums={library}
        sortBy="latestListen"
        ascending={false}
        onSortChange={onSortChange}
        onOpenAlbum={onOpenAlbum}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Sort library"), "name:asc");
    expect(onSortChange).toHaveBeenCalledWith("name", true);

    await user.click(screen.getByRole("button", { name: /Album 1/i }));
    expect(onOpenAlbum).toHaveBeenCalledWith(library[0]);
  });

  it("keeps column filters available on mobile", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(
      <AlbumMobileList
        albums={albums(1)}
        sortBy="label"
        ascending={true}
        onSortChange={vi.fn()}
        onOpenAlbum={vi.fn()}
        filterHeaders={[{ key: "artist", label: "Artist" }]}
        filterOptions={{
          artist: [
            { value: "Test Artist", label: "Test Artist" },
            { value: "Other Artist", label: "Other Artist" },
          ],
        }}
        columnFilters={{}}
        onFilterChange={onFilterChange}
      />,
    );

    expect(screen.getByLabelText("Sort library")).toHaveValue("label:asc");
    await user.click(screen.getByText("Filters"));
    await user.click(screen.getByRole("button", { name: "Filter Artist" }));
    await user.click(screen.getByRole("checkbox", { name: "Other Artist" }));
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onFilterChange).toHaveBeenCalledWith("artist", ["Test Artist"]);
    expect(screen.getByRole("button", { name: "Filter Artist" })).toHaveClass("min-h-11");
  });
});
