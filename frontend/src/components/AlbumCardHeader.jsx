import { CardTitle } from "@/components/ui/card";

function AlbumHeader({ album }) {
  return (
    <div className="p-6 flex flex-col items-center gap-1 text-center">
      <CardTitle className="line-clamp-2 text-xl font-bold text-foreground">
        {album.name}
      </CardTitle>
      <p className="text-sm font-medium text-foreground/70 line-clamp-1">
        {album.artist}
      </p>
    </div>
  );
}

export default AlbumHeader;