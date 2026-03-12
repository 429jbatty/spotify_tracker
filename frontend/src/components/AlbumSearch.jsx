import { Input } from "@/components/ui/input";

function AlbumSearch({ searchTerm, setSearchTerm }) {
  return (
    <div className="mb-4 w-full">
      <Input
        type="text"
        placeholder="Search by album, artist, or label..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full"
      />
    </div>
  );
}

export default AlbumSearch;