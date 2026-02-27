// components/Timeline.jsx
import React, { useMemo } from "react";
import DecadeBar from "./DecadeBar";
import YearBars from "./YearBars";

function Timeline({ albums, selectedFilter, onSelect, onReset, chartWidth = 600, chartHeight = 300 }) {
  const margin = { top: 20, right: 20, bottom: 50, left: 50 };
  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;

  // compute albums per decade
  const albumsPerDecade = useMemo(() => {
    const decadeMap = {};
    Object.values(albums).forEach((a) => {
      if (!a.release_date) return;
      const year = parseInt(a.release_date.slice(0, 4));
      const decade = Math.floor(year / 10) * 10;
      if (!decadeMap[decade]) decadeMap[decade] = { decade, count: 0, years: {} };
      decadeMap[decade].count += 1;
      decadeMap[decade].years[year] = (decadeMap[decade].years[year] || 0) + 1;
    });
    return Object.values(decadeMap).sort((a, b) => a.decade - b.decade);
  }, [albums]);

  // determine current max for Y-axis
  let currentMax = 1; // fallback
  if (selectedFilter.decade) {
    const decadeData = albumsPerDecade.find(d => d.decade === selectedFilter.decade);
    if (decadeData && Object.values(decadeData.years).length > 0) {
      currentMax = Math.max(...Object.values(decadeData.years));
    }
  } else if (albumsPerDecade.length > 0) {
    currentMax = Math.max(...albumsPerDecade.map(d => d.count));
  }

  const ticks = 5;
  const tickValues = Array.from({ length: ticks + 1 }, (_, i) =>
    Math.round((currentMax / ticks) * i)
  );

  return (
    <svg width={chartWidth} height={chartHeight} onClick={onReset} style={{ cursor: "pointer" }}>
      <g transform={`translate(${margin.left}, ${margin.top})`}>
        {/* Y-axis */}
        <g className="y-axis">
          {tickValues.map((val, idx) => {
            const y = innerHeight - (val / currentMax) * innerHeight;
            return (
              <g key={idx} transform={`translate(0, ${y})`}>
                <line x1={0} x2={-5} y1={0} y2={0} stroke="#000" />
                <text x={-10} y={4} textAnchor="end" fontSize={10} fill="#000">{val}</text>
              </g>
            );
          })}
          <line x1={0} y1={0} x2={0} y2={innerHeight} stroke="#000" />
        </g>

        {/* X-axis */}
        <line x1={0} y1={innerHeight} x2={innerWidth} y2={innerHeight} stroke="#000" strokeWidth={1.5} />

        {/* Render decade bars only if no decade is selected */}
        {!selectedFilter.decade && albumsPerDecade.map((decadeData, idx) => {
          const barWidth = innerWidth / albumsPerDecade.length - 5;
          return (
            <g
              key={decadeData.decade}
              transform={`translate(${idx * (barWidth + 5)}, 0)`}
              onClick={(e) => { e.stopPropagation(); onSelect(decadeData.decade); }}
              style={{ cursor: "pointer" }}
            >
              <DecadeBar
                decadeData={decadeData}
                chartHeight={innerHeight}
                currentMax={currentMax}
                width={barWidth}
                isSelected={false}
              />
            </g>
          );
        })}

        {/* Render year bars if a decade is selected */}
        {selectedFilter.decade && (
          <YearBars
            decadeData={albumsPerDecade.find(d => d.decade === selectedFilter.decade)}
            chartHeight={innerHeight}
            chartWidth={innerWidth}
            onYearClick={(decade, year) => onSelect(decade, year)}
            selectedYear={selectedFilter.year} // highlight selected year
          />
        )}
      </g>
    </svg>
  );
}

export default Timeline;