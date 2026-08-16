import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import AlbumTable from "./components/AlbumTable";
import AlbumTimeView from "./components/PageReleaseDate";
import AlbumSearch from "./components/AlbumSearch";
import {
  fetchAlbumState,
  fetchSpotifyStatus,
  spotifyConnectUrl,
  fetchUsers,
  createUser,
  beginGoogleSignIn,
  fetchCurrentAccount,
  getOwnedProfileSlugs,
  signOut,
  setSelectedUserSlug,
  storeGoogleSessionFromFragment,
} from "./services/albumApi";
import normalizeAlbums from "./services/albumNormalizer";
import Header from "./components/universalHeader";
import PageDiscovery from "./components/PageDiscovery";
import PageConnections from "./components/PageConnections";
import { filterAlbums } from "./components/utils/albumFilters";
import SplashPage from "./components/splash/SplashPage";
import { Toaster } from "./components/Toaster";
import ImportHistoryDialog from "./components/ImportHistoryDialog";
import AlbumPanelSheet from "./components/AlbumPanelSheet";
import EmptyLibraryState from "./components/onboarding/EmptyLibraryState";
import {
  albumPath,
  legacyRedirectPath,
  PROFILE_ROUTES,
  profilePath,
} from "./routing";
import {
  getProfileDocumentMetadata,
  useDocumentMetadata,
} from "./components/utils/useDocumentMetadata";

function LoadingState() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      Loading...
    </div>
  );
}

function NotFound({ onBackHome }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <div className="max-w-md rounded-lg border border-border/80 bg-card p-6 text-center shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          This Albumary page does not exist or is no longer available.
        </p>
        <button
          type="button"
          onClick={onBackHome}
          className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/85"
        >
          Back to profiles
        </button>
      </div>
    </div>
  );
}

function ProfileNotFound({ onBackHome }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <div className="max-w-md rounded-lg border border-border/80 bg-card p-6 text-center shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">Profile not found</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          This Albumary profile does not exist or is not active.
        </p>
        <button
          type="button"
          onClick={onBackHome}
          className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/85"
        >
          Back to profiles
        </button>
      </div>
    </div>
  );
}

