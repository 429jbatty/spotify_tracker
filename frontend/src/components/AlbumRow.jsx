import { TableRow, TableCell } from "@/components/ui/table";
import AlbumSearchMatches from "./search/AlbumSearchMatches";
import ResponsiveAlbumImage from "./ResponsiveAlbumImage";
import { getSourceLabel } from "./utils/sourceLabels";

function AlbumRow({ albumId, album, onRowClick }) {
  const formatDate = (isoString) => {
    if (!isoString) return "Unknown";
    const date = new Date(isoString);
    const m = String(date.getMonth() + 1);
    const dd = String(date.getDate()).padStart(2, "0");
    const yyyy = date.getFullYear();
    return `${m}/${dd}/${yyyy}`;
  };

  return (
    <TableRow
      key={albumId}
      onClick={onRowClick}
      className="group transition-colors duration-200 hover:bg-muted cursor-pointer border-b border-border"
    >
      <TableCell className="py-3 w-[72px]">
        <div className="relative overflow-hidden rounded-md border border-border w-12 h-12 bg-card shadow-sm">
          <ResponsiveAlbumImage
            src={album.image_url}
            sizes="48px"
            className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-125"
            alt={album.name}
          />
        </div>
      </TableCell>

      <TableCell className="max-w-0 text-left text-foreground">
        <div className="min-w-0">
          <div className="truncate font-medium" title={album.name}>
            {album.name}
          </div>
          <AlbumSearchMatches matches={album.searchMatches} />
        </div>
      </TableCell>

      <TableCell className="text-foreground/70 truncate max-w-0">
        {album.artist}
      </TableCell>

      <TableCell className="text-foreground/60">
        {album.release_year || "Unknown"}
      </TableCell>

      <TableCell className="text-foreground/60 truncate max-w-0">
        {album.label || "Unknown"}
      </TableCell>

      <TableCell className="text-foreground/60 truncate max-w-0">
        {getSourceLabel(album.entry_source || album.source)}
      </TableCell>

      <TableCell className="text-foreground/60">
        {album.totalListens}
      </TableCell>

      <TableCell className="text-foreground/60 whitespace-nowrap">
        {formatDate(album.latestListen)}
      </TableCell>
    </TableRow>
  );
}

export default AlbumRow;
