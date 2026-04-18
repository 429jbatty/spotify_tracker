import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  BarChart3,
  CalendarDays,
  DatabaseZap,
  Library,
  Plus,
  ShieldCheck,
  Table2,
} from "lucide-react";

const NAV_ITEMS = [
  {
    value: "discovery",
    label: "Discovery",
    description: "Recent patterns",
    icon: BarChart3,
    accent: "data-active:bg-chart-1/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
  {
    value: "table",
    label: "Library",
    description: "All albums",
    icon: Table2,
    accent: "data-active:bg-chart-2/20 data-active:text-foreground",
    iconAccent: "text-chart-2",
  },
  {
    value: "timeline",
    label: "Release Dates",
    description: "Years and decades",
    icon: CalendarDays,
    accent: "data-active:bg-chart-3/20 data-active:text-foreground",
    iconAccent: "text-chart-3",
  },
  {
    value: "quality",
    label: "Data Quality",
    description: "Metadata cleanup",
    icon: ShieldCheck,
    accent: "data-active:bg-chart-4/20 data-active:text-foreground",
    iconAccent: "text-chart-4",
  },
];

function UniversalHeader({ view, setView }) {
  return (
    <header className="sticky top-0 z-30 border-b border-primary/20 bg-[linear-gradient(90deg,hsl(var(--chart-1)/0.18),hsl(var(--background)/0.96)_34%,hsl(var(--chart-4)/0.10))] backdrop-blur">
      <div className="px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex size-11 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary shadow-sm">
                <Library className="size-5" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-foreground">
                  SoundStats
                </h1>
                <p className="text-xs text-muted-foreground">
                  Album listening history
                </p>
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/15 xl:hidden"
            >
              <Plus className="size-4" />
              Add Album
            </Button>
          </div>

          <Tabs value={view} onValueChange={setView} className="min-w-0">
            <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-md border border-primary/15 bg-background/70 p-1 shadow-sm xl:w-auto">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;

                return (
                  <TabsTrigger
                    key={item.value}
                    value={item.value}
                    className={`min-w-[10.5rem] justify-start gap-3 rounded-md px-3 py-2 hover:bg-muted/70 ${item.accent}`}
                  >
                    <Icon className={`size-4 ${item.iconAccent}`} />
                    <span className="flex flex-col items-start leading-tight">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className="text-[11px] font-normal text-muted-foreground">
                        {item.description}
                      </span>
                    </span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>

          <div className="hidden items-center gap-2 xl:flex">
            <Button
              variant="outline"
              size="sm"
              className="border-chart-3/30 bg-chart-3/10 text-foreground hover:bg-chart-3/15"
            >
              <DatabaseZap className="size-4" />
              Refresh Metadata
            </Button>
            <Button
              size="sm"
              className="bg-primary text-primary-foreground hover:bg-primary/85"
            >
              <Plus className="size-4" />
              Add Album
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}

export default UniversalHeader;
