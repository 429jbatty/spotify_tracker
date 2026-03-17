import { Badge } from "@/components/ui/badge";

export default function ListenCountBadge({ count }) {
  if (!count) return null;

  return (
    <Badge variant="secondary">
      {count} {count === 1 ? "listen" : "listens"}
    </Badge>
  );
}