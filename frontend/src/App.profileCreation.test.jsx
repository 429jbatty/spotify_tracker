/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  createUser,
  fetchAlbumState,
  fetchSpotifyStatus,
  fetchUsers,
} from "./services/albumApi";

vi.mock("./services/albumApi", () => ({
  createUser: vi.fn(),
  fetchAlbumState: vi.fn(),
  fetchSpotifyStatus: vi.fn(),
  fetchUsers: vi.fn(),
  setSelectedUserSlug: vi.fn(),
}));

vi.mock("./components/splash/SplashPage", () => ({
  default: ({ onCreateProfile }) => (
    <button
      type="button"
      onClick={() => onCreateProfile({ display_name: "New Listener", slug: "new-listener" })}
    >
      Create test profile
    </button>
  ),
}));

function CurrentPath() {
  return <output data-testid="current-path">{useLocation().pathname}</output>;
}

describe("profile creation route", () => {
  it("opens the created profile using the slug returned by the API", async () => {
    const user = userEvent.setup();
    createUser.mockResolvedValue({ slug: "returned-slug" });
    fetchUsers.mockResolvedValue([{ slug: "returned-slug", display_name: "New Listener" }]);
    fetchAlbumState.mockResolvedValue({ completed_albums: {} });
    fetchSpotifyStatus.mockResolvedValue({ connected: false });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
        <CurrentPath />
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: "Create test profile" }));

    expect(createUser).toHaveBeenCalledWith({
      display_name: "New Listener",
      slug: "new-listener",
    });
    await waitFor(() => {
      expect(screen.getByTestId("current-path")).toHaveTextContent("/returned-slug/discovery");
    });
  });
});
