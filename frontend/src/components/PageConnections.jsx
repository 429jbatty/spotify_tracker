import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Disc3,
  GitCompareArrows,
  Network,
  Search,
  Sparkles,
  UsersRound,
} from "lucide-react";
import ConnectionSummaryCard from "./connections/ConnectionSummaryCard";
import ConnectionsGraph from "./connections/ConnectionsGraph";
import { filterContributorOptions } from "./connections/contributorSearch";
import { connectionSearchProgress } from "./connections/connectionSearchStatus";
import {
  fetchAlbumConnectionGraph,
  fetchConnectionGraph,
  fetchCreditPersonDetail,
  fetchRecurringContributors,
  searchContributors,
} from "@/services/albumApi";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  formatCount,
  formatRoleSummary,
} from "./connections/connectionFormatters";
import { Input } from "@/components/ui/input";

function CoverageStat({ icon, label, value }) {
  const IconComponent = icon;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <IconComponent className="mb-3 size-4 text-primary" />
      <p className="text-2xl font-semibold text-foreground">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function EmptyState({ reason }) {
  const message =
    reason === "no_projected_credit_facts"
      ? "No projected credit facts are available for this profile yet."
      : reason === "low_credit_fact_coverage"
        ? "Credit coverage is still too sparse to rank recurring contributors."
        : reason === "empty_library"
          ? "This profile does not have library albums yet."
          : "No recurring contributors matched the current quality filters.";

  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center">
      <AlertCircle className="mx-auto mb-3 size-5 text-muted-foreground" />
      <p className="text-sm font-medium text-foreground">{message}</p>
    </div>
  );
}

function graphContributorId(contributor) {
  return contributor?.person_key ? `contributor:${contributor.person_key}` : null;
}

function firstGraphAlbumNode(graphPayload) {
  const albumNodes = (graphPayload?.nodes || []).filter((node) => node.type === "album");
  return albumNodes.find((node) => node.image_url) || albumNodes[0] || null;
}

function ExplorationPrompt({ active, description, disabled, icon, label, onClick }) {
  const IconComponent = icon;

  return (
    <Button
      className="h-auto justify-between gap-3 px-3 py-3 text-left"
      disabled={disabled}
      onClick={onClick}
      type="button"
      variant={active ? "default" : "outline"}
    >
      <span className="flex min-w-0 items-center gap-3">
        <IconComponent className={active ? "size-4 shrink-0" : "size-4 shrink-0 text-primary"} />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{label}</span>
          <span className={active ? "block truncate text-xs font-normal opacity-80" : "block truncate text-xs font-normal text-muted-foreground"}>
            {description}
          </span>
        </span>
      </span>
      <ArrowRight className={active ? "size-4 shrink-0 opacity-80" : "size-4 shrink-0 text-muted-foreground"} />
    </Button>
  );
}

function albumOptionLabel(album) {
  return album ? `${album.name} · ${album.artist}` : "";
}

function contributorOptionLabel(contributor) {
  return contributor?.person_name || "";
}

function filterAlbumOptions(albumOptions, query, excludeAlbumId) {
  const terms = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  return albumOptions
    .filter((album) => album.id !== excludeAlbumId)
    .filter((album) => {
      if (terms.length === 0) return true;
      const text = `${album.name} ${album.artist}`.toLowerCase();
      return terms.every((term) => text.includes(term));
    })
    .slice(0, 8);
}

