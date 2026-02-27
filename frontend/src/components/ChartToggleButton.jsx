// components/ChartToggleButton.jsx
import React from "react";

function ChartToggleButton({ mode, onToggle }) {
  return (
    <button
      onClick={onToggle}
      style={{
        marginBottom: "10px",
        padding: "6px 12px",
        cursor: "pointer",
        borderRadius: "4px",
        border: "1px solid #ccc",
        backgroundColor: "#f0f0f0",
      }}
    >
      View by {mode === "decade" ? "year" : "decade"}
    </button>
  );
}

export default ChartToggleButton;