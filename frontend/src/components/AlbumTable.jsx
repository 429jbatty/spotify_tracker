import { useState } from "react";
import AlbumRow from "./AlbumRow";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function AlbumTable({ albums }) {
  const [sortBy, setSortBy] = useState("listen_history");
  const [ascending, setAscending] = useState(false);

  const sortedAlbums = Object.entries(albums)
    .map(([id, data]) => ({ id, ...data }))
    .sort((a, b) => {
      const aValue = a[sortBy];
      const bValue = b[sortBy];

      if (!isNaN(Date.parse(aValue))) {
        return ascending
          ? new Date(aValue) - new Date(bValue)
          : new Date(bValue) - new Date(aValue);
      }

      if (typeof aValue === "number") {
        return ascending ? aValue - bValue : bValue - aValue;
      }

      return ascending
        ? String(aValue).localeCompare(String(bValue))
        : String(bValue).localeCompare(String(aValue));
    });

  const handleSort = (key) => {
    if (sortBy === key) setAscending(!ascending);
    else {
      setSortBy(key);
      setAscending(true);
    }
  };

  const headers = [
    { key: "image_url", label: "", sortable: false },
    { key: "name", label: "Album", sortable: true },
    { key: "artist", label: "Artist", sortable: true },
    { key: "release_date", label: "Release Date", sortable: true },
    { key: "label", label: "Label", sortable: true },
  ];

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table className="w-full">
        <TableHeader className="bg-muted">
          <TableRow>
            {headers.map((header) => (
              <TableHead
                key={header.key}
                className={`px-4 py-2 text-left text-sm font-medium select-none ${
                  header.sortable ? "cursor-pointer" : ""
                }`}
                onClick={header.sortable ? () => handleSort(header.key) : undefined}
              >
                {header.label}{" "}
                {header.sortable && sortBy === header.key
                  ? ascending
                    ? "▲"
                    : "▼"
                  : ""}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedAlbums.map((album) => (
            <AlbumRow key={album.id} albumId={album.id} album={album} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default AlbumTable;