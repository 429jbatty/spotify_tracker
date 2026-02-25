function StatCard({ title, value }) {
  return (
    <div style={{
      flex: 1,
      border: "1px solid #ccc",
      borderRadius: "8px",
      padding: "1rem",
      textAlign: "center",
      marginRight: "0.5rem"
    }}>
      <div style={{ fontSize: "0.9rem", color: "#666" }}>{title}</div>
      <div style={{ fontSize: "1.5rem", fontWeight: "bold" }}>{value}</div>
    </div>
  );
}

export default StatCard;