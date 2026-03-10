import StatsBar from "./StatsBar";
import RecentAlbums from "./RecentAlbums";

function Dashboard({ albums, ids }) {
  return (
    <div style={{ padding: "2rem" }}>
      <StatsBar albums={albums} />
      <RecentAlbums albums={albums} ids={ids} />
    </div>
  );
}

export default Dashboard;

