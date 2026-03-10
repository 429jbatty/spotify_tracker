function AlbumRow({ albumId, album }) {

  const BASE = import.meta.env.BASE_URL;

  return (
    <tr key={albumId}>
      <td>
        <img
          loading="lazy"
          src={album.image_url || `${BASE}placeholder_art.png`}
          onError={(e) => {
            e.target.onerror = null;
            e.target.src = `${BASE}placeholder_art.png`;
          }}
          style={{
            width: "50px",
            height: "50px",
            objectFit: "cover",
            borderRadius: "4px",
          }}
        />
      </td>
      <td>{album.name}</td>
      <td>{album.artist}</td>
      <td>{album.release_date}</td>
      <td>{album.label}</td>
    </tr>
  );
}

export default AlbumRow;