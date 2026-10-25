/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import SplashPage from "./SplashPage";
import { fetchCurrentAccount, fetchSplashData } from "@/services/albumApi";

vi.mock("@/services/albumApi", () => ({
  fetchCurrentAccount: vi.fn(),
  fetchSplashData: vi.fn(),
  signOut: vi.fn(),
}));

afterEach(() => cleanup());

describe("SplashPage", () => {
  it("explains the product and the ways to add listening history", async () => {
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockRejectedValue(new Error("No active session"));

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Keep a history of the albums you listen to." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Connect Spotify")).toBeInTheDocument();
    expect(screen.getByText("Import Last.fm")).toBeInTheDocument();
    expect(screen.getByText("Upload Spotify history")).toBeInTheDocument();
    expect(screen.getByText("Log an album yourself")).toBeInTheDocument();
  });

  it("hides profile creation for an account that already owns a profile", async () => {
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockResolvedValue({
      email: "person@example.com",
      profile_slugs: ["jacob"],
      profiles: [{ slug: "jacob", display_name: "Jacob" }],
    });

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(fetchCurrentAccount).toHaveBeenCalled();
    });

    expect(screen.queryByRole("button", { name: "Create profile" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create your profile" })).not.toBeInTheDocument();
  });

  it("keeps an owned profile reachable even when it is not in public browse results", async () => {
    const user = userEvent.setup();
    const onOpenProfile = vi.fn();
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockResolvedValue({
      email: "person@example.com",
      profile_slugs: ["private-listener"],
      profiles: [{ slug: "private-listener", display_name: "Private Listener" }],
    });

    render(<SplashPage onCreateProfile={vi.fn()} onOpenProfile={onOpenProfile} onLogin={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Open your profile" }));
    expect(onOpenProfile).toHaveBeenCalledWith("private-listener");
  });

  it("starts Google sign-in from Create profile for a visitor without a session", async () => {
    const user = userEvent.setup();
    const onStartProfileCreation = vi.fn();
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockRejectedValue(new Error("No active session"));

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
        onStartProfileCreation={onStartProfileCreation}
      />
    );

    const createProfileButton = await screen.findByRole("button", { name: "Create profile" });
    await user.click(createProfileButton);

    expect(onStartProfileCreation).toHaveBeenCalledOnce();
  });

  it("keeps a persistent setup action for a signed-in account without a profile", async () => {
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockResolvedValue({
      email: "person@example.com",
      profile_slugs: [],
      profiles: [],
    });

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
      />
    );

    expect(await screen.findByRole("button", { name: "Choose profile name" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Finish setting up your profile" }),
    ).toBeInTheDocument();
  });

  it("clears the incomplete-setup state after profile creation", async () => {
    const user = userEvent.setup();
    const onCreateProfile = vi.fn().mockResolvedValue({
      slug: "new-listener",
      display_name: "New Listener",
    });
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockResolvedValue({
      email: "person@example.com",
      profile_slugs: [],
      profiles: [],
    });

    render(
      <SplashPage
        onCreateProfile={onCreateProfile}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Choose profile name" }));
    await user.type(screen.getByLabelText("Profile name"), "New Listener");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    await waitFor(() => {
      expect(onCreateProfile).toHaveBeenCalledWith({
        slug: "new-listener",
        display_name: "New Listener",
      });
    });
    expect(
      screen.queryByRole("heading", { name: "Finish setting up your profile" }),
    ).not.toBeInTheDocument();
  });

  it("shows a retryable message when Google sign-in is cancelled", async () => {
    const user = userEvent.setup();
    const onStartProfileCreation = vi.fn();
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockRejectedValue(new Error("No active session"));

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
        onStartProfileCreation={onStartProfileCreation}
        authError="cancelled"
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Google sign-in was cancelled");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onStartProfileCreation).toHaveBeenCalledOnce();
  });

  it("explains an identity conflict without offering another sign-in attempt", async () => {
    fetchSplashData.mockResolvedValue({ featured_users: [], recent_activity: [] });
    fetchCurrentAccount.mockRejectedValue(new Error("No active session"));

    render(
      <SplashPage
        onCreateProfile={vi.fn()}
        onOpenProfile={vi.fn()}
        onLogin={vi.fn()}
        authError="identity_conflict"
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("already linked to a different Google identity");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
