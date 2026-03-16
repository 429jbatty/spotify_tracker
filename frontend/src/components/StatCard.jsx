function StatCard({ title, value, color = "text-foreground", bgColor = "bg-muted" }) {
  return (
    <div className={`flex-1 rounded-lg ${bgColor} p-3 text-center shadow-sm`}>
      {/* Title */}
      <div className="text-xs font-medium text-foreground">
        {title}
      </div>

      {/* Value */}
      <div className={`mt-1 text-xl font-bold ${color}`}>
        {value}
      </div>
    </div>
  );
}

export default StatCard;