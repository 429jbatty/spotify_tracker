import { describe, expect, it } from "vitest";
import { filterContributorOptions } from "./connections/contributorSearch";

const contributors = [
  {
    person_key: "mbid:producer-one",
    person_name: "Producer One",
    role_buckets: { producer: 4, engineering: 1 },
  },
  {
    person_key: "name:writer-two",
    person_name: "Writer Two",
    role_buckets: { writer_composer: 3 },
  },
  {
    person_key: "name:mixer-three",
    person_name: "Mixer Three",
    role_buckets: { mixing_mastering: 2 },
  },
];

describe("PageConnections contributor search", () => {
  it("matches contributors by person name", () => {
    expect(filterContributorOptions(contributors, "producer")).toEqual([
      contributors[0],
    ]);
  });

  it("matches contributors by formatted role text", () => {
    expect(filterContributorOptions(contributors, "mastering")).toEqual([
      contributors[2],
    ]);
  });

  it("requires every search term to match", () => {
    expect(filterContributorOptions(contributors, "producer engineering")).toEqual([
      contributors[0],
    ]);
    expect(filterContributorOptions(contributors, "producer mastering")).toEqual([]);
  });
});
