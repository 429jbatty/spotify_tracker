import { Input } from "@/components/ui/input";

function AlbumSearch({ searchTerm, setSearchTerm }) {
  return (
    <div className="mb-4 w-full text-foreground">
      <Input
        type="text"
        placeholder="Search albums, artists, labels, genres, your tags, years, or credits..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full"
      />
    </div>
  );
}

export default AlbumSearch;
