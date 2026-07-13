/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";

import CreateProfileDialog from "./CreateProfileDialog";
import { profileSlugFromName } from "./utils/profileSlug";

afterEach(cleanup);

function DialogHarness({ onCreateProfile = vi.fn() }) {
  const [open, setOpen] = useState(true);
  return (
    <CreateProfileDialog
      open={open}
      onOpenChange={setOpen}
      onCreateProfile={onCreateProfile}
    />
  );
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function fillCredentials(user) {
  await user.type(screen.getByLabelText("Email"), "listener@example.com");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery-staple");
}

describe("profileSlugFromName", () => {
  it("creates URL-safe slugs from display names", () => {
    expect(profileSlugFromName("  Béyoncé & JAY-Z! ")).toBe("beyonce-jay-z");
    expect(profileSlugFromName("---")).toBe("");
  });
});

describe("CreateProfileDialog", () => {
  it("validates missing and unusable profile names", async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);

    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a profile name");

    await user.type(screen.getByLabelText("Profile name"), "***");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(screen.getByRole("alert")).toHaveTextContent("at least one letter or number");
  });

  it("submits the display name and generated slug, then closes", async () => {
    const user = userEvent.setup();
    const onCreateProfile = vi.fn().mockResolvedValue({ slug: "beyonce-jay-z" });
    render(<DialogHarness onCreateProfile={onCreateProfile} />);

    await user.type(screen.getByLabelText("Profile name"), "Béyoncé & JAY-Z!");
    await fillCredentials(user);
    expect(screen.getByText("Your profile URL: /beyonce-jay-z")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(onCreateProfile).toHaveBeenCalledWith({
      display_name: "Béyoncé & JAY-Z!",
      slug: "beyonce-jay-z",
      email: "listener@example.com",
      password: "correct-horse-battery-staple",
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("disables the form while profile creation is in progress", async () => {
    const user = userEvent.setup();
    const request = deferred();
    render(<DialogHarness onCreateProfile={vi.fn().mockReturnValue(request.promise)} />);

    await user.type(screen.getByLabelText("Profile name"), "Listener");
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(screen.getByRole("button", { name: "Creating profile..." })).toBeDisabled();
    expect(screen.getByLabelText("Profile name")).toBeDisabled();
    request.resolve({ slug: "listener" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("shows API failures and allows another attempt", async () => {
    const user = userEvent.setup();
    const onCreateProfile = vi.fn().mockRejectedValue(new Error("User already exists: alex"));
    render(<DialogHarness onCreateProfile={onCreateProfile} />);

    await user.type(screen.getByLabelText("Profile name"), "Alex");
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("User already exists: alex");
    expect(screen.getByRole("button", { name: "Create profile" })).toBeEnabled();
  });
});
