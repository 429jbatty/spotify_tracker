import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

function AlbumBubble({ album }) {
  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        <div className="h-16 w-16 overflow-hidden rounded-md shadow cursor-pointer hover:scale-105 transition">
          <img
            src={album.image_url}
            alt={album.name}
            className="h-full w-full object-cover"
          />
        </div>
      </HoverCardTrigger>

      <HoverCardContent className="w-64">
        <div className="flex gap-4">
          <img
            src={album.image_url}
            alt={album.name}
            className="h-16 w-16 rounded"
          />

          <div>
            <div className="font-semibold">{album.name}</div>
            <div className="text-sm text-muted-foreground">
              {album.artist}
            </div>
            <div className="text-xs text-muted-foreground">
              {album.release_year}
            </div>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

export default AlbumBubble;