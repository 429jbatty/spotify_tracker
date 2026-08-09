import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import AlbumCreateDialog from "./AlbumCreateDialog";
import { disconnectSpotify, spotifyConnectUrl, syncSpotifyNow } from "../services/albumApi";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { DropdownMenu } from "radix-ui";
import {
  BarChart3,
  CalendarDays,
  Ellipsis,
  Library,
  Network,
  Table2,
  UserRound,
} from "lucide-react";
import { PROFILE_ROUTES, profilePath } from "@/routing";
import { accountProfileLabel } from "./utils/accountProfileLabel";

const NAV_ITEMS = [
  {
    value: PROFILE_ROUTES.discovery,
    label: "Discovery",
    icon: BarChart3,
    accent: "data-active:bg-chart-1/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
  {
    value: PROFILE_ROUTES.library,
    label: "Library",
    icon: Table2,
    accent: "data-active:bg-chart-2/20 data-active:text-foreground",
    iconAccent: "text-chart-2",
  },
  {
    value: PROFILE_ROUTES.releases,
    label: "Release Dates",
    icon: CalendarDays,
    accent: "data-active:bg-chart-3/20 data-active:text-foreground",
    iconAccent: "text-chart-3",
  },
  {
    value: PROFILE_ROUTES.connections,
    label: "Connections",
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
  authenticatedAccount = null,
  onSignOut,
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
      <div className="px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center gap-2 xl:flex-nowrap xl:gap-4">
          <div className="min-w-0 shrink-0">
            <button
              type="button"
              onClick={onSwitchUser}
              className="-mx-1 -my-1 flex items-center gap-2 rounded-md px-1 py-1 text-left transition-colors hover:bg-primary/10 hover:text-primary active:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-muted"
              aria-label="Go to Albumary splash page"
            >
              <div className="flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/30 text-primary shadow-sm">
                <Library className="size-5" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-foreground">
                  Albumary
                </h1>
                <p className="hidden text-xs text-muted-foreground 2xl:block">
                  {selectedUser?.display_name ? `${selectedUser.display_name}'s listening history` : "Album listening history"}
                </p>
              </div>
            </button>
          </div>

          <Tabs
            value={view}
            onValueChange={(nextView) => {
              if (!selectedUser?.slug) return;
              navigate(profilePath(selectedUser.slug, nextView));
            }}
            className="order-last w-full min-w-0 xl:order-none xl:flex-1"
          >
            <TabsList className="flex !h-9 w-full items-center gap-1 overflow-x-auto rounded-md border border-primary/15 bg-background/75 p-1 shadow-sm">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <TabsTrigger
                    key={item.value}
                    value={item.value}
                    className={`h-7 shrink-0 justify-center gap-1.5 rounded px-2.5 text-xs hover:bg-muted/70 after:hidden sm:px-3 sm:text-sm ${item.accent}`}
                  >
                    <Icon className={`size-4 ${item.iconAccent}`} />
                    <span className="truncate font-medium">{item.label}</span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>

          <div className="flex shrink-0 items-center gap-1">
            {isOwner && (
              <AlbumCreateDialog
                albums={albums}
                onDataChanged={onDataChanged}
                triggerClassName="bg-primary text-primary-foreground hover:bg-primary/85"
              />
            )}
            <ProfileToolsMenu
              isOwner={isOwner}
              importDialogOpen={importDialogOpen}
              onImportDialogOpenChange={onImportDialogOpenChange}
              spotifyStatus={spotifyStatus}
              isSyncing={isSyncing}
              onConnectSpotify={handleConnectSpotify}
              onDisconnectSpotify={handleDisconnectSpotify}
              onSyncSpotify={handleSyncNow}
            />
            <AccountMenu
              account={authenticatedAccount}
              onBrowseProfiles={onSwitchUser}
              onSignOut={onSignOut}
            />
          </div>
        </div>
      </div>
    </header>
  );
}

function AccountMenu({ account, onBrowseProfiles, onSignOut }) {
  if (!account) return null;
  const profileLabel = accountProfileLabel(account);

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Open account menu">
          <UserRound />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 min-w-56 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg outline-none"
        >
          <div className="px-2 py-1.5 text-xs text-muted-foreground">Signed in as</div>
          <div className="max-w-52 truncate px-2 text-sm font-medium">{profileLabel}</div>
          <div className="max-w-52 truncate px-2 pb-2 text-xs text-muted-foreground">{account.email}</div>
          <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border" />
          <MenuItem onSelect={onBrowseProfiles}>Browse profiles</MenuItem>
          <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border" />
          <MenuItem onSelect={onSignOut} destructive>Sign out</MenuItem>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function ProfileToolsMenu({
  isOwner,
  importDialogOpen,
  onImportDialogOpenChange,
  spotifyStatus,
  isSyncing,
  onConnectSpotify,
  onDisconnectSpotify,
  onSyncSpotify,
}) {
  if (!isOwner) return null;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Open profile tools">
          <Ellipsis />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 min-w-48 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg outline-none"
        >
          <MenuItem onSelect={() => onImportDialogOpenChange?.(!importDialogOpen)}>
            Import history
          </MenuItem>
          <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border" />
          {spotifyStatus?.connected ? (
            <>
              <MenuItem onSelect={onSyncSpotify} disabled={isSyncing}>
                {isSyncing ? "Syncing Spotify…" : "Sync Spotify"}
              </MenuItem>
              <MenuItem onSelect={onDisconnectSpotify}>Disconnect Spotify</MenuItem>
            </>
          ) : (
            <MenuItem onSelect={onConnectSpotify}>Connect Spotify</MenuItem>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function MenuItem({ children, destructive = false, ...props }) {
  return (
    <DropdownMenu.Item
      className={`flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-muted data-[disabled]:pointer-events-none data-[disabled]:opacity-50 ${
        destructive ? "text-destructive data-[highlighted]:bg-destructive/10" : ""
      }`}
      {...props}
    >
      {children}
    </DropdownMenu.Item>
  );
}

export default UniversalHeader;
