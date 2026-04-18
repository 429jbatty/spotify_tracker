import { useState } from "react";
import AlbumRow from "./AlbumRow";
import {
  Sheet,
  SheetContent,
} from "@/components/ui/sheet";

import AlbumSidePanel from "./AlbumSidePanel"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function AlbumTable({ albums, onFilterSelect }) {
  const [sortBy, setSortBy] = useState("listen_history");
  const [ascending, setAscending] = useState(false);
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);

  
  const albumArray = Object.entries(albums).map(([id, data]) => ({
    id,
    ...data,
  }));

  const sortedAlbums = albumArray.sort((a, b) => {
    let aValue = a[sortBy];
    let bValue = b[sortBy];

    if (aValue === null || aValue === undefined) return 1;
    if (bValue === null || bValue === undefined) return -1;

    if (typeof aValue === "number") {
      return ascending ? aValue - bValue : bValue - aValue;
    }

    if (sortBy === "latestListen") {
      return ascending
        ? new Date(aValue) - new Date(bValue)
        : new Date(bValue) - new Date(aValue);
    }

    return ascending
      ? String(aValue).localeCompare(String(aValue))
      : String(bValue).localeCompare(String(aValue));
  });

  const handleSort = (key) => {
    if (sortBy === key) setAscending(!ascending);
    else {
      setSortBy(key);
      setAscending(true);
    }
  };

  const handleRowClick = (album) => {
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const headers = [
    { key: "image_url", label: "", sortable: false, width: "w-[100px]" },
    { key: "name", label: "Album", sortable: true, width: "w-[37%]" },
    { key: "artist", label: "Artist", sortable: true, width: "w-[20%]" },
    { key: "release_year", label: "Year", sortable: true, width: "w-[10%]" },
    { key: "label", label: "Label", sortable: true, width: "w-[15%]" },
    { key: "totalListens", label: "Listens", sortable: true, width: "w-[8%]" },
    { key: "latestListen", label: "Last listen", sortable: true, width: "w-[10%]" },
  ];

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table className="w-full table-fixed bg-card">
          <TableHeader className="bg-muted">
            <TableRow>
              {headers.map((header) => (
                <TableHead
                  key={header.key}
                  className={`py-2 text-left text-sm font-medium select-none text-foreground ${header.sortable ? "cursor-pointer" : ""} ${header.width}`}
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

          <TableBody className="bg-primary-foreground">
            {sortedAlbums.map((album) => (
              <AlbumRow
                key={album.id}
                albumId={album.id}
                album={album}
                onRowClick={() => handleRowClick(album)}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent
          side="right"
          className="w-[650px] sm:w-[750px] overflow-y-auto p-6"
        >
          {selectedAlbum && (
            <AlbumSidePanel album={selectedAlbum} onFilterSelect={onFilterSelect} />
          )}
        </SheetContent>
      </Sheet>

    </>
  );
}

export default AlbumTable;
