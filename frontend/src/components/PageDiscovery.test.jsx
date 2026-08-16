/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PageDiscovery from "./PageDiscovery";

vi.mock("./AlbumCardVertical", () => ({
  default: ({ album }) => <div data-testid="discovery-album">{album.name}</div>,
}));

vi.mock("./discovery/DiscoveryMetricRail", () => ({ default: () => null }));
vi.mock("./discovery/DiscoveryQualityCard", () => ({ default: () => null }));
vi.mock("./discovery/NewToYouTrend", () => ({ default: () => null }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-07-16T12:00:00.000Z"));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function album(index) {
  return {
    album_key: `Artist - Album ${index}`,
    artist: "Artist",
    id: String(index),
    listen_history: [`2026-06-${String(index).padStart(2, "0")}T12:00:00.000Z`],
    name: `Album ${index}`,
  };
}

describe("PageDiscovery", () => {
  it("shows every in-range album from the full collection, not only the filtered first eight", () => {
    const allAlbums = Array.from({ length: 10 }, (_, index) => album(index + 1));

    render(
      <MemoryRouter initialEntries={["/listener/discovery?range=1y"]}>
        <PageDiscovery
          albums={allAlbums.slice(0, 1)}
          allAlbums={allAlbums}
          onOpenAlbum={vi.fn()}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Listens in this range" })).toBeVisible();
    expect(screen.getAllByTestId("discovery-album")).toHaveLength(10);
    expect(screen.getAllByTestId("discovery-album")[0]).toHaveTextContent("Album 10");
    expect(screen.getByText("Album 1")).toBeVisible();
    expect(screen.queryByRole("button", { name: /View all listens/i })).not.toBeInTheDocument();
  });

  it("offers only bounded ranges and normalizes the obsolete all-time range", () => {
    render(
      <MemoryRouter initialEntries={["/listener/discovery?range=all"]}>
        <PageDiscovery albums={[album(1)]} allAlbums={[album(1)]} />
      </MemoryRouter>
    );

    expect(screen.getByRole("tab", { name: "1Y" })).toHaveAttribute(
      "data-state",
      "active"
    );
    expect(screen.queryByRole("tab", { name: "All" })).not.toBeInTheDocument();
  });

  it("guides an empty owned profile to each supported first-listen path", () => {
    const onAddAlbum = vi.fn();
    const onImport = vi.fn();
    const onConnectSpotify = vi.fn();

    render(
      <MemoryRouter>
        <PageDiscovery
          albums={[]}
          allAlbums={[]}
          onAddAlbum={onAddAlbum}
          onImport={onImport}
          onConnectSpotify={onConnectSpotify}
        />
      </MemoryRouter>
    );

    expect(screen.getByText("Turn album listens into a map of your taste.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Add your first album" }));
    fireEvent.click(screen.getByRole("button", { name: "Import Last.fm" }));
    fireEvent.click(screen.getByRole("button", { name: "Upload Spotify ZIP" }));
    fireEvent.click(screen.getByRole("button", { name: "Connect Spotify" }));

    expect(onAddAlbum).toHaveBeenCalledOnce();
    expect(onImport).toHaveBeenNthCalledWith(1, "lastfm");
    expect(onImport).toHaveBeenNthCalledWith(2, "spotify_import");
    expect(onConnectSpotify).toHaveBeenCalledOnce();
  });
});
