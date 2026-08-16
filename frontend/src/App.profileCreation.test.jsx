/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  createUser,
  fetchAlbumState,
  fetchCurrentAccount,
  fetchSpotifyStatus,
  fetchUsers,
  spotifyConnectUrl,
} from "./services/albumApi";

vi.mock("./services/albumApi", () => ({
  createUser: vi.fn(),
  disconnectSpotify: vi.fn(),
  fetchAlbumState: vi.fn(),
  fetchSpotifyStatus: vi.fn(),
  fetchCurrentAccount: vi.fn().mockRejectedValue(new Error("No active session")),
  getOwnedProfileSlugs: vi.fn(() => []),
  fetchUsers: vi.fn(),
  login: vi.fn(),
  ownsProfile: vi.fn(() => true),
  setSelectedUserSlug: vi.fn(),
  signOut: vi.fn(),
  spotifyConnectUrl: vi.fn(),
  storeGoogleSessionFromFragment: vi.fn(),
  syncSpotifyNow: vi.fn(),
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

afterEach(() => cleanup());

function CurrentPath() {
  const location = useLocation();
  return <output data-testid="current-path">{location.pathname}{location.search}</output>;
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

  it("sends a first-time Google account directly to profile creation", async () => {
    fetchCurrentAccount.mockResolvedValueOnce({ profile_slugs: [] });
    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <App />
        <CurrentPath />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("current-path")).toHaveTextContent("/?create_profile=1");
    });
  });

  it("routes an invalid multi-profile account to an ownership error", async () => {
    fetchCurrentAccount.mockResolvedValueOnce({ profile_slugs: ["first", "second"] });
    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <App />
        <CurrentPath />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("current-path")).toHaveTextContent("/?ownership_error=multiple_profiles");
    });
  });

  it("returns an OAuth callback error to the splash page", async () => {
    render(
      <MemoryRouter initialEntries={["/auth/callback?auth_error=cancelled"]}>
        <App />
        <CurrentPath />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("current-path")).toHaveTextContent("/?auth_error=cancelled");
    });
  });

  it("starts Spotify authorization from an empty owned profile", async () => {
    const user = userEvent.setup();
    fetchUsers.mockResolvedValue([{ slug: "owner", display_name: "Owner" }]);
    fetchCurrentAccount.mockResolvedValue({ profile_slugs: ["owner"] });
    fetchAlbumState.mockResolvedValue({ completed_albums: {} });
    fetchSpotifyStatus.mockResolvedValue({ connected: false });
    spotifyConnectUrl.mockResolvedValue(null);

    render(
      <MemoryRouter initialEntries={["/owner/discovery"]}>
        <App />
      </MemoryRouter>
    );

    await user.click(await screen.findByRole("button", { name: "Connect Spotify" }));
    expect(spotifyConnectUrl).toHaveBeenCalledWith("owner");
  });
});
