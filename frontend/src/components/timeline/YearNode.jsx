import { useState, useEffect, useRef } from "react";
import AlbumCluster from "./AlbumCluster";

function YearNode({ year, albums, onAlbumClick }) {
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(false);
  const ref = useRef();

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.1 }
    );

    if (ref.current) observer.observe(ref.current);

    return () => observer.disconnect();
  }, []);

  const dotSize = Math.min(36, 10 + Math.log(albums.length) * 10);

  return (
    <div ref={ref} className="relative flex flex-col items-center">
      {/* year label */}
      <div className="mb-2 text-sm font-medium text-muted-foreground">
        {year}
      </div>

      {/* timeline dot */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="z-10 flex items-center justify-center rounded-full border bg-background shadow transition hover:scale-110"
        style={{
          width: dotSize,
          height: dotSize,
        }}
      />

      {/* cluster */}
      {visible && expanded && (
        <AlbumCluster albums={albums} onAlbumClick={onAlbumClick} />
      )}
    </div>
  );
}

export default YearNode;
