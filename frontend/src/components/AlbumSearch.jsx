function AlbumSearch({ searchTerm, setSearchTerm }) {
  return (
    <input
      type="text"
      placeholder="Search by album, artist, or label..."
      value={searchTerm}
      onChange={(e) => setSearchTerm(e.target.value)}
      style={{
        marginBottom: "1rem",
        padding: "0.5rem",
        width: "100%",
        borderRadius: "4px",
        border: "1px solid #ccc",
      }}
    />
  );
}

export default AlbumSearch;