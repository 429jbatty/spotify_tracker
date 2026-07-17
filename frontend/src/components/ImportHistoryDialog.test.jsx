/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  commitImport: vi.fn(),
  deleteImportSession: vi.fn(),
  fetchImportHistory: vi.fn(),
  fetchImportReview: vi.fn(),
  previewImport: vi.fn(),
  resolveImportReview: vi.fn(),
  uploadSpotifyImportZip: vi.fn(),
}));

vi.mock("../services/albumApi", () => api);

import ImportHistoryDialog from "./ImportHistoryDialog";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function activeSpotifyImport() {
  return {
    id: 19,
    source: "spotify_import",
    status: "storing_streaming_events",
    session_name: "Spotify history",
    started_at: "2026-07-12T20:00:00Z",
    completed_at: null,
    summary: {
      total_rows: 10,
      new_event_rows: 7,
      derived_album_listens: 0,
      review_candidates: 0,
      progress_current: 7,
      progress_total: 10,
    },
    steps: [
      {
        key: "store_source",
        label: "Store source data",
        status: "current",
        current: 7,
        total: 10,
      },
    ],
    current_step_key: "store_source",
    current_step_label: "Store source data",
    current_step_detail: "7 of 10 Spotify plays stored.",
  };
}

function DialogHarness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Reopen import history
      </button>
      <ImportHistoryDialog
        hideTrigger
        open={open}
        onOpenChange={setOpen}
        selectedUser={{ slug: "jacob", display_name: "Jacob" }}
      />
    </>
  );
}

function importFor(id, detail) {
  return {
    ...activeSpotifyImport(),
    id,
    current_step_detail: detail,
  };
}

describe("ImportHistoryDialog", () => {
  it("keeps persisted active-import status visible while reopening refreshes", async () => {
    const user = userEvent.setup();
    const activeImport = activeSpotifyImport();
    let resolveNextHistory;
    const nextHistory = new Promise((resolve) => {
      resolveNextHistory = resolve;
    });

    api.fetchImportHistory
      .mockResolvedValueOnce([activeImport])
      .mockImplementation(() => nextHistory);
    api.fetchImportReview.mockResolvedValue([]);

    render(<DialogHarness />);

    expect(
      (await screen.findAllByText("7 of 10 Spotify plays stored.")).length
    ).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Reopen import history" }));

    expect(screen.getAllByText("7 of 10 Spotify plays stored.").length).toBeGreaterThan(0);

    resolveNextHistory([activeImport]);
    await waitFor(() => {
      expect(api.fetchImportHistory).toHaveBeenCalled();
    });
  });

  it("hides prior-profile data and ignores its late refresh response", async () => {
    const jacobImport = importFor(19, "Jacob import is active.");
    const taylorImport = importFor(20, "Taylor import is active.");
    let resolveJacobRefresh;
    const jacobRefresh = new Promise((resolve) => {
      resolveJacobRefresh = resolve;
    });

    api.fetchImportHistory.mockImplementation((slug) =>
      slug === "jacob" ? jacobRefresh : Promise.resolve([taylorImport])
    );
    api.fetchImportReview.mockResolvedValue([]);

    const { rerender } = render(
      <ImportHistoryDialog
        hideTrigger
        open
        onOpenChange={vi.fn()}
        selectedUser={{ slug: "jacob", display_name: "Jacob" }}
      />
    );

    rerender(
      <ImportHistoryDialog
        hideTrigger
        open
        onOpenChange={vi.fn()}
        selectedUser={{ slug: "taylor", display_name: "Taylor" }}
      />
    );

    expect(
      (await screen.findAllByText("Taylor import is active.")).length
    ).toBeGreaterThan(0);

    resolveJacobRefresh([jacobImport]);
    await waitFor(() => {
      expect(api.fetchImportHistory).toHaveBeenCalledWith("jacob");
    });
    expect(screen.queryByText("Jacob import is active.")).not.toBeInTheDocument();
    expect(screen.getAllByText("Taylor import is active.").length).toBeGreaterThan(0);
  });
});
