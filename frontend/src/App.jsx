import { useCallback, useEffect, useMemo, useState } from "react";
import AlbumTable from "./components/AlbumTable";
import AlbumTimeView from "./components/PageReleaseDate";
import AlbumSearch from "./components/AlbumSearch";
import {
  fetchAlbumState,
  fetchSpotifyStatus,
  fetchUsers,
  setSelectedUserSlug,
} from "./services/albumApi";
import normalizeAlbums from "./services/albumNormalizer";
import Header from "./components/universalHeader";
import PageDiscovery from "./components/PageDiscovery";
import PageDataQuality from "./components/PageDataQuality";
import { filterAlbums } from "./components/utils/albumFilters";
import SplashPage from "./components/splash/SplashPage";
import { Toaster } from "./components/Toaster";
import ImportHistoryDialog from "./components/ImportHistoryDialog";

const PATH_VIEW_MAP = {
  albums: "table",
  discovery: "discovery",
  timeline: "timeline",
  quality: "quality",
};

const VIEW_PATH_MAP = {
  table: "albums",
  discovery: "discovery",
  timeline: "timeline",
  quality: "quality",
};

function parseRoute(pathname) {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return { page: "splash", userSlug: null, view: "discovery" };

  const [userSlug, section] = segments;
  return {
    page: "profile",
    userSlug,
    view: PATH_VIEW_MAP[section] || "discovery",
  };
}

function profilePath(userSlug, nextView = "discovery") {
  if (nextView === "discovery") return `/${userSlug}/discovery`;
  return `/${userSlug}/${VIEW_PATH_MAP[nextView] || "discovery"}`;
}

