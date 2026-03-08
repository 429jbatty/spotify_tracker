function ViewSwitcher({ view, setView }) {
  const buttonStyle = (isActive) => ({
    marginRight: "0.5rem",
    padding: "0.5rem 1rem",
    cursor: "pointer",
    backgroundColor: isActive ? "#007bff" : "#f0f0f0",
    color: isActive ? "white" : "black",
    border: "none",
    borderRadius: "4px",
  });

  return (
    <div style={{ marginBottom: "1rem" }}>
      <button onClick={() => setView("dashboard")} style={buttonStyle(view === "dashboard")}>Dashboard</button>
      <button onClick={() => setView("table")} style={buttonStyle(view === "table")}>All</button>
      <button onClick={() => setView("card")} style={buttonStyle(view === "card")}>Cards</button>
      <button onClick={() => setView("timeline")} style={buttonStyle(view === "timeline")}>Release Dates</button>
    </div>
  );
}

export default ViewSwitcher;