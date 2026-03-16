import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";

function UniversalHeader({ view, setView }) {
  const [waveform, setWaveform] = useState([]);

  useEffect(() => {
    const heights = Array.from({ length: 100 }).map(() => Math.random() * 40 + 12);
    setWaveform(heights);
  }, []);

  return (
    <header className="relative w-full">

      {/* Horizontal gradient */}
      <div className="absolute inset-0 bg-gradient-to-r from-chart-1/60 via-chart-4/40 to-primary/60"></div>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_15%,hsl(var(--primary)/0.10),transparent_55%)]"></div>

      {/* Vertical fade */}
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent/0 via-[10%] to-background"></div>

      {/* Waveform */}
      <div className="absolute inset-0 text-primary pointer-events-none">
      <svg className="w-full h-full" preserveAspectRatio="none">
          <defs>
          <clipPath id="waveClip">
              <rect x="20%" y="0%" width="22%" height="100%" />
              <rect x="70%" y="0%" width="22%" height="100%" />
          </clipPath>
          </defs>

          <g clipPath="url(#waveClip)">
          {waveform.map((h, i) => (
              <rect
              key={i}
              x={`${i * 1}%`}
              y={`${50 - h / 2}%`}
              width="0.25%"
              height={`${h}%`}
              className="fill-current opacity-30"
              rx="1"
              />
          ))}
          </g>
      </svg>
      </div>

      {/* Content */}
      <div className="relative flex justify-between items-center h-40 px-6">

        {/* Title */}
        <h1 className="text-5xl font-semibold tracking-tight drop-shadow-lg">
            <span className="text-primary/80">Sound</span>
            <span className="text-foreground/50">Stats</span>
        </h1>

        {/* Navigation */}
        <Tabs value={view} onValueChange={setView}>
          <TabsList className="bg-background/30 backdrop-blur-sm rounded-xl p-1">
            {["dashboard", "discovery", "table", "timeline"].map((v) => (
              <TabsTrigger
                key={v}
                value={v}
                className="relative px-4 py-2 text-sm font-medium transition-all
                  data-[state=active]:bg-background/80
                  data-[state=active]:text-primary
                  data-[state=active]:shadow-md
                  hover:text-primary
                  rounded-lg"
              >
                {v === "dashboard"
                  ? "Dashboard"
                  : v === "discovery"
                  ? "Discovery"
                  : v === "table"
                  ? "All"
                  : "Release Dates"}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-primary border-border hover:bg-accent"
          >
            Add Album
          </Button>
        </div>

      </div>
    </header>
  );
}

export default UniversalHeader;