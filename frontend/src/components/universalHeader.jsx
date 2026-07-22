import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart3, CalendarDays, CheckCircle2, Network, Table2 } from "lucide-react";

import SiteHeader from "@/components/SiteHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AlbumCreateDialog from "./AlbumCreateDialog";
import { useToast } from "@/hooks/use-toast";
import { disconnectSpotify, spotifyConnectUrl, syncSpotifyNow } from "../services/albumApi";
import { PROFILE_ROUTES, profilePath } from "@/routing";

const NAV_ITEMS = [
  [PROFILE_ROUTES.discovery, "Discovery", "Recent patterns", BarChart3],
  [PROFILE_ROUTES.library, "Library", "All albums", Table2],
  [PROFILE_ROUTES.releases, "Release Dates", "Years and decades", CalendarDays],
  [PROFILE_ROUTES.connections, "Connections", "Shared credits", Network],
];

function UniversalHeader({ view, albums, onDataChanged, selectedUser, isOwner = false, authenticatedAccount, spotifyStatus, onSpotifyStatusChanged, onSwitchUser, importDialogOpen, onImportDialogOpenChange }) {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [isSyncing, setIsSyncing] = useState(false);
  const profileSlug = selectedUser?.slug;

  const connectSpotify = async () => {
    const url = await spotifyConnectUrl(profileSlug);
    if (url) window.location.href = url;
  };
  const syncNow = async () => {
    setIsSyncing(true);
    try {
      await syncSpotifyNow(profileSlug);
      await onSpotifyStatusChanged?.();
      await onDataChanged?.();
      toast({ title: "Sync Complete", description: "Your Spotify data has been synchronized successfully." });
    } catch (error) {
      toast({ title: "Sync Failed", description: error.message || "An error occurred while syncing.", variant: "destructive" });
    } finally { setIsSyncing(false); }
  };
  const disconnect = async () => {
    try {
      await disconnectSpotify(profileSlug);
      await onSpotifyStatusChanged?.();
      toast({ title: "Spotify disconnected" });
    } catch (error) {
      toast({ title: "Could not disconnect Spotify", description: error.message || "An error occurred while disconnecting.", variant: "destructive" });
    }
  };

  return <SiteHeader context={selectedUser?.display_name ? `${selectedUser.display_name}'s listening history` : null} onBrowseProfiles={onSwitchUser} authenticatedAccount={authenticatedAccount}>
    <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-3 sm:px-6 lg:px-8 xl:flex-row xl:items-center xl:justify-between">
      <Tabs value={view} onValueChange={(nextView) => profileSlug && navigate(profilePath(profileSlug, nextView))} className="min-w-0 xl:flex-1">
        <TabsList className="grid !h-auto w-full grid-cols-2 gap-1 rounded-md bg-background/80 p-1 sm:grid-cols-4 xl:max-w-2xl">
          {NAV_ITEMS.map(([value, label, description, Icon]) => {
            const NavigationIcon = Icon;
            return <TabsTrigger key={value} value={value} className="h-auto min-w-0 justify-start gap-2 px-2.5 py-2.5 data-active:bg-primary/10 data-active:text-foreground">
              <NavigationIcon className="size-4 text-primary" /><span className="flex min-w-0 flex-col items-start"><span className="w-full truncate text-sm font-medium">{label}</span><span className="hidden w-full truncate text-[11px] font-normal text-muted-foreground sm:block">{description}</span></span>
            </TabsTrigger>;
          })}
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap items-center gap-2 xl:justify-end">
        <AccessBadge isOwner={isOwner} authenticatedAccount={authenticatedAccount} />
        {isOwner && <OwnerActions albums={albums} onDataChanged={onDataChanged} spotifyStatus={spotifyStatus} isSyncing={isSyncing} importDialogOpen={importDialogOpen} onImportDialogOpenChange={onImportDialogOpenChange} onConnect={connectSpotify} onSync={syncNow} onDisconnect={disconnect} />}
      </div>
    </div>
  </SiteHeader>;
}

function AccessBadge({ isOwner, authenticatedAccount }) {
  if (isOwner) return <Badge className="gap-1 border-emerald-500/30 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300" variant="outline"><CheckCircle2 className="size-3" /> Owner view</Badge>;
  if (authenticatedAccount) return <Badge variant="secondary">Public profile</Badge>;
  return <Badge variant="secondary">Public profile</Badge>;
}

function OwnerActions({ albums, onDataChanged, spotifyStatus, isSyncing, importDialogOpen, onImportDialogOpenChange, onConnect, onSync, onDisconnect }) {
  return <>
    <Button variant="outline" size="sm" onClick={() => onImportDialogOpenChange?.(!importDialogOpen)}>Import</Button>
    {spotifyStatus?.connected ? <><Button variant="outline" size="sm" onClick={onSync} disabled={isSyncing}>{isSyncing ? "Syncing..." : "Sync Spotify"}</Button><Button variant="outline" size="sm" onClick={onDisconnect}>Disconnect</Button></> : <Button variant="outline" size="sm" onClick={onConnect}>Connect Spotify</Button>}
    <AlbumCreateDialog albums={albums} onDataChanged={onDataChanged} triggerClassName="bg-primary text-primary-foreground hover:bg-primary/85" />
  </>;
}

export default UniversalHeader;
