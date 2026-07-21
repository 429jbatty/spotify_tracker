/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PageConnections from "./PageConnections";
import {
  fetchAlbumConnectionGraph,
  fetchConnectionGraph,
  fetchRecurringContributors,
  searchContributors,
} from "@/services/albumApi";

vi.mock("@/services/albumApi", () => ({
  fetchAlbumConnectionGraph: vi.fn(),
  fetchConnectionGraph: vi.fn(),
  fetchCreditPersonDetail: vi.fn(),
  fetchRecurringContributors: vi.fn(),
  searchContributors: vi.fn(),
}));

vi.mock("./connections/ConnectionsGraph", () => ({
  default: ({ albumConnection, graph, isUpdating }) => (
    <div
      aria-busy={isUpdating}
      data-connection-reason={albumConnection?.search_limited_reason || ""}
      data-testid="connections-graph-mock"
    >
      {albumConnection?.album_a?.name || graph?.nodes?.[0]?.label || "Graph"}
    </div>
  ),
}));

const albums = [
  { id: 1, name: "Album One", artist: "Artist A" },
  { id: 2, name: "Album Two", artist: "Artist B" },
  { id: 3, name: "Album Three", artist: "Artist C" },
];

function recurring(userSlug = "listener") {
  return {
    user_slug: userSlug,
    results: [{
      person_key: "name:producer",
      person_name: "Producer One",
      role_buckets: { producer: 2 },
      connected_album_count: 2,
      distinct_primary_artist_count: 2,
      representative_albums: [],
    }],
  };
}

function graph(userSlug = "listener") {
  return {
    user_slug: userSlug,
    nodes: [{ id: "album:1", type: "album", album_id: 1, label: `${userSlug} graph`, artist: "Artist A" }],
    edges: [],
  };
}

