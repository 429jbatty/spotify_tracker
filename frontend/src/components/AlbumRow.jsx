import { TableRow, TableCell } from "@/components/ui/table";

function AlbumRow({ albumId, album }) {
  const BASE = import.meta.env.BASE_URL;

  return (
    <TableRow key={albumId} className="hover:bg-muted">
      <TableCell>
        <img
          loading="lazy"
          src={album.image_url || `${BASE}placeholder_art.png`}
          onError={(e) => {
            e.target.onerror = null;
            e.target.src = `${BASE}placeholder_art.png`;
          }}
          style={{ width: "50px", height: "50px", objectFit: "cover", borderRadius: "4px", }}
          className="w-12 h-12 object-cover rounded"
          alt={album.name}
        />
      </TableCell>
      <TableCell>{album.name}</TableCell>
      <TableCell>{album.artist}</TableCell>
      <TableCell>{album.release_date}</TableCell>
      <TableCell>{album.label}</TableCell>
    </TableRow>
  );
}

export default AlbumRow;