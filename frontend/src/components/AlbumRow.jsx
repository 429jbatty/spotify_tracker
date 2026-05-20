import { TableRow, TableCell } from "@/components/ui/table";

function AlbumRow({ albumId, album, onRowClick }) {
  const BASE = import.meta.env.BASE_URL;

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
      <TableCell className="py-3 w-[100px]">
        <div className="relative overflow-hidden rounded-md border border-border w-12 h-12 bg-card shadow-sm">
          <img
            loading="lazy"
            src={album.image_url || `${BASE}placeholder_art.png`}
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = `${BASE}placeholder_art.png`;
            }}
            className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-125"
            alt={album.name}
          />
        </div>
      </TableCell>

      <TableCell
        className="text-left text-foreground font-medium truncate max-w-0"
        title={album.name}
      >
        {album.name}
      </TableCell>

      <TableCell className="text-foreground/70 truncate max-w-0">
        {album.artist}
      </TableCell>

      <TableCell className="text-foreground/60">
        {album.release_year || "Unknown"}
      </TableCell>

      <TableCell className="text-foreground/60 truncate max-w-0">
        {album.label}
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