function useUsers() {
  const [users, setUsers] = useState([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [error, setError] = useState(null);

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

  return { users, usersLoaded, error };
}

function RootRoute() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const openCreateProfileAfterSignIn = searchParams.get("create_profile") === "1";
  const hasMultipleProfiles = searchParams.get("ownership_error") === "multiple_profiles";
  const authError = searchParams.get("auth_error");
  useDocumentMetadata({
    title: "Albumary | Your album listening history",
    description: "Track album listens, revisit favorites, and explore the stories in your music library.",
    path: "/",
  });

  const startGoogleSignIn = async () => {
    const { authorize_url } = await beginGoogleSignIn();
    window.location.assign(authorize_url);
  };

  return (
    <SplashPage
      onCreateProfile={async (profile) => {
        const user = await createUser(profile);
        navigate(profilePath(user.slug, PROFILE_ROUTES.discovery));
        return user;
      }}
      onOpenProfile={(userSlug) => navigate(profilePath(userSlug, PROFILE_ROUTES.discovery))}
      onLogin={startGoogleSignIn}
      onStartProfileCreation={startGoogleSignIn}
      openCreateProfileAfterSignIn={openCreateProfileAfterSignIn}
      onCreateProfileIntentHandled={() => setSearchParams({}, { replace: true })}
      hasMultipleProfiles={hasMultipleProfiles}
      authError={authError}
      onAuthErrorHandled={() => {
        const nextSearchParams = new URLSearchParams(searchParams);
        nextSearchParams.delete("auth_error");
        setSearchParams(nextSearchParams, { replace: true });
      }}
    />
  );
}

function LegacyRedirect({ legacySection }) {
  const { userSlug } = useParams();
  return <Navigate to={legacyRedirectPath(userSlug, legacySection) || "/"} replace />;
}

function ProfileIndexRedirect() {
  const { userSlug } = useParams();
  return <Navigate to={profilePath(userSlug, PROFILE_ROUTES.discovery)} replace />;
}

function UserRoute({ view }) {
  const { users, usersLoaded, error } = useUsers();
  const { userSlug, albumId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [dataUserSlug, setDataUserSlug] = useState(null);
  const [spotifyStatus, setSpotifyStatus] = useState({ connected: false });
  const [spotifyStatusUserSlug, setSpotifyStatusUserSlug] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeFilters, setActiveFilters] = useState([]);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importDialogSource, setImportDialogSource] = useState("lastfm");
  const [albumCreateOpen, setAlbumCreateOpen] = useState(false);
  const [inlineAlbumSelection, setInlineAlbumSelection] = useState(null);
  const [ownedProfileSlugs, setOwnedProfileSlugs] = useState(getOwnedProfileSlugs);
  const [authenticatedAccount, setAuthenticatedAccount] = useState(null);
  const selectedUser = useMemo(
    () => users.find((user) => user.slug === userSlug) || null,
    [userSlug, users]
  );
  const isOwner = Boolean(selectedUser && ownedProfileSlugs.includes(selectedUser.slug));
  const profileName = selectedUser?.display_name || userSlug;
  const viewName = {
    [PROFILE_ROUTES.discovery]: "Discovery",
    [PROFILE_ROUTES.library]: "Library",
    [PROFILE_ROUTES.releases]: "Releases",
    [PROFILE_ROUTES.connections]: "Connections",
  }[view] || "Profile";
  const metadataAlbum = albumId ? data?.completed_albums?.[albumId] : null;
  useDocumentMetadata(getProfileDocumentMetadata({
    profileName,
    viewName,
    path: window.location.pathname,
    album: metadataAlbum,
    albumMissing: Boolean(albumId && data && !metadataAlbum),
    hasError: Boolean(error || loadError),
    profileMissing: usersLoaded && !selectedUser,
  }));

  useEffect(() => {
    fetchCurrentAccount()
      .then((account) => {
        setAuthenticatedAccount(account);
        setOwnedProfileSlugs(account.profile_slugs || []);
      })
      .catch(() => {
        setAuthenticatedAccount(null);
        setOwnedProfileSlugs(getOwnedProfileSlugs());
      });
  }, []);

  const loadAlbumState = useCallback(async (options = {}) => {
    if (!selectedUser) return null;
    const json = await fetchAlbumState(selectedUser.slug, options);
    const normalized = {
      ...json,
      completed_albums: normalizeAlbums(json.completed_albums),
    };
    setData(normalized);
    setDataUserSlug(selectedUser.slug);
    setLoadError(null);
    setInlineAlbumSelection((current) => {
      if (!current) return current;
      if (current.userSlug !== selectedUser.slug) return null;
      return Object.prototype.hasOwnProperty.call(
        normalized.completed_albums,
        String(current.albumId)
      )
        ? current
        : null;
    });
    return normalized;
  }, [selectedUser]);

  const loadSpotifyStatus = useCallback(async (options = {}) => {
    if (!selectedUser) return null;
    const status = await fetchSpotifyStatus(selectedUser.slug, options);
    setSpotifyStatus(status);
    setSpotifyStatusUserSlug(selectedUser.slug);
    return status;
  }, [selectedUser]);

  useEffect(() => {
    if (selectedUser) {
      setSelectedUserSlug(selectedUser.slug);
      return;
    }

    if (usersLoaded) {
      setSelectedUserSlug(null);
    }
  }, [selectedUser, usersLoaded]);

  useEffect(() => {
    if (!selectedUser) return undefined;
    const controller = new AbortController();

    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAlbumState({ signal: controller.signal }).catch((err) => {
      if (controller.signal.aborted) return;
      if (err?.name !== "TypeError") {
        console.error(err);
      }
      setLoadError(err.message);
    });
    return () => controller.abort();
  }, [loadAlbumState, selectedUser]);

  useEffect(() => {
    if (!selectedUser || !isOwner) return undefined;
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
  }, [isOwner, loadSpotifyStatus, selectedUser]);

  const handleSwitchUser = () => {
    setSelectedUserSlug(null);
    setData(null);
    setDataUserSlug(null);
    setSpotifyStatus({ connected: false });
    setSpotifyStatusUserSlug(null);
    setInlineAlbumSelection(null);
    navigate("/");
  };

  if (error || loadError) return <div>Error: {error || loadError}</div>;
  if (!usersLoaded) return <LoadingState />;
  if (!selectedUser) return <ProfileNotFound onBackHome={handleSwitchUser} />;
  if (!data || dataUserSlug !== selectedUser.slug) return <LoadingState />;

  const processedAlbums = Object.entries(data.completed_albums).map(([id, album]) => {
    const history = album.listen_history || [];
    return {
      id,
      name: album.name ?? "Unknown Album",
      artist: album.artist ?? "Unknown Artist",
      ...album,
      totalListens: history.length,
      latestListen: history.length ? [...history].sort().reverse()[0] : null,
    };
  });

  const visibleAlbums = filterAlbums(processedAlbums, searchTerm, activeFilters);
  const filteredAlbums = Object.fromEntries(
    visibleAlbums.map((album) => [album.id, album])
  );
  const routedAlbum = albumId
    ? processedAlbums.find((album) => String(album.id) === String(albumId))
    : null;
  const inlineAlbum = inlineAlbumSelection?.albumId
    && inlineAlbumSelection.userSlug === selectedUser.slug
    && !albumId
    ? processedAlbums.find((album) => String(album.id) === String(inlineAlbumSelection.albumId))
    : null;
  const panelAlbum = routedAlbum || inlineAlbum;
  const routeAlbumMissing = Boolean(albumId && !routedAlbum);

  const handleFilterSelect = (filter) => {
    setActiveFilters((current) => {
      if (current.some((item) => item.id === filter.id)) return current;
      return [...current, filter];
    });
    setInlineAlbumSelection(null);
    navigate(profilePath(selectedUser.slug, PROFILE_ROUTES.library));
  };

  const removeFilter = (filterId) => {
    setActiveFilters((current) => current.filter((filter) => filter.id !== filterId));
  };

  const clearFilters = () => {
    setSearchTerm("");
    setActiveFilters([]);
  };

  const handleOpenAlbum = (album) => {
    if (!album?.id) return;
    setInlineAlbumSelection(null);
    navigate(albumPath(selectedUser.slug, album.id));
  };

  const handleOpenAlbumInline = (album) => {
    if (!album?.id) return;
    setInlineAlbumSelection({
      userSlug: selectedUser.slug,
      albumId: String(album.id),
    });
  };

  const handleAlbumPanelOpenChange = (open) => {
    if (open) return;
    if (albumId) {
      navigate(profilePath(selectedUser.slug, PROFILE_ROUTES.library));
      return;
    }
    setInlineAlbumSelection(null);
  };

  const handleRoutedAlbumUpdated = (album) => {
    if (!album?.id) return;
    loadAlbumState();
  };

  const handleRoutedAlbumDeleted = () => {
    if (albumId) {
      navigate(profilePath(selectedUser.slug, PROFILE_ROUTES.library));
    } else {
      setInlineAlbumSelection(null);
    }
    loadAlbumState();
  };

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch {
      // Local auth state is cleared by signOut even when the request fails.
    }
    setAuthenticatedAccount(null);
    setOwnedProfileSlugs([]);
    navigate("/", { replace: true });
  };

  const handleImport = (source) => {
    setImportDialogSource(source);
    setImportDialogOpen(true);
  };

  const handleConnectSpotify = async () => {
    const authorizeUrl = await spotifyConnectUrl(selectedUser.slug);
    if (authorizeUrl) window.location.assign(authorizeUrl);
  };

  const onboardingActions = isOwner
    ? {
      onAddAlbum: () => setAlbumCreateOpen(true),
      onImport: handleImport,
      onConnectSpotify: handleConnectSpotify,
    }
    : null;

  return (
    <>
      <div className="min-h-screen space-y-10 ">
        <div className="flex flex-col gap-4">
          <Header
            view={view}
            albums={processedAlbums}
            onDataChanged={loadAlbumState}
            selectedUser={selectedUser}
            isOwner={isOwner}
            authenticatedAccount={authenticatedAccount}
            onSignOut={handleSignOut}
            spotifyStatus={
              spotifyStatusUserSlug === selectedUser.slug
                ? spotifyStatus
                : { connected: false }
            }
            onSpotifyStatusChanged={loadSpotifyStatus}
            onSwitchUser={handleSwitchUser}
            importDialogOpen={importDialogOpen}
            onImportDialogOpenChange={setImportDialogOpen}
            albumCreateOpen={albumCreateOpen}
            onAlbumCreateOpenChange={setAlbumCreateOpen}
          />

          {[PROFILE_ROUTES.library, PROFILE_ROUTES.releases].includes(view) && (
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

        {routeAlbumMissing ? (
          <NotFound onBackHome={handleSwitchUser} />
        ) : null}

        {!routeAlbumMissing && view === PROFILE_ROUTES.discovery && (
          <PageDiscovery
            albums={visibleAlbums}
            allAlbums={processedAlbums}
            onFilterSelect={handleFilterSelect}
            onDataChanged={loadAlbumState}
            onOpenAlbum={handleOpenAlbum}
            syncSortWithUrl
            {...onboardingActions}
          />
        )}
        {!routeAlbumMissing && view === PROFILE_ROUTES.library && (
          processedAlbums.length === 0 && isOwner ? (
            <EmptyLibraryState view="library" {...onboardingActions} />
          ) : (
            <AlbumTable
              key={visibleAlbums.map((album) => album.id).join(",")}
              albums={filteredAlbums}
              searchTerm={searchTerm}
              onFilterSelect={handleFilterSelect}
              onDataChanged={loadAlbumState}
              onOpenAlbum={handleOpenAlbum}
            />
          )
        )}
        {!routeAlbumMissing && view === PROFILE_ROUTES.releases && (
          processedAlbums.length === 0 && isOwner ? (
            <EmptyLibraryState view="releases" {...onboardingActions} />
          ) : (
            <AlbumTimeView
              albums={filteredAlbums}
              onFilterSelect={handleFilterSelect}
              onDataChanged={loadAlbumState}
              onOpenAlbum={handleOpenAlbum}
            />
          )
        )}
        {!routeAlbumMissing && view === PROFILE_ROUTES.connections && (
          <PageConnections
            albums={processedAlbums}
            selectedUser={selectedUser}
            onOpenAlbum={handleOpenAlbumInline}
          />
        )}
      </div>
      <Toaster />
      <ImportHistoryDialog
        selectedUser={selectedUser}
        albums={processedAlbums}
        onDataChanged={loadAlbumState}
        open={isOwner && importDialogOpen}
        onOpenChange={setImportDialogOpen}
        hideTrigger
        initialSource={importDialogSource}
      />
      <AlbumPanelSheet
        open={Boolean(panelAlbum)}
        onOpenChange={handleAlbumPanelOpenChange}
        album={panelAlbum}
        searchTerm={searchTerm}
        onFilterSelect={handleFilterSelect}
        onAlbumUpdated={handleRoutedAlbumUpdated}
        onAlbumDeleted={handleRoutedAlbumDeleted}
        onDataChanged={loadAlbumState}
        isOwner={isOwner}
      />
    </>
  );
}

function AppNotFound() {
  const navigate = useNavigate();
  useDocumentMetadata({
    title: "Page not found | Albumary",
    description: "The Albumary page you requested is unavailable.",
  });
  return <NotFound onBackHome={() => navigate("/")} />;
}

function GoogleAuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const authError = searchParams.get("auth_error");
  useEffect(() => {
    async function completeSignIn() {
      if (authError) {
        navigate(`/?auth_error=${encodeURIComponent(authError)}`, { replace: true });
        return;
      }
      try {
        storeGoogleSessionFromFragment();
        const account = await fetchCurrentAccount();
        const profileSlugs = account.profile_slugs || [];
        const destination = profileSlugs.length === 0
          ? "/?create_profile=1"
          : profileSlugs.length === 1
            ? profilePath(profileSlugs[0], PROFILE_ROUTES.discovery)
            : "/?ownership_error=multiple_profiles";
        navigate(destination, { replace: true });
      } catch {
        navigate("/?auth_error=sign_in_failed", { replace: true });
      }
    }
    completeSignIn();
  }, [authError, navigate]);
  return <LoadingState />;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRoute />} />
      <Route path="/auth/callback" element={<GoogleAuthCallback />} />
      <Route path="/:userSlug" element={<ProfileIndexRedirect />} />
      <Route path="/:userSlug/albums" element={<LegacyRedirect legacySection="albums" />} />
      <Route path="/:userSlug/timeline" element={<LegacyRedirect legacySection="timeline" />} />
      <Route path="/:userSlug/discovery" element={<UserRoute view={PROFILE_ROUTES.discovery} />} />
      <Route path="/:userSlug/library" element={<UserRoute view={PROFILE_ROUTES.library} />} />
      <Route path="/:userSlug/releases" element={<UserRoute view={PROFILE_ROUTES.releases} />} />
      <Route path="/:userSlug/connections" element={<UserRoute view={PROFILE_ROUTES.connections} />} />
      <Route
        path="/:userSlug/albums/:albumId"
        element={<UserRoute view={PROFILE_ROUTES.library} />}
      />
      <Route path="*" element={<AppNotFound />} />
    </Routes>
  );
}

export default App;
