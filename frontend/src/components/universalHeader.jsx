import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import AlbumCreateDialog from "./AlbumCreateDialog";
import { disconnectSpotify, spotifyConnectUrl, syncSpotifyNow } from "../services/albumApi";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart3,
  CalendarDays,
  Library,
  Network,
  Table2,
} from "lucide-react";
import { PROFILE_ROUTES, profilePath } from "@/routing";

const NAV_ITEMS = [
  {
    value: PROFILE_ROUTES.discovery,
    label: "Discovery",
    description: "Recent patterns",
    icon: BarChart3,
    accent: "data-active:bg-chart-1/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
  {
    value: PROFILE_ROUTES.library,
    label: "Library",
    description: "All albums",
    icon: Table2,
    accent: "data-active:bg-chart-2/20 data-active:text-foreground",
    iconAccent: "text-chart-2",
  },
  {
    value: PROFILE_ROUTES.releases,
    label: "Release Dates",
    description: "Years and decades",
    icon: CalendarDays,
    accent: "data-active:bg-chart-3/20 data-active:text-foreground",
    iconAccent: "text-chart-3",
  },
  {
    value: PROFILE_ROUTES.connections,
    label: "Connections",
    description: "Shared credits",
    icon: Network,
    accent: "data-active:bg-primary/15 data-active:text-foreground",
    iconAccent: "text-primary",
  },
];

function UniversalHeader({
  view,
  albums,
  onDataChanged,
  selectedUser,
  isOwner = false,
  spotifyStatus,
  onSpotifyStatusChanged,
  onSwitchUser,
  importDialogOpen,
  onImportDialogOpenChange,
}) {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [isSyncing, setIsSyncing] = useState(false);
  const handleConnectSpotify = async () => {
    const url = await spotifyConnectUrl(selectedUser?.slug);
    if (url) window.location.href = url;
  };

  const handleSyncNow = async () => {
    setIsSyncing(true);
    try {
      await syncSpotifyNow(selectedUser?.slug);
      await onSpotifyStatusChanged?.();
      await onDataChanged?.();
      toast({
        title: "Sync Complete",
        description: "Your Spotify data has been synchronized successfully.",
      });
    } catch (error) {
      toast({
        title: "Sync Failed",
        description: error.message || "An error occurred while syncing.",
        variant: "destructive",
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDisconnectSpotify = async () => {
    try {
      await disconnectSpotify(selectedUser?.slug);
      await onSpotifyStatusChanged?.();
      toast({ title: "Spotify disconnected" });
    } catch (error) {
      toast({
        title: "Could not disconnect Spotify",
        description: error.message || "An error occurred while disconnecting.",
        variant: "destructive",
      });
    }
  };

  return (
    <header className="sticky top-0 z-30 border-b border-primary/20 bg-muted backdrop-blur">
      <div className="px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center justify-between gap-4">
            <button
              type="button"
              onClick={onSwitchUser}
              className="-mx-2 -my-1 flex items-center gap-3 rounded-md px-2 py-1 text-left transition-colors hover:bg-primary/10 hover:text-primary active:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-muted"
              aria-label="Go to Albumary splash page"
            >
              <div className="flex size-11 items-center justify-center rounded-md border border-primary/20 bg-primary/30 text-primary shadow-sm">
                <Library className="size-5" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-foreground">
                  Albumary
                </h1>
                <p className="text-xs text-muted-foreground">
                  Album listening history
                </p>
              </div>
            </button>

            {isOwner && (
              <AlbumCreateDialog
                albums={albums}
                onDataChanged={onDataChanged}
                variant="outline"
                triggerClassName="border-primary/20 bg-primary/10 text-primary hover:bg-primary/15 xl:hidden"
              />
            )}
          </div>

          <Tabs
            value={view}
            onValueChange={(nextView) => {
              if (!selectedUser?.slug) return;
              navigate(profilePath(selectedUser.slug, nextView));
            }}
            className="w-full min-w-0 xl:flex-1 xl:items-center"
          >
            <TabsList className="grid !h-auto w-full grid-cols-2 items-stretch gap-2 overflow-hidden rounded-md border border-primary/15 bg-background/75 p-2 shadow-sm sm:grid-cols-3 xl:grid-cols-4">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <TabsTrigger
                    key={item.value}
                    value={item.value}
                    className={`h-auto min-w-0 self-stretch justify-start gap-2 rounded-md px-2.5 py-3.5 hover:bg-muted/70 after:hidden ${item.accent}`}
                  >
                    <Icon className={`size-4 ${item.iconAccent}`} />
                    <span className="flex min-w-0 flex-col items-start leading-snug">
                      <span className="w-full truncate text-sm font-medium">{item.label}</span>
                      <span className="w-full truncate text-[11px] font-normal text-muted-foreground">
                        {item.description}
                      </span>
                    </span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>

          <div className="hidden items-center gap-2 xl:flex">
            <div className="mr-2 flex flex-col items-end text-xs">
              <span className="font-medium text-foreground">
                {selectedUser?.display_name}
              </span>
              <button
                type="button"
                onClick={onSwitchUser}
                className="text-muted-foreground hover:text-foreground"
              >
                Switch user
              </button>
            </div>
            {isOwner ? (
              <>
                <Button variant="outline" onClick={() => onImportDialogOpenChange?.(!importDialogOpen)}>
                  Import History
                </Button>
                {spotifyStatus?.connected ? (
                  <>
                    <Button variant="outline" onClick={handleSyncNow} disabled={isSyncing}>
                      {isSyncing ? "Syncing..." : "Sync Spotify"}
                    </Button>
                    <Button variant="outline" onClick={handleDisconnectSpotify}>Disconnect Spotify</Button>
                  </>
                ) : (
                  <Button variant="outline" onClick={handleConnectSpotify}>
                    Connect Spotify
                  </Button>
                )}
                <AlbumCreateDialog
                  albums={albums}
                  onDataChanged={onDataChanged}
                  triggerClassName="bg-primary text-primary-foreground hover:bg-primary/85"
                />
              </>
            ) : (
              <span className="text-xs text-muted-foreground">Public profile · read-only</span>
            )}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 xl:hidden">
          <span className="text-sm font-medium text-foreground">
            {selectedUser?.display_name}
          </span>
          <Button variant="outline" size="sm" onClick={onSwitchUser}>
            Switch user
          </Button>
          {isOwner ? (
            <>
              <Button variant="outline" size="sm" onClick={() => onImportDialogOpenChange?.(!importDialogOpen)}>
                Import History
              </Button>
              {spotifyStatus?.connected ? (
                <>
                  <Button variant="outline" size="sm" onClick={handleSyncNow} disabled={isSyncing}>
                    {isSyncing ? "Syncing..." : "Sync Spotify"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleDisconnectSpotify}>Disconnect Spotify</Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={handleConnectSpotify}>
                  Connect Spotify
                </Button>
              )}
            </>
          ) : (
            <span className="text-xs text-muted-foreground">Public profile · read-only</span>
          )}
        </div>
      </div>
    </header>
  );
}

export default UniversalHeader;
