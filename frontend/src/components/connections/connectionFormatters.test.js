import { describe, expect, it } from "vitest";
import {
  formatCount,
  formatPercent,
  formatQualityLabel,
  formatRoleLabel,
  formatRoleSummary,
  getPrimaryRole,
} from "./connectionFormatters";

describe("connection formatters", () => {
  it("formats counts and percentages", () => {
    expect(formatCount(1, "album")).toBe("1 album");
    expect(formatCount(2, "artist")).toBe("2 artists");
    expect(formatPercent(0.717)).toBe("72%");
  });

  it("formats known roles and quality flags", () => {
    expect(formatRoleLabel("writer_composer")).toBe("Writer");
    expect(formatQualityLabel("name_only_identity")).toBe("Name-only identity");
  });

  it("orders role summaries by count", () => {
    expect(
      formatRoleSummary({
        engineering: 1,
        mixing_mastering: 3,
        producer: 2,
      })
    ).toBe("Mixing/mastering 3, Producer 2, Engineering 1");
  });

  it("selects the highest-volume role", () => {
    expect(getPrimaryRole({ producer: 2, engineering: 5 })).toBe("engineering");
  });
});
