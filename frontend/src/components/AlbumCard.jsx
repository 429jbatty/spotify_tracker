import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";

// Helper function to group album credits by category
function groupAlbumCredits(album) {
  const categories = {
    Engineers: ["engineer", "mix"],
    Instrumentation: ["instrument"],
    Producer: ["producer"],
    Other: [],
  };

  const grouped = {
    Engineers: {},
    Instrumentation: {},
    Producer: {},
    Other: {},
  };

  for (const track of album.tracklist || []) {
    const credits = Array.isArray(track.credits) ? track.credits : [];
    for (const credit of credits) {
      if (!Array.isArray(credit) || credit.length < 3) continue;
      const [name, role, detail] = credit;
      const roleDetail = detail ? `${role}, ${detail}` : role;

      let category = "Other";
      for (const [catName, roles] of Object.entries(categories)) {
        if (roles.includes(role.toLowerCase())) {
          category = catName;
          break;
        }
      }

      if (!grouped[category][name]) grouped[category][name] = new Set();
      grouped[category][name].add(roleDetail);
    }
  }

  for (const category of Object.keys(grouped)) {
    for (const person of Object.keys(grouped[category])) {
      grouped[category][person] = Array.from(grouped[category][person]);
    }
  }

  return grouped;
}

function AlbumInfoRow({ label, value, color = "primary" }) {
  const colors = {
    primary: "bg-primary/10 text-primary hover:bg-primary/20",
    muted: "bg-muted text-foreground/80 hover:bg-muted/50",
    accent: "bg-accent/10 text-accent hover:bg-accent/20",
    destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20",
  };

  return (
    <div
      className={`flex items-center justify-between rounded-lg p-3 ${colors[color]}`}
    >
      <span className="text-sm font-medium">{label}</span>
      {typeof value === "string" || typeof value === "number" ? (
        <span className="text-sm font-semibold">{value}</span>
      ) : (
        <Badge className={`cursor-default ${colors[color]}`}>{value}</Badge>
      )}
    </div>
  );
}

function AlbumCard({ album }) {
  const groupedCredits = groupAlbumCredits(album);
  const BASE = import.meta.env.BASE_URL;

  const hasCredits = Object.values(groupedCredits).some(
    (group) => Object.keys(group).length > 0
  );

  return (
    <Card className="group overflow-hidden transition-all duration-300 hover:shadow-lg border border-border bg-card">
      <CardHeader className="p-0 bg-card">
        {/* Album Artwork */}
        <div className="relative overflow-hidden aspect-square bg-card">
          <img
            loading="lazy"
            src={album.image_url || `${BASE}placeholder_art.png`}
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = `${BASE}placeholder_art.png`;
            }}
            alt={album.name}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        </div>

        {/* Title and Artist */}
        <div className="space-y-2 p-6">
          <CardTitle className="line-clamp-2 text-xl font-bold text-foreground">
            {album.name}
          </CardTitle>
          <p className="text-sm font-medium text-foreground/70">{album.artist}</p>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-6">
        {/* Info Grid */}
        <div className="space-y-3">
          <AlbumInfoRow label="Release" value={album.release_date} color="primary" />
          <AlbumInfoRow label="Label" value={album.label} color="muted" />
        </div>

        {/* Credits Section */}
        {hasCredits && (
          <div className="border-t border-border pt-4">
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="credits" className="border-0">
                <AccordionTrigger className="hover:no-underline py-2 px-0 font-semibold text-foreground">
                  Credits
                </AccordionTrigger>
                <AccordionContent className="space-y-4 pb-0">
                  {Object.entries(groupedCredits).map(([groupName, persons]) => {
                    if (Object.keys(persons).length === 0) return null;
                    return (
                      <div key={groupName} className="space-y-2">
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground/70">
                          {groupName}
                        </h4>
                        <div className="space-y-1 ml-2">
                          {Object.entries(persons).map(([name, roles]) => (
                            <div key={name} className="text-xs text-foreground/70">
                              <span className="font-medium">{name}</span>
                              <span className="text-foreground/50"> — {roles.join(", ")}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default AlbumCard;