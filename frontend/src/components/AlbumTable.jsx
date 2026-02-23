import { useState } from "react";
import AlbumRow from "./AlbumRow";

function AlbumTable({ albums, searchTerm }) {
  const [sortBy, setSortBy] = useState("listen_date");
  const [ascending, setAscending] = useState(false);

  // Convert albums object to array and filter by search term
  const filteredAlbums = Object.entries(albums)
    .map(([id, data]) => ({ id, ...data }))
    .filter((album) => {
      const term = searchTerm.toLowerCase();
      return (
        album.name.toLowerCase().includes(term) ||
        (album.artist && album.artist.toLowerCase().includes(term)) ||
        (album.label && album.label.toLowerCase().includes(term))
      );
    });

  const sortedAlbums = Object.entries(filteredAlbums)
    .map(([id, data]) => ({ id, ...data }))
    .sort((a, b) => {
      const aValue = a[sortBy];
      const bValue = b[sortBy];

      // sort by date if value looks like a date
      if (!isNaN(Date.parse(aValue))) {
        return ascending
          ? new Date(aValue) - new Date(bValue)
          : new Date(bValue) - new Date(aValue);
      }

      // numeric sort fallback
      if (typeof aValue === "number") {
        return ascending ? aValue - bValue : bValue - aValue;
      }

      // string fallback
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

  // dynamically create headers based on album fields
  const headers = [
    { key: "image_url", label: "" },
    { key: "artist", label: "Artist" },
    { key: "name", label: "Album" },
    { key: "release_date", label: "Release Date" },
    { key: "label", label: "Label" },
  ];

  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead>
        <tr>
          {headers.map((header) => (
            <th
              key={header.key}
              style={{
                borderBottom: "1px solid #ccc",
                padding: "8px",
                cursor: "pointer",
              }}
              onClick={() => handleSort(header.key)}
            >
              {header.label} {sortBy === header.key ? (ascending ? "▲" : "▼") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedAlbums.map((album) => (
          <AlbumRow key={album.id} albumId={album.id} album={album} />
        ))}
      </tbody>
    </table>
  );
}

export default AlbumTable;