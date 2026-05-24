import { useMemo, useState } from "react";
import AlbumColumnFilter from "./AlbumColumnFilter";
import AlbumRow from "./AlbumRow";
import AlbumPanelSheet from "./AlbumPanelSheet";
import { getSourceLabel } from "./utils/sourceLabels";
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const TABLE_HEADERS = [
  { key: "image_url", label: "", sortable: false, filterable: false, width: "w-[72px]" },
  { key: "name", label: "Album", sortable: true, filterable: true, width: "w-[24%]" },
  { key: "artist", label: "Artist", sortable: true, filterable: true, width: "w-[16%]" },
  { key: "release_year", label: "Release year", sortable: true, filterable: true, width: "w-[10%]" },
  { key: "label", label: "Label", sortable: true, filterable: true, width: "w-[14%]" },
  { key: "entry_source", label: "Source", sortable: true, filterable: true, width: "w-[12%]" },
  { key: "totalListens", label: "Listens", sortable: true, filterable: true, width: "w-[8%]" },
  { key: "latestListen", label: "Last listen", sortable: true, filterable: true, width: "w-[12%]" },
];

function formatDate(isoString) {
  if (!isoString || isoString === "Unknown") return "Unknown";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const m = String(date.getMonth() + 1);
  const dd = String(date.getDate()).padStart(2, "0");
  const yyyy = date.getFullYear();
  return `${m}/${dd}/${yyyy}`;
}

function getColumnValue(album, key) {
  if (key === "entry_source") return album.entry_source || album.source || "unknown";
  if (key === "label") return album.label || "Unknown";
  if (key === "release_year") return album.release_year || "Unknown";
  if (key === "totalListens") return album.totalListens ?? 0;
  if (key === "latestListen") return album.latestListen || "Unknown";
  return album[key] || "Unknown";
}

function getColumnLabel(album, key) {
  const value = getColumnValue(album, key);
  if (key === "entry_source") return getSourceLabel(value);
  if (key === "latestListen") return formatDate(value);
  return String(value);
}

function AlbumTable({ albums, searchTerm, onFilterSelect, onDataChanged }) {
  const [sortBy, setSortBy] = useState("latestListen");
  const [ascending, setAscending] = useState(false);
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [columnFilters, setColumnFilters] = useState({});

  const albumArray = useMemo(
    () =>
      Object.entries(albums).map(([id, data]) => ({
        id,
        ...data,
      })),
    [albums]
  );

  const filterOptions = useMemo(() => {
    return Object.fromEntries(
      TABLE_HEADERS
        .filter((header) => header.filterable)
        .map((header) => {
          const optionMap = new Map();
          albumArray.forEach((album) => {
            const value = getColumnLabel(album, header.key);
            optionMap.set(value, value);
          });
          const options = [...optionMap.entries()]
            .map(([value, label]) => ({ value, label }))
            .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));

          return [header.key, options];
        })
    );
  }, [albumArray]);

  const filteredByColumns = albumArray.filter((album) =>
    Object.entries(columnFilters).every(([key, values]) => {
      if (!values.length) return false;
      return values.includes(getColumnLabel(album, key));
    })
  );

  const sortedAlbums = [...filteredByColumns].sort((a, b) => {
    let aValue = a[sortBy];
    let bValue = b[sortBy];

    if (sortBy === "entry_source") {
      aValue = getSourceLabel(a.entry_source || a.source);
      bValue = getSourceLabel(b.entry_source || b.source);
    }

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

  const handleRowClick = (album) => {
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const updateSelectedAlbum = (album) => {
    setSelectedAlbum((current) => (current ? { ...current, ...album } : album));
  };

  const handleAlbumDeleted = () => {
    setSelectedAlbum(null);
    setPanelOpen(false);
  };

  const updateColumnFilter = (key, values) => {
    setColumnFilters((current) => {
      const next = { ...current };
      if (values === null) delete next[key];
      else next[key] = values;
      return next;
    });
  };

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table className="w-full table-fixed bg-card">
          <TableHeader className="bg-muted">
            <TableRow>
              {TABLE_HEADERS.map((header) => (
                <TableHead
                  key={header.key}
                  className={`py-2 align-top text-left text-sm font-medium select-none text-foreground ${header.width}`}
                >
                  {header.sortable ? (
                    <button
                      type="button"
                      className="block max-w-full truncate text-left font-medium leading-tight text-foreground hover:text-primary"
                      onClick={() => handleSort(header.key)}
                      title={`Sort by ${header.label}`}
                    >
                      {header.label}{" "}
                      {sortBy === header.key ? (ascending ? "▲" : "▼") : ""}
                    </button>
                  ) : (
                    <span className="block leading-tight">{header.label}</span>
                  )}
                  {header.filterable && (
                    <div className="mt-1">
                      <AlbumColumnFilter
                        align={["totalListens", "latestListen"].includes(header.key) ? "right" : "left"}
                        label={header.label}
                        selectedValues={columnFilters[header.key]}
                        options={filterOptions[header.key] || []}
                        onApply={(values) => updateColumnFilter(header.key, values)}
                      />
                    </div>
                  )}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>

          <TableBody className="bg-muted">
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

      <AlbumPanelSheet
        open={panelOpen}
        onOpenChange={setPanelOpen}
        album={selectedAlbum}
        searchTerm={searchTerm}
        onFilterSelect={onFilterSelect}
        onAlbumUpdated={updateSelectedAlbum}
        onAlbumDeleted={handleAlbumDeleted}
        onDataChanged={onDataChanged}
      />

    </>
  );
}

export default AlbumTable;
