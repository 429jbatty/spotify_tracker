function BarChart({ data }) {
  // Replace with your chart library
  return (
    <div style={{
      border: "1px solid #ccc",
      borderRadius: "8px",
      padding: "1rem",
      height: "200px",
      textAlign: "center",
      marginBottom: "1rem"
    }}>
      Chart Placeholder
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

export default BarChart;