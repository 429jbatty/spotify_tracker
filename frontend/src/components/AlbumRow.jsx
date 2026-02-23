function AlbumRow({ albumId, album }) {
  return (
    <tr key={albumId}>
      <td>
        {album.image_url && (
          <img
            src={album.image_url}
            alt={album.name}
            style={{
              width: "50px",
              height: "50px",
              objectFit: "cover",
              borderRadius: "4px",
            }}
          />
        )}
      </td>
      <td>{album.artist}</td>
      <td>{album.name}</td>
      <td>{album.release_date}</td>
      <td>{album.label}</td>
    </tr>
  );
}

export default AlbumRow;