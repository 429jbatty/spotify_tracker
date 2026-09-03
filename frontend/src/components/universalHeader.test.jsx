/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversalHeader from "./universalHeader";

vi.mock("./AlbumCreateDialog", () => ({ default: () => null }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

afterEach(cleanup);

describe("UniversalHeader", () => {
  it("keeps Connect Spotify visible but disabled without sync access", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <UniversalHeader
          view="discovery"
          albums={[]}
          onDataChanged={vi.fn()}
          selectedUser={{ slug: "listener", display_name: "Listener" }}
          isOwner
          spotifyStatus={{ connected: false, spotify_sync_eligible: false }}
          onSwitchUser={vi.fn()}
        />
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: "Open profile tools" }));

    expect(await screen.findByText("Connect Spotify")).toHaveAttribute(
      "data-disabled"
    );
  });
});
