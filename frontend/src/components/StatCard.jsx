function StatCard({ title, value, color = "text-neutral-600" }) {
  return (
    <div className="flex-1 rounded-xl bg-muted p-6 text-center shadow-sm">
      {/* Title */}
      <div className="text-sm font-medium text-neutral-foreground">
        {title}
      </div>

      {/* Value */}
      <div className={`mt-2 text-3xl font-extrabold ${color}`}>
        {value}
      </div>
    </div>
  );
}

export default StatCard;