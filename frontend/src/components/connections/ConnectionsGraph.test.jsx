import { describe, expect, it } from "vitest";
import {
  buildConnectionGraphModel,
  relatedIds,
  selectedLinks,
} from "./connectionGraphModel";
import { connectionRoleLabels } from "./connectionRoles";
import { resolveEffectiveSelectedId } from "./connectionSelection";

const graphPayload = {
  nodes: [
    {
      id: "contributor:name:producer one",
      type: "contributor",
      label: "Producer One",
      person_key: "name:producer one",
      role_buckets: { producer: 3 },
    },
    {
      id: "album:1",
      type: "album",
      label: "Album One",
      album_id: 1,
      artist: "Artist A",
      image_url: "/media/artwork/album-one.jpg",
      role_buckets: { producer: 1 },
    },
  ],
  edges: [
    {
      id: "edge:1",
      source: "contributor:name:producer one",
      target: "album:1",
      role_bucket: "producer",
    },
  ],
};

describe("ConnectionsGraph model", () => {
  it("normalizes explicit graph nodes and edges from the backend", () => {
    const model = buildConnectionGraphModel(graphPayload);

    expect(model.contributors).toHaveLength(1);
    expect(model.albums).toHaveLength(1);
    expect(model.albums[0]).toEqual(
      expect.objectContaining({
        image_url: "/media/artwork/album-one.jpg",
        name: "Album One",
        primaryRole: "producer",
      })
    );
    expect(model.links).toEqual([
      expect.objectContaining({
        role: "producer",
        source: "contributor:name:producer one",
        target: "album:1",
      }),
    ]);
  });

  it("identifies directly related nodes and edges", () => {
    const model = buildConnectionGraphModel(graphPayload);

    expect(Array.from(relatedIds("album:1", model.links))).toEqual([
      "album:1",
      "contributor:name:producer one",
    ]);
    expect(selectedLinks("album:1", model.links)).toHaveLength(1);
  });

  it("prefers a present external focus over a stale internal selection", () => {
    expect(
      resolveEffectiveSelectedId({
        currentSelectionScope: "album:2",
        focusNodeId: "album:2",
        nodeIds: ["album:1", "album:2"],
        selectedId: "album:1",
        selectedSelectionScope: "album:1",
      })
    ).toBe("album:2");
  });

  it("uses the internal selection when there is no external focus", () => {
    expect(
      resolveEffectiveSelectedId({
        currentSelectionScope: "default",
        focusNodeId: null,
        nodeIds: ["album:1", "album:2"],
        selectedId: "album:1",
        selectedSelectionScope: "default",
      })
    ).toBe("album:1");
  });

  it("clears selection when the external focus is missing from the graph", () => {
    expect(
      resolveEffectiveSelectedId({
        currentSelectionScope: "album:3",
        focusNodeId: "album:3",
        nodeIds: ["album:1", "album:2"],
        selectedId: "album:1",
        selectedSelectionScope: "album:1",
      })
    ).toBeNull();
  });

  it("lets graph clicks override the current external focus within the same focus scope", () => {
    expect(
      resolveEffectiveSelectedId({
        currentSelectionScope: "album:1",
        focusNodeId: "album:1",
        nodeIds: ["album:1", "album:2"],
        selectedId: "album:2",
        selectedSelectionScope: "album:1",
      })
    ).toBe("album:2");
  });

  it("formats role labels for the selected contributor-album edge", () => {
    expect(
      connectionRoleLabels(
        { id: "contributor:name:producer one" },
        { id: "album:1" },
        [
          {
            source: "contributor:name:producer one",
            target: "album:1",
            role: "producer",
          },
          {
            source: "contributor:name:producer one",
            target: "album:1",
            role: "engineering",
          },
          {
            source: "contributor:name:other",
            target: "album:1",
            role: "performer",
          },
        ]
      )
    ).toEqual(["Producer", "Engineering"]);
  });
});
