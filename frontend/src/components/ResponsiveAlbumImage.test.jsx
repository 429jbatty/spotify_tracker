// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ResponsiveAlbumImage from "./ResponsiveAlbumImage";
import { artworkSourceSet, artworkVariantUrl } from "@/lib/artworkSources";

afterEach(cleanup);


describe("artworkSourceSet", () => {
  it("builds WebP candidates for content-addressed local artwork", () => {
    expect(artworkSourceSet("/media/artwork/release-sha256-a1b2c3d4e5f6.jpg")).toBe(
      "/media/artwork/release-sha256-a1b2c3d4e5f6-240.webp 240w, /media/artwork/release-sha256-a1b2c3d4e5f6-640.webp 640w"
    );
  });

  it("does not invent variants for remote or legacy artwork", () => {
    expect(artworkSourceSet("https://example.test/cover.jpg")).toBeUndefined();
    expect(artworkSourceSet("/media/artwork/legacy.jpg")).toBeUndefined();
    expect(
      artworkSourceSet("/media/artwork/e6f8d52b-3b24-4546-b86d-99d79b0df209.jpg")
    ).toBeUndefined();
  });

  it("selects a single optimized URL for non-img renderers", () => {
    expect(
      artworkVariantUrl("/media/artwork/release-sha256-a1b2c3d4e5f6.jpg", 240)
    ).toBe("/media/artwork/release-sha256-a1b2c3d4e5f6-240.webp");
    expect(artworkVariantUrl("https://example.test/cover.jpg", 240)).toBe(
      "https://example.test/cover.jpg"
    );
  });

  it("retries the original before falling back when a variant fails", () => {
    const original = "/media/artwork/release-sha256-a1b2c3d4e5f6.jpg";
    render(<ResponsiveAlbumImage src={original} alt="Album" />);
    const image = screen.getByRole("img", { name: "Album" });

    fireEvent.error(image);
    expect(image).not.toHaveAttribute("srcset");
    expect(image).toHaveAttribute("src", original);

    fireEvent.error(image);
    expect(image.getAttribute("src")).toContain("placeholder_art.png");
  });
});