function connection(albumA = "Album One", reason = null) {
  return {
    user_slug: "listener",
    album_a: { album_id: 1, name: albumA, artist: "Artist A" },
    album_b: { album_id: 2, name: "Album Two", artist: "Artist B" },
    best_path: null,
    alternate_paths: [],
    nodes: [],
    edges: [],
    no_path: reason == null,
    search_status: reason ? "limited" : "complete",
    search_limited_reason: reason,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

async function renderLoaded(userSlug = "listener") {
  fetchRecurringContributors.mockResolvedValue(recurring(userSlug));
  fetchConnectionGraph.mockResolvedValue(graph(userSlug));
  const user = userEvent.setup();
  const view = render(
    <PageConnections
      albums={albums}
      onOpenAlbum={vi.fn()}
      selectedUser={{ slug: userSlug }}
    />,
  );
  await screen.findByTestId("connections-graph-mock");
  return { user, ...view };
}

async function chooseAlbum(label, query, optionName) {
  const input = screen.getByLabelText(label);
  await userEvent.clear(input);
  await userEvent.type(input, query);
  const option = screen.getByRole("button", { name: optionName });
  fireEvent.mouseDown(option);
}

afterEach(() => cleanup());

beforeEach(() => {
  vi.clearAllMocks();
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
  window.requestAnimationFrame = (callback) => callback();
});

describe("PageConnections request lifecycle", () => {
  it("loads recurring contributors and the initial graph for the selected user", async () => {
    await renderLoaded();

    expect(fetchRecurringContributors).toHaveBeenCalledWith("listener", expect.objectContaining({ limit: 25 }));
    expect(fetchConnectionGraph).toHaveBeenCalledWith("listener", expect.objectContaining({ contributorLimit: 8 }));
    expect(screen.getByTestId("connections-graph-mock")).toHaveTextContent("listener graph");
    expect(screen.getByRole("button", { name: /Connect two albums/ })).toBeEnabled();
  });

  it("searches beyond the initial recommendations before enabling contributor exploration", async () => {
    searchContributors.mockResolvedValue({
      results: [{
        person_key: "name:ranked-contributor-29",
        person_name: "Ranked Contributor 29",
        role_buckets: { writer_composer: 2 },
        connected_album_count: 2,
        distinct_primary_artist_count: 2,
      }],
    });
    const { user } = await renderLoaded();

    await user.click(screen.getByRole("button", { name: /Start from a contributor/ }));
    const input = screen.getByLabelText("Contributor");
    await user.clear(input);
    await user.type(input, "Ranked Contributor 29");

    await waitFor(() => expect(searchContributors).toHaveBeenLastCalledWith(
      "listener",
      expect.objectContaining({ query: "Ranked Contributor 29", limit: 8 }),
    ));
    const result = await screen.findByRole("button", { name: /Ranked Contributor 29/ });
    fireEvent.mouseDown(result);
    expect(screen.getByRole("button", { name: "Explore from here" })).toBeEnabled();
  });

  it("clears a pending contributor search when the selected user changes", async () => {
    const pending = deferred();
    searchContributors.mockReturnValue(pending.promise);
    const { rerender, user } = await renderLoaded();

    await user.click(screen.getByRole("button", { name: /Start from a contributor/ }));
    await user.type(screen.getByLabelText("Contributor"), "Ranked Contributor 29");
    const signal = searchContributors.mock.calls.at(-1)[1].signal;

    fetchRecurringContributors.mockResolvedValue(recurring("friend"));
    fetchConnectionGraph.mockResolvedValue(graph("friend"));
    rerender(<PageConnections albums={albums} onOpenAlbum={vi.fn()} selectedUser={{ slug: "friend" }} />);

    expect(signal.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Explore from here" })).toBeDisabled();
    await act(async () => pending.resolve({ results: [{ person_key: "name:stale" }] }));
    expect(screen.getByRole("button", { name: "Explore from here" })).toBeDisabled();
  });

  it("shows an initial loading failure instead of rendering a graph", async () => {
    fetchRecurringContributors.mockRejectedValue(new Error("Connections unavailable"));
    fetchConnectionGraph.mockResolvedValue(graph());
    render(<PageConnections albums={albums} onOpenAlbum={vi.fn()} selectedUser={{ slug: "listener" }} />);

    expect(await screen.findByText("Connections unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("connections-graph-mock")).not.toBeInTheDocument();
  });

  it("submits the selected album IDs and renders the returned connection", async () => {
    fetchAlbumConnectionGraph.mockResolvedValue(connection());
    const { user } = await renderLoaded();
    await user.click(screen.getByRole("button", { name: /Connect two albums/ }));
    await chooseAlbum("First album", "Album One", "Album OneArtist A");
    await chooseAlbum("Second album", "Album Two", "Album TwoArtist B");
    await user.click(screen.getByRole("button", { name: "Show connection" }));

    await waitFor(() => expect(fetchAlbumConnectionGraph).toHaveBeenCalledWith(
      "listener",
      expect.objectContaining({ albumAId: "1", albumBId: "2", signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByTestId("connections-graph-mock")).toHaveTextContent("Album One");
  });

  it("preserves the limited-result reason returned by the backend", async () => {
    fetchAlbumConnectionGraph.mockResolvedValue(connection("Partial Path", "queue_limit"));
    const { user } = await renderLoaded();
    await user.click(screen.getByRole("button", { name: /Connect two albums/ }));
    await chooseAlbum("First album", "Album One", "Album OneArtist A");
    await chooseAlbum("Second album", "Album Two", "Album TwoArtist B");
    await user.click(screen.getByRole("button", { name: "Show connection" }));

    await waitFor(() => expect(screen.getByTestId("connections-graph-mock")).toHaveAttribute(
      "data-connection-reason",
      "queue_limit",
    ));
  });

  it("cancels a pending search and ignores its late result", async () => {
    const pending = deferred();
    fetchAlbumConnectionGraph.mockReturnValue(pending.promise);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole("button", { name: /Connect two albums/ }));
    await chooseAlbum("First album", "Album One", "Album OneArtist A");
    await chooseAlbum("Second album", "Album Two", "Album TwoArtist B");
    await user.click(screen.getByRole("button", { name: "Show connection" }));

    const signal = fetchAlbumConnectionGraph.mock.calls[0][1].signal;
    await user.click(screen.getByRole("button", { name: "Cancel search" }));
    expect(signal.aborted).toBe(true);
    expect(screen.getByText(/Search cancelled/)).toBeInTheDocument();

    await act(async () => pending.resolve(connection("Late Album")));
    expect(screen.getByTestId("connections-graph-mock")).toHaveTextContent("listener graph");
    expect(screen.queryByText("Late Album")).not.toBeInTheDocument();
  });

  it("shows a request error and allows a successful retry", async () => {
    fetchAlbumConnectionGraph
      .mockRejectedValueOnce(new Error("Connection service unavailable"))
      .mockResolvedValueOnce(connection());
    const { user } = await renderLoaded();
    await user.click(screen.getByRole("button", { name: /Connect two albums/ }));
    await chooseAlbum("First album", "Album One", "Album OneArtist A");
    await chooseAlbum("Second album", "Album Two", "Album TwoArtist B");
    await user.click(screen.getByRole("button", { name: "Show connection" }));
    expect(await screen.findByText("Connection service unavailable")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show connection" }));
    await waitFor(() => expect(fetchAlbumConnectionGraph).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Connection service unavailable")).not.toBeInTheDocument();
  });

  it("aborts an active connection search when the selected user changes", async () => {
    const pending = deferred();
    fetchAlbumConnectionGraph.mockReturnValue(pending.promise);
    const { rerender, user } = await renderLoaded();
    await user.click(screen.getByRole("button", { name: /Connect two albums/ }));
    await chooseAlbum("First album", "Album One", "Album OneArtist A");
    await chooseAlbum("Second album", "Album Two", "Album TwoArtist B");
    await user.click(screen.getByRole("button", { name: "Show connection" }));
    const signal = fetchAlbumConnectionGraph.mock.calls[0][1].signal;

    fetchRecurringContributors.mockResolvedValue(recurring("friend"));
    fetchConnectionGraph.mockResolvedValue(graph("friend"));
    rerender(<PageConnections albums={albums} onOpenAlbum={vi.fn()} selectedUser={{ slug: "friend" }} />);

    expect(signal.aborted).toBe(true);
    expect(screen.queryByText("listener graph")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("connections-graph-mock")).toHaveTextContent("friend graph"));
  });
});
