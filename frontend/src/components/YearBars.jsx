// components/YearBars.jsx
import React from "react";

function YearBars({ decadeData, chartHeight, chartWidth, onYearClick, selectedYear, spacing = 2 }) {
  const years = Object.entries(decadeData.years).sort(([a], [b]) => a - b);
  const maxCount = Math.max(...years.map(([_, count]) => count));
  const barWidth = (chartWidth - spacing * (years.length - 1)) / years.length;

  return (
    <g className="year-bars">
      {years.map(([year, count], idx) => {
        const barHeight = (count / maxCount) * chartHeight;
        const x = idx * (barWidth + spacing);
        const y = chartHeight - barHeight;
        const isSelected = selectedYear === parseInt(year, 10);
        return (
          <rect
            key={year}
            x={x}
            y={y}
            width={barWidth}
            height={barHeight}
            fill={isSelected ? "#ff7f0e" : "#69b3a2"}
            style={{ cursor: "pointer" }}
            onClick={(e) => { e.stopPropagation(); onYearClick(decadeData.decade, parseInt(year, 10)); }}
          />
        );
      })}
    </g>
  );
}

export default YearBars;