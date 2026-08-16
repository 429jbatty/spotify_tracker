import { Disc3, FileArchive, Radio, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";

const IMPORT_ACTIONS = [
  { id: "lastfm", label: "Import Last.fm", description: "Bring in completed album listens.", icon: <Radio className="size-5 text-primary" aria-hidden="true" /> },
  { id: "spotify_import", label: "Upload Spotify ZIP", description: "Use Spotify Extended Streaming History.", icon: <Upload className="size-5 text-primary" aria-hidden="true" /> },
];

export default function EmptyLibraryState({
  view = "library",
  onAddAlbum,
  onImport,
  onConnectSpotify,
}) {
  const isDiscovery = view === "discovery";

  return (
    <section className="mx-6 rounded-xl border border-dashed border-primary/35 bg-primary/5 p-6 sm:p-8">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Your listening story starts here</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {isDiscovery ? "Turn album listens into a map of your taste." : "Your library is ready for its first album."}
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Add one album now, import listening history, or connect Spotify. After listens arrive, Albumary will show discoveries, replays, release eras, and collaborator connections.
        </p>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <ActionCard icon={<Disc3 className="size-5 text-primary" aria-hidden="true" />} label="Add your first album" description="Log an album you listened to." onClick={onAddAlbum} primary />
        {IMPORT_ACTIONS.map((action) => (
          <ActionCard key={action.id} {...action} onClick={() => onImport?.(action.id)} />
        ))}
        <ActionCard icon={<FileArchive className="size-5 text-primary" aria-hidden="true" />} label="Connect Spotify" description="Sync future listens from Spotify." onClick={onConnectSpotify} />
      </div>
    </section>
  );
}

function ActionCard({ icon, label, description, onClick, primary = false }) {
  return (
    <div className="rounded-lg border border-border/80 bg-card p-4 shadow-sm">
      {icon}
      <h2 className="mt-3 font-semibold text-foreground">{label}</h2>
      <p className="mt-1 min-h-10 text-sm leading-5 text-muted-foreground">{description}</p>
      <Button type="button" className="mt-4 w-full" variant={primary ? "default" : "outline"} onClick={onClick}>
        {label}
      </Button>
    </div>
  );
}
