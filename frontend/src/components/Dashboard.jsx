import StatsBar from "./StatsBar";
import RecentAlbums from "./RecentAlbums";

function Dashboard({ albums }) {
  return (
    <div style={{ padding: "2rem" }}>
      <StatsBar albums={albums} />
      <RecentAlbums albums={albums} />
    </div>
  );
}

export default Dashboard;

