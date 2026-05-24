import { Badge } from "@/components/ui/badge";

function AlbumInfoRow({ label, value, color = "primary" }) {
  const colors = {
    primary: "bg-primary/10 text-primary hover:bg-primary/20",
    muted: "bg-muted text-foreground/80 hover:bg-muted/50",
    accent:
      "border border-primary/15 bg-primary/5 text-foreground hover:bg-primary/10",
    destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20",
  };

  return (
    <div className={`flex items-center justify-between rounded-lg p-3 ${colors[color]}`}>
      <span className="text-sm font-medium">{label}</span>

      {typeof value === "string" || typeof value === "number" ? (
        <span className="text-sm font-semibold">{value}</span>
      ) : (
        <Badge className={`cursor-default ${colors[color]}`}>{value}</Badge>
      )}
    </div>
  );
}

export default AlbumInfoRow;