function App() {
  const [data, setData] = useState(null);
  const [dataUserSlug, setDataUserSlug] = useState(null);
  const [users, setUsers] = useState([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [spotifyStatus, setSpotifyStatus] = useState({ connected: false });
  const [spotifyStatusUserSlug, setSpotifyStatusUserSlug] = useState(null);
  const [error, setError] = useState(null);
  const [route, setRoute] = useState(() => parseRoute(window.location.pathname));
  const [searchTerm, setSearchTerm] = useState("");
  const [activeFilters, setActiveFilters] = useState([]);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const selectedUser = useMemo(() => {
    if (route.page !== "profile") return null;
    return users.find((user) => user.slug === route.userSlug) || null;
  }, [route.page, route.userSlug, users]);
  const view = route.page === "profile" ? route.view : "discovery";

  const loadAlbumState = useCallback(async (options = {}) => {
    if (!selectedUser) return null;
    const json = await fetchAlbumState(selectedUser.slug, options);
    const normalized = {
      ...json,
      completed_albums: normalizeAlbums(json.completed_albums)
    };
    setData(normalized);
    setDataUserSlug(selectedUser.slug);
    setError(null);
    return normalized;
  }, [selectedUser]);

  const loadSpotifyStatus = useCallback(async (options = {}) => {
    if (!selectedUser) return null;
    const status = await fetchSpotifyStatus(selectedUser.slug, options);
    setSpotifyStatus(status);
    setSpotifyStatusUserSlug(selectedUser.slug);
    return status;
  }, [selectedUser]);

  const navigateTo = useCallback((path) => {
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
    setRoute(parseRoute(path));
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      setRoute(parseRoute(window.location.pathname));
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    fetchUsers()
      .then((loadedUsers) => {
        setUsers(loadedUsers);
        setUsersLoaded(true);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
        setUsersLoaded(true);
      });
  }, []);

  useEffect(() => {
    if (selectedUser) {
      setSelectedUserSlug(selectedUser.slug);
      return;
    }

    if (usersLoaded && route.page === "profile") {
      setSelectedUserSlug(null);
    }
  }, [route.page, selectedUser, usersLoaded]);

  useEffect(() => {
    if (!selectedUser) return;
    const controller = new AbortController();

    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAlbumState({ signal: controller.signal }).catch((err) => {
      if (controller.signal.aborted) return;
      if (err?.name !== "TypeError") {
        console.error(err);
      }
      setError(err.message);
    });
    return () => controller.abort();
  }, [loadAlbumState, selectedUser]);

  useEffect(() => {
    if (!selectedUser) return;
    const controller = new AbortController();

    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSpotifyStatus({ signal: controller.signal }).catch((err) => {
      if (controller.signal.aborted) return;
      if (err?.name !== "TypeError") {
        console.error(err);
      }
      setSpotifyStatus({ connected: false, last_sync_error: err.message });
    });
    return () => controller.abort();
  }, [loadSpotifyStatus, selectedUser]);

  const handleOpenProfile = (userSlug) => {
    setSelectedUserSlug(userSlug);
    navigateTo(`/${userSlug}`);
  };

  const handleSwitchUser = () => {
    setSelectedUserSlug(null);
    setData(null);
    setDataUserSlug(null);
    setSpotifyStatus({ connected: false });
    setSpotifyStatusUserSlug(null);
    navigateTo("/");
  };

  const handleViewChange = (nextView) => {
    if (!selectedUser) return;
    navigateTo(profilePath(selectedUser.slug, nextView));
  };

  if (error) return <div>Error: {error}</div>;
  if (route.page === "splash") {
    return <SplashPage onOpenProfile={handleOpenProfile} />;
  }
  if (usersLoaded && !selectedUser) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="max-w-md rounded-lg border border-border/80 bg-card p-6 text-center shadow-sm">
          <h1 className="text-2xl font-semibold tracking-tight">Profile not found</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            This Albumary profile does not exist or is not active.
          </p>
          <button
            type="button"
            onClick={handleSwitchUser}
            className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/85"
          >
            Back to profiles
          </button>
        </div>
      </div>
    );
  }
  if (!data || dataUserSlug !== selectedUser.slug) return <div>Loading...</div>;

  // Pre-calculate total listens and latest listen for sorting purposes
  const processedAlbums = Object.entries(data.completed_albums).map(([id, data]) => {
    const history = data.listen_history || [];
    return {
      id,

      // core safe fields (critical fix)
      name: data.name ?? "Unknown Album",
      artist: data.artist ?? "Unknown Artist",

      ...data,
      totalListens: history.length,
      // We keep latestListen as a sortable string/date object
      latestListen: history.length ? [...history].sort().reverse()[0] : null,
    };
  });

  const visibleAlbums = filterAlbums(processedAlbums, searchTerm, activeFilters);
  const filteredAlbums = Object.fromEntries(
    visibleAlbums.map((album) => [album.id, album])
  );
  const handleFilterSelect = (filter) => {
    setActiveFilters((current) => {
      if (current.some((item) => item.id === filter.id)) return current;
      return [...current, filter];
    });
    handleViewChange("table");
  };

  const removeFilter = (filterId) => {
    setActiveFilters((current) => current.filter((filter) => filter.id !== filterId));
  };

  const clearFilters = () => {
    setSearchTerm("");
    setActiveFilters([]);
  };

  return (
    <>
      <div className="min-h-screen space-y-10 ">

        {/* vertical stack header and search bar */}
        <div className="flex flex-col gap-4">
          {/* Header with tabs */}
          <Header
            view={view}
            setView={handleViewChange}
            albums={processedAlbums}
            onDataChanged={loadAlbumState}
            selectedUser={selectedUser}
            spotifyStatus={
              spotifyStatusUserSlug === selectedUser.slug
                ? spotifyStatus
                : { connected: false }
            }
            onSpotifyStatusChanged={loadSpotifyStatus}
            onSwitchUser={handleSwitchUser}
            importDialogOpen={importDialogOpen}
            onImportDialogOpenChange={setImportDialogOpen}
          />

          {/* Search box (skip on dashboard) */}
          {!(view === "dashboard" || view === "discovery") && (
            <div className="px-6">
              <AlbumSearch searchTerm={searchTerm} setSearchTerm={setSearchTerm} />
            </div>
          )}

          {(searchTerm || activeFilters.length > 0) && (
            <div className="flex flex-wrap items-center gap-2 px-6">
              {searchTerm && (
                <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
                  Search: {searchTerm}
                </span>
              )}
              {activeFilters.map((filter) => (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => removeFilter(filter.id)}
                  className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-muted"
                >
                  {filter.label}
                </button>
              ))}
              <button
                type="button"
                onClick={clearFilters}
                className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {view === "discovery" && (
          <PageDiscovery
            albums={visibleAlbums}
            allAlbums={processedAlbums}
            onFilterSelect={handleFilterSelect}
            onDataChanged={loadAlbumState}
          />
        )}
        {view === "table" && (
          <AlbumTable
            albums={filteredAlbums}
            searchTerm={searchTerm}
            onFilterSelect={handleFilterSelect}
            onDataChanged={loadAlbumState}
          />
        )}
        {view === "timeline" && (
          <AlbumTimeView
            albums={filteredAlbums}
            onFilterSelect={handleFilterSelect}
            onDataChanged={loadAlbumState}
          />
        )}
        {view === "quality" && (
          <PageDataQuality
            albums={visibleAlbums}
            onDataChanged={loadAlbumState}
            onFilterSelect={handleFilterSelect}
          />
        )}
      </div>
      <Toaster />
      <ImportHistoryDialog
        selectedUser={selectedUser}
        albums={processedAlbums}
        onDataChanged={loadAlbumState}
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        hideTrigger
      />
    </>
  );
}

export default App;