function AlbumConnectionSearch({
  albumOptions,
  excludeAlbumId,
  id,
  label,
  onChange,
  value,
}) {
  const selectedAlbum = albumOptions.find((album) => album.id === value) || null;
  const [query, setQuery] = useState(albumOptionLabel(selectedAlbum));
  const [open, setOpen] = useState(false);
  const filteredOptions = useMemo(
    () => filterAlbumOptions(albumOptions, query, excludeAlbumId),
    [albumOptions, excludeAlbumId, query]
  );

  const selectAlbum = (album) => {
    onChange(album.id);
    setQuery(albumOptionLabel(album));
    setOpen(false);
  };

  return (
    <div className="relative grid gap-1">
      <label className="text-xs font-medium text-muted-foreground" htmlFor={id}>
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoComplete="off"
          className="pl-9"
          id={id}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setQuery(event.target.value);
            if (value) onChange("");
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search by album or artist"
          value={query}
        />
      </div>
      {open && (
        <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-md">
          {filteredOptions.length > 0 ? (
            filteredOptions.map((album) => (
              <button
                className="flex w-full min-w-0 flex-col rounded-sm px-3 py-2 text-left hover:bg-muted"
                key={album.id}
                onMouseDown={(event) => {
                  event.preventDefault();
                  selectAlbum(album);
                }}
                type="button"
              >
                <span className="truncate text-sm font-medium text-foreground">
                  {album.name}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {album.artist}
                </span>
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-muted-foreground">
              No albums matched that search.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ContributorSearch({
  contributors,
  id,
  label,
  onChange,
  onQueryChange,
  searchLoading,
  searchResults,
  value,
}) {
  const selectedContributor = contributors.find((contributor) => contributor.person_key === value) || null;
  const [query, setQuery] = useState(contributorOptionLabel(selectedContributor));
  const [open, setOpen] = useState(false);
  const localOptions = useMemo(
    () => filterContributorOptions(contributors, query),
    [contributors, query]
  );
  const hasQuery = Boolean(query.trim());
  const options = hasQuery ? searchResults : localOptions;

  const selectContributor = (contributor) => {
    onChange(contributor.person_key);
    setQuery(contributorOptionLabel(contributor));
    setOpen(false);
  };

  return (
    <div className="relative grid gap-1">
      <label className="text-xs font-medium text-muted-foreground" htmlFor={id}>
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoComplete="off"
          className="pl-9"
          id={id}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setQuery(event.target.value);
            if (value) onChange("");
            onQueryChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search by contributor or role"
          value={query}
        />
      </div>
      {open && (
        <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-md">
          {searchLoading ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">Searching contributors...</p>
          ) : options.length > 0 ? (
            options.map((contributor) => (
              <button
                className="flex w-full min-w-0 flex-col rounded-sm px-3 py-2 text-left hover:bg-muted"
                key={contributor.person_key}
                onMouseDown={(event) => {
                  event.preventDefault();
                  selectContributor(contributor);
                }}
                type="button"
              >
                <span className="truncate text-sm font-medium text-foreground">
                  {contributor.person_name}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {formatRoleSummary(contributor.role_buckets)}
                </span>
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-muted-foreground">
              No contributors matched that search.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ExplorationHeader({
  activeMode,
  albumStart,
  albumFocusId,
  albumOptions,
  albumPair,
  connectionError,
  connectionElapsedSeconds,
  connectionLoading,
  connectionNotice,
  contributorFocusKey,
  contributors,
  onActivateConnectorMode,
  onActivateAlbumMode,
  onActivateConnectionMode,
  onAlbumPairChange,
  onConnectAlbums,
  onCancelConnection,
  onFocusContributorChange,
  onContributorQueryChange,
  onFocusAlbumChange,
  onStartAlbum,
  onStartConnector,
  topConnector,
  contributorSearchLoading,
  contributorSearchResults,
}) {
  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Explore your credit network
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          Follow the producers, musicians, writers, and engineers connecting your library.
        </p>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <ExplorationPrompt
          active={activeMode === "connector"}
          description={topConnector ? topConnector.person_name : "Waiting for connector data"}
          disabled={!topConnector}
          icon={Sparkles}
          label="Start from a contributor"
          onClick={onActivateConnectorMode}
        />
        <ExplorationPrompt
          active={activeMode === "album"}
          description={albumStart ? `${albumStart.label} by ${albumStart.artist}` : "Waiting for album data"}
          disabled={!albumStart}
          icon={Search}
          label="Explore an album"
          onClick={onActivateAlbumMode}
        />
        <ExplorationPrompt
          active={activeMode === "connection"}
          description="Find direct or indirect credit paths"
          disabled={albumOptions.length < 2}
          icon={GitCompareArrows}
          label="Connect two albums"
          onClick={onActivateConnectionMode}
        />
      </div>

      {activeMode === "connector" && (
        <div className="rounded-lg border border-border bg-card p-3">
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
            <ContributorSearch
              contributors={contributors}
              id="contributor-start-search"
              label="Contributor"
              onChange={onFocusContributorChange}
              onQueryChange={onContributorQueryChange}
              searchLoading={contributorSearchLoading}
              searchResults={contributorSearchResults}
              value={contributorFocusKey}
            />
            <Button
              className="self-end"
              disabled={!contributorFocusKey}
              onClick={onStartConnector}
              type="button"
            >
              Explore from here
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Rebuild the graph around this contributor and their connected albums.
          </p>
        </div>
      )}

      {activeMode === "album" && (
        <div className="rounded-lg border border-border bg-card p-3">
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
            <AlbumConnectionSearch
              albumOptions={albumOptions}
              excludeAlbumId={null}
              id="album-start-search"
              label="Album"
              onChange={onFocusAlbumChange}
              value={albumFocusId}
            />
            <Button
              className="self-end"
              disabled={!albumFocusId}
              onClick={onStartAlbum}
              type="button"
            >
              Explore from here
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Rebuild the graph around this album and its credited contributors.
          </p>
        </div>
      )}

      {activeMode === "connection" && (
        <div className="rounded-lg border border-border bg-card p-3">
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <AlbumConnectionSearch
              albumOptions={albumOptions}
              excludeAlbumId={albumPair.albumBId}
              id="album-connection-a"
              label="First album"
              onChange={(value) => onAlbumPairChange("albumAId", value)}
              value={albumPair.albumAId}
            />
            <AlbumConnectionSearch
              albumOptions={albumOptions}
              excludeAlbumId={albumPair.albumAId}
              id="album-connection-b"
              label="Second album"
              onChange={(value) => onAlbumPairChange("albumBId", value)}
              value={albumPair.albumBId}
            />
            <Button
              className="self-end"
              disabled={!connectionLoading && (!albumPair.albumAId || !albumPair.albumBId || albumPair.albumAId === albumPair.albumBId)}
              onClick={connectionLoading ? onCancelConnection : onConnectAlbums}
              type="button"
              variant={connectionLoading ? "outline" : "default"}
            >
              {connectionLoading ? "Cancel search" : "Show connection"}
            </Button>
          </div>
          {connectionLoading && (
            <div aria-live="polite" className="mt-3 rounded-md bg-muted/60 px-3 py-2 text-sm text-muted-foreground" role="status">
              <p className="font-medium text-foreground">
                {connectionSearchProgress(connectionElapsedSeconds).label}
              </p>
              <p className="mt-0.5 text-xs">
                {connectionSearchProgress(connectionElapsedSeconds).detail}
              </p>
            </div>
          )}
          {connectionError && (
            <p className="mt-2 text-sm text-destructive">{connectionError}</p>
          )}
          {connectionNotice && (
            <p className="mt-2 text-sm text-muted-foreground">{connectionNotice}</p>
          )}
        </div>
      )}
    </section>
  );
}

function DetailAlbumRow({ album, onOpenAlbum }) {
  return (
    <button
      type="button"
      onClick={() => onOpenAlbum?.(album.album_id)}
      className="w-full rounded-md border border-border px-3 py-2 text-left hover:bg-muted"
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-foreground">
          {album.name}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {album.artist}
        </span>
      </span>
    </button>
  );
}

function PersonDetailSheet({
  contributor,
  detail,
  error,
  loading,
  onOpenAlbum,
  onOpenChange,
  open,
}) {
  const activeContributor = detail || contributor;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[92vw] overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="pr-8 text-xl">
            {activeContributor?.person_name || "Contributor"}
          </SheetTitle>
          <SheetDescription>
            {activeContributor
              ? `${formatCount(activeContributor.connected_album_count, "album")} across ${formatCount(activeContributor.distinct_primary_artist_count, "artist")}`
              : "Loading contributor detail"}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 px-4 pb-6">
          {loading && (
            <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
              Loading contributor detail...
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
              {error}
            </div>
          )}

          {activeContributor && (
            <>
              <div className="grid grid-cols-3 gap-2">
                <CoverageStat
                  icon={Disc3}
                  label="albums"
                  value={activeContributor.connected_album_count}
                />
                <CoverageStat
                  icon={UsersRound}
                  label="artists"
                  value={activeContributor.distinct_primary_artist_count}
                />
                <CoverageStat
                  icon={Network}
                  label="roles"
                  value={Object.keys(activeContributor.role_buckets || {}).length}
                />
              </div>

              <section className="space-y-2">
                <h2 className="text-sm font-semibold text-foreground">Roles</h2>
                <p className="text-sm leading-6 text-muted-foreground">
                  {formatRoleSummary(activeContributor.role_buckets)}
                </p>
              </section>

              <section className="space-y-2">
                <h2 className="text-sm font-semibold text-foreground">Albums</h2>
                <div className="space-y-2">
                  {(detail?.albums || activeContributor.representative_albums || []).map(
                    (album) => (
                      <DetailAlbumRow
                        album={album}
                        key={album.album_id}
                        onOpenAlbum={onOpenAlbum}
                      />
                    )
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default function PageConnections({ albums, selectedUser, onOpenAlbum }) {
  const [payload, setPayload] = useState(null);
  const [graphPayload, setGraphPayload] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedContributor, setSelectedContributor] = useState(null);
  const [personDetail, setPersonDetail] = useState(null);
  const [personDetailError, setPersonDetailError] = useState(null);
  const [personDetailLoading, setPersonDetailLoading] = useState(false);
  const [graphFocusNodeId, setGraphFocusNodeId] = useState(null);
  const [activeMode, setActiveMode] = useState(null);
  const [contributorFocusKey, setContributorFocusKey] = useState("");
  const [albumFocusId, setAlbumFocusId] = useState("");
  const [albumPair, setAlbumPair] = useState({ albumAId: "", albumBId: "" });
  const [albumConnection, setAlbumConnection] = useState(null);
  const [albumConnectionError, setAlbumConnectionError] = useState(null);
  const [albumConnectionNotice, setAlbumConnectionNotice] = useState(null);
  const [albumConnectionLoading, setAlbumConnectionLoading] = useState(false);
  const [albumConnectionElapsedSeconds, setAlbumConnectionElapsedSeconds] = useState(0);
  const [showContributorDirectory, setShowContributorDirectory] = useState(false);
  const [contributorSearchLoading, setContributorSearchLoading] = useState(false);
  const [contributorSearchResults, setContributorSearchResults] = useState([]);
  const connectionControllerRef = useRef(null);
  const contributorSearchControllerRef = useRef(null);
  const connectionRequestIdRef = useRef(0);
  const graphSectionRef = useRef(null);
  const albumById = useMemo(() => {
    return new Map((albums || []).map((album) => [String(album.id), album]));
  }, [albums]);
  const albumOptions = useMemo(() => {
    return (albums || [])
      .filter((album) => album.id && album.name && album.artist)
      .map((album) => ({
        id: String(album.id),
        name: album.name,
        artist: album.artist,
      }))
      .sort((left, right) => (
        left.artist.localeCompare(right.artist)
        || left.name.localeCompare(right.name)
      ));
  }, [albums]);
  const selectedUserSlug = selectedUser?.slug;

  useEffect(() => () => {
    connectionRequestIdRef.current += 1;
    connectionControllerRef.current?.abort();
    connectionControllerRef.current = null;
    contributorSearchControllerRef.current?.abort();
    contributorSearchControllerRef.current = null;
  }, [selectedUserSlug]);

  useEffect(() => {
    if (!selectedUserSlug) return undefined;
    const controller = new AbortController();

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setLoadError(null);
    const graphOptions = graphFocusNodeId
      ? {
          contributorLimit: 18,
          albumLimitPerContributor: 10,
          albumLimit: 80,
          focusNodeId: graphFocusNodeId,
          signal: controller.signal,
        }
      : {
          contributorLimit: 8,
          albumLimitPerContributor: 4,
          albumLimit: 32,
          signal: controller.signal,
        };

    Promise.all([
      fetchRecurringContributors(selectedUserSlug, {
        limit: 25,
        signal: controller.signal,
      }),
      fetchConnectionGraph(selectedUserSlug, graphOptions),
    ])
      .then(([recurringResponse, graphResponse]) => {
        setPayload(recurringResponse);
        setGraphPayload(graphResponse);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error.message || "Connections could not be loaded.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [graphFocusNodeId, selectedUserSlug]);

  useEffect(() => {
    if (!albumConnectionLoading) return undefined;
    const startedAt = Date.now();
    const intervalId = window.setInterval(() => {
      setAlbumConnectionElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(intervalId);
  }, [albumConnectionLoading]);

  const handleInspect = (contributor) => {
    const controller = new AbortController();
    setSelectedContributor(contributor);
    setPersonDetail(null);
    setPersonDetailError(null);
    setPersonDetailLoading(true);

    fetchCreditPersonDetail(contributor.person_key, selectedUserSlug, {
      signal: controller.signal,
    })
      .then((detail) => setPersonDetail(detail))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setPersonDetailError(error.message || "Contributor detail could not be loaded.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setPersonDetailLoading(false);
      });
  };

  const closeSheet = (open) => {
    if (open) return;
    setSelectedContributor(null);
    setPersonDetail(null);
    setPersonDetailError(null);
    setPersonDetailLoading(false);
  };

  const openAlbumById = (albumId) => {
    const album = albumById.get(String(albumId));
    if (album) onOpenAlbum?.(album);
  };

  const activePayload = payload?.user_slug === selectedUserSlug ? payload : null;
  const activeGraphPayload = graphPayload?.user_slug === selectedUserSlug ? graphPayload : null;
  const results = activePayload?.results || [];
  const topConnector = results[0] || null;
  const albumStart = firstGraphAlbumNode(activeGraphPayload);
  const returnToGraph = () => {
    window.requestAnimationFrame(() => {
      graphSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
  const focusContributor = (contributor) => {
    const nodeId = graphContributorId(contributor);
    if (nodeId) {
      setActiveMode("connector");
      setAlbumConnection(null);
      setContributorFocusKey(contributor.person_key);
      setGraphFocusNodeId(nodeId);
      returnToGraph();
    }
  };
  const handleAlbumPairChange = (field, value) => {
    setAlbumPair((current) => ({ ...current, [field]: value }));
    setAlbumConnectionError(null);
    setAlbumConnectionNotice(null);
  };
  const handleStartAlbum = () => {
    if (!albumFocusId) return;
    setAlbumConnection(null);
    setGraphFocusNodeId(`album:${albumFocusId}`);
  };
  const handleActivateConnectorMode = () => {
    setActiveMode("connector");
    setAlbumConnection(null);
    setAlbumConnectionError(null);
    if (!contributorFocusKey && topConnector?.person_key) {
      setContributorFocusKey(topConnector.person_key);
    }
  };
  const handleStartConnector = () => {
    if (!contributorFocusKey) return;
    const contributor = [...results, ...contributorSearchResults]
      .find((item) => item.person_key === contributorFocusKey);
    if (contributor) focusContributor(contributor);
  };
  const handleContributorQueryChange = (query) => {
    contributorSearchControllerRef.current?.abort();
    if (!query.trim() || !selectedUserSlug) {
      setContributorSearchLoading(false);
      setContributorSearchResults([]);
      return;
    }

    const controller = new AbortController();
    contributorSearchControllerRef.current = controller;
    setContributorSearchLoading(true);
    searchContributors(selectedUserSlug, {
      query,
      limit: 8,
      signal: controller.signal,
    })
      .then((response) => {
        if (contributorSearchControllerRef.current === controller) {
          setContributorSearchResults(response?.results || []);
        }
      })
      .catch(() => {
        if (contributorSearchControllerRef.current === controller) {
          setContributorSearchResults([]);
        }
      })
      .finally(() => {
        if (contributorSearchControllerRef.current === controller) {
          setContributorSearchLoading(false);
        }
      });
  };
  const handleActivateAlbumMode = () => {
    setActiveMode("album");
    setAlbumConnection(null);
    setAlbumConnectionError(null);
    if (!albumFocusId && albumStart?.album_id) {
      setAlbumFocusId(String(albumStart.album_id));
    }
  };
  const handleActivateConnectionMode = () => {
    setActiveMode("connection");
    setAlbumConnectionError(null);
  };
  const handleConnectAlbums = () => {
    if (!selectedUserSlug) return;
    if (!albumPair.albumAId || !albumPair.albumBId) {
      setAlbumConnectionError("Choose two albums to compare.");
      return;
    }
    if (albumPair.albumAId === albumPair.albumBId) {
      setAlbumConnectionError("Choose two different albums.");
      return;
    }
    const controller = new AbortController();
    const requestId = connectionRequestIdRef.current + 1;
    connectionRequestIdRef.current = requestId;
    connectionControllerRef.current?.abort();
    connectionControllerRef.current = controller;
    setActiveMode("connection");
    setAlbumConnection(null);
    setAlbumConnectionLoading(true);
    setAlbumConnectionElapsedSeconds(0);
    setAlbumConnectionError(null);
    setAlbumConnectionNotice(null);
    fetchAlbumConnectionGraph(selectedUserSlug, {
      albumAId: albumPair.albumAId,
      albumBId: albumPair.albumBId,
      signal: controller.signal,
    })
      .then((connection) => {
        if (requestId !== connectionRequestIdRef.current) return;
        setAlbumConnection(connection);
        setGraphFocusNodeId(null);
      })
      .catch((error) => {
        if (controller.signal.aborted || requestId !== connectionRequestIdRef.current) return;
        setAlbumConnectionError(error.message || "Album connection could not be loaded.");
      })
      .finally(() => {
        if (requestId !== connectionRequestIdRef.current) return;
        connectionControllerRef.current = null;
        setAlbumConnectionLoading(false);
      });
  };
  const handleCancelConnection = () => {
    connectionRequestIdRef.current += 1;
    connectionControllerRef.current?.abort();
    connectionControllerRef.current = null;
    setAlbumConnection(null);
    setAlbumConnectionLoading(false);
    setAlbumConnectionElapsedSeconds(0);
    setAlbumConnectionError(null);
    setAlbumConnectionNotice("Search cancelled. Choose two albums to try another connection.");
  };

  return (
    <>
      <div className="space-y-7 p-6">
        <ExplorationHeader
          activeMode={activeMode}
          albumStart={albumStart}
          albumFocusId={albumFocusId}
          albumOptions={albumOptions}
          albumPair={albumPair}
          connectionError={albumConnectionError}
          connectionElapsedSeconds={albumConnectionElapsedSeconds}
          connectionLoading={albumConnectionLoading}
          connectionNotice={albumConnectionNotice}
          contributorFocusKey={contributorFocusKey}
          contributors={results}
          onActivateConnectorMode={handleActivateConnectorMode}
          onActivateAlbumMode={handleActivateAlbumMode}
          onActivateConnectionMode={handleActivateConnectionMode}
          onAlbumPairChange={handleAlbumPairChange}
          onCancelConnection={handleCancelConnection}
          onConnectAlbums={handleConnectAlbums}
          onContributorQueryChange={handleContributorQueryChange}
          onFocusContributorChange={setContributorFocusKey}
          onFocusAlbumChange={setAlbumFocusId}
          onStartAlbum={handleStartAlbum}
          onStartConnector={handleStartConnector}
          topConnector={topConnector}
          contributorSearchLoading={contributorSearchLoading}
          contributorSearchResults={contributorSearchResults}
        />

        {loading && results.length === 0 && (
          <div className="rounded-lg border border-border p-8 text-center text-sm text-muted-foreground">
            Loading connections...
          </div>
        )}

        {loadError && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-6 text-sm text-destructive">
            {loadError}
          </div>
        )}

        {!loading && !loadError && results.length === 0 && (
          <EmptyState reason={activePayload?.insufficient_data_reason} />
        )}

        {results.length > 0 && (
          <div ref={graphSectionRef}>
            <ConnectionsGraph
              albumConnection={albumConnection}
              focusNodeId={graphFocusNodeId}
              graph={albumConnection || activeGraphPayload}
              isUpdating={loading}
              onFocusNode={(nodeId) => {
                setActiveMode(null);
                setAlbumConnection(null);
                setGraphFocusNodeId(nodeId);
              }}
              onInspectContributor={handleInspect}
              onOpenAlbum={openAlbumById}
            />
          </div>
        )}

        {results.length > 0 && (
          <section className="space-y-4 border-t border-border/70 pt-5">
            <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-base font-semibold text-foreground">More starting points</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Try another contributor when you want to restart the graph.
                </p>
              </div>
              {results.length > 4 && (
                <Button
                  onClick={() => setShowContributorDirectory((current) => !current)}
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  {showContributorDirectory ? "Hide contributor directory" : "Browse contributor directory"}
                </Button>
              )}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {results.slice(0, 4).map((contributor) => (
                <ConnectionSummaryCard
                  compact
                  contributor={contributor}
                  key={contributor.person_key}
                  onFocus={focusContributor}
                  onInspect={handleInspect}
                />
              ))}
            </div>

            {showContributorDirectory && (
              <div className="space-y-3 rounded-lg border border-border/70 bg-muted/20 p-4">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">Contributor directory</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Search every eligible contributor in your library. Results use connected albums and artist breadth, never listen count.
                  </p>
                </div>
                <ContributorSearch
                  contributors={results}
                  id="contributor-directory-search"
                  label="Search all contributors"
                  onChange={setContributorFocusKey}
                  onQueryChange={handleContributorQueryChange}
                  searchLoading={contributorSearchLoading}
                  searchResults={contributorSearchResults}
                  value={contributorFocusKey}
                />
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {results.slice(4).map((contributor) => (
                    <ConnectionSummaryCard
                      compact
                      contributor={contributor}
                      key={contributor.person_key}
                      onFocus={focusContributor}
                      onInspect={handleInspect}
                    />
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

      </div>

      <PersonDetailSheet
        contributor={selectedContributor}
        detail={personDetail}
        error={personDetailError}
        loading={personDetailLoading}
        onOpenAlbum={openAlbumById}
        onOpenChange={closeSheet}
        open={Boolean(selectedContributor)}
      />
    </>
  );
}
