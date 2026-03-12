// components/DecadeBar.jsx
import React from "react";

function DecadeBars({ decadeData, chartHeight, currentMax, width, isSelected }) {
  const barHeight = (decadeData.count / currentMax) * chartHeight; // simple relative height
  return (
    <rect
      x={0}
      y={chartHeight - barHeight}
      width={width}
      height={barHeight}
      fill={isSelected ? "#ff7f0e" : "#4c78a8"}
    />
  );
}

export default DecadeBars;