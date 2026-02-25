import StatsBar from "./StatsBar";
import AlbumsByDecadeChart from "./AlbumsByDecadeChart";
import RecentAlbums from "./RecentAlbums";

function Dashboard({ albums }) {
  return (
    <div style={{ padding: "2rem" }}>
      <StatsBar albums={albums} />
      <AlbumsByDecadeChart albums={albums} />
      <RecentAlbums albums={albums} />
    </div>
  );
}

export default Dashboard;