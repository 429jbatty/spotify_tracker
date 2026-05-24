import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import AlbumCreateDialog from "./AlbumCreateDialog";
import { spotifyConnectUrl, syncSpotifyNow } from "../services/albumApi";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";
import {
  BarChart3,
  CalendarDays,
  Library,
  ShieldCheck,
  Table2,
} from "lucide-react";

const NAV_ITEMS = [
  {
    value: "discovery",
    label: "Discovery",
    description: "Recent patterns",
    icon: BarChart3,
    accent: "data-active:bg-chart-1/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
  {
    value: "table",
    label: "Library",
    description: "All albums",
    icon: Table2,
    accent: "data-active:bg-chart-2/20 data-active:text-foreground",
    iconAccent: "text-chart-2",
  },
  {
    value: "timeline",
    label: "Release Dates",
    description: "Years and decades",
    icon: CalendarDays,
    accent: "data-active:bg-chart-3/20 data-active:text-foreground",
    iconAccent: "text-chart-3",
  },
  {
    value: "quality",
    label: "Data Quality",
    description: "Metadata cleanup",
    icon: ShieldCheck,
    accent: "data-active:bg-chart-4/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
];

function UniversalHeader({
  view,
  setView,
  albums,
  onDataChanged,
  selectedUser,
  spotifyStatus,
  onSpotifyStatusChanged,
  onSwitchUser,
  importDialogOpen,
  onImportDialogOpenChange,
}) {
  const { toast } = useToast();
  const [isSyncing, setIsSyncing] = useState(false);
  const handleConnectSpotify = () => {
    const url = spotifyConnectUrl(selectedUser?.slug);
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

  return (
    <header className="sticky top-0 z-30 border-b border-primary/20 bg-muted backdrop-blur">
      <div className="px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
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
            </div>

            <AlbumCreateDialog
              albums={albums}
              onDataChanged={onDataChanged}
              variant="outline"
              triggerClassName="border-primary/20 bg-primary/10 text-primary hover:bg-primary/15 xl:hidden"
            />
          </div>

          <Tabs
            value={view}
            onValueChange={setView}
            className="min-w-0 w-full xl:flex-1 xl:items-center"
          >
            <TabsList className="!h-auto w-full flex-wrap items-stretch justify-center gap-2 overflow-hidden rounded-md border border-primary/15 bg-background/75 p-2 shadow-sm">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <TabsTrigger
                    key={item.value}
                    value={item.value}
                    className={`h-auto min-w-[11.25rem] flex-none self-stretch justify-start gap-3 rounded-md px-4 py-3.5 hover:bg-muted/70 after:hidden ${item.accent}`}
                  >
                    <Icon className={`size-4 ${item.iconAccent}`} />
                    <span className="flex flex-col items-start leading-snug">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className="text-[11px] font-normal text-muted-foreground">
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
            <Button
              variant="outline"
              onClick={() => onImportDialogOpenChange?.(!importDialogOpen)}
            >
              Import History
            </Button>
            {spotifyStatus?.connected ? (
              <Button variant="outline" onClick={handleSyncNow} disabled={isSyncing}>
                {isSyncing ? "Syncing..." : "Sync Spotify"}
              </Button>
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
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 xl:hidden">
          <span className="text-sm font-medium text-foreground">
            {selectedUser?.display_name}
          </span>
          <Button variant="outline" size="sm" onClick={onSwitchUser}>
            Switch user
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onImportDialogOpenChange?.(!importDialogOpen)}
          >
            Import History
          </Button>
          {spotifyStatus?.connected ? (
            <Button variant="outline" size="sm" onClick={handleSyncNow} disabled={isSyncing}>
              {isSyncing ? "Syncing..." : "Sync Spotify"}
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={handleConnectSpotify}>
              Connect Spotify
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}

export default UniversalHeader;
