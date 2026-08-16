/* @vitest-environment jsdom */

import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it } from "vitest";

import { useDocumentMetadata } from "./useDocumentMetadata";

function MetadataProbe(props) {
  useDocumentMetadata(props);
  return null;
}

afterEach(() => {
  document.head.innerHTML = "";
});

describe("useDocumentMetadata", () => {
  it("sets a branded title and share metadata for a public profile route", () => {
    render(
      <MetadataProbe
        title="Taylor's Library | Albumary"
        description="Explore Taylor's album listening history on Albumary."
        path="/taylor/library"
      />
    );

    expect(document.title).toBe("Taylor's Library | Albumary");
    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      "Explore Taylor's album listening history on Albumary."
    );
    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "http://localhost:3000/taylor/library"
    );
    expect(document.head.querySelector('meta[property="og:title"]')).toHaveAttribute(
      "content",
      "Taylor's Library | Albumary"
    );
  });
});
