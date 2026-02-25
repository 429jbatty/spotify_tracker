import BarChart from "./BarChart";
function AlbumsByDecadeChart({ albums }) {

    const decadeCounts = {};
    Object.values(albums).forEach(a => {
        if (!a.release_date) return;
        const year = parseInt(a.release_date.slice(0, 4));
        const decade = Math.floor(year / 10) * 10;
        decadeCounts[decade] = (decadeCounts[decade] || 0) + 1;
    });
    const albumsPerDecade = Object.entries(decadeCounts).map(([decade, count]) => ({
        decade,
        count,
    }));

    return <BarChart data={albumsPerDecade} />;
}

export default AlbumsByDecadeChart;