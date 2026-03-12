import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";

function UniversalHeader({ view, setView }) {
  return (
    <header className="relative w-full">

    {/* Horizontal sunburst gradient */}
    <div className="absolute inset-0 bg-gradient-to-r from-yellow-200 via-orange-300 to-red-400"></div>

    {/* Vertical fade overlay */}
    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-white/100"></div>

    {/* Content */}
    <div className="relative flex justify-between items-center h-50 px-6">

        {/* Left: App Title */}
        <h1 className="text-5xl font-extrabold tracking-tight text-mauve-700 drop-shadow-lg">
        Vinyl Vault
        </h1>

        {/* Center: View Navigation */}
        <Tabs value={view} onValueChange={setView}>
        <TabsList className="bg-white/30 backdrop-blur-sm rounded-xl p-1">
            {["dashboard", "table", "card", "timeline"].map((v) => (
            <TabsTrigger
                key={v}
                value={v}
                className="relative px-4 py-2 text-sm font-medium transition-all 
                        data-[state=active]:bg-white/80 
                        data-[state=active]:text-orange-600 
                        data-[state=active]:shadow-md 
                        hover:text-orange-500 rounded-lg"
            >
                {v === "dashboard" ? "Dashboard" : v === "table" ? "All" : v === "card" ? "Cards" : "Release Dates"}
            </TabsTrigger>
            ))}
        </TabsList>
        </Tabs>

        {/* Right Actions */}
        <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="text-orange-600 border-orange-400 hover:bg-orange-50">
            Add Album
        </Button>
        </div>

    </div>
    </header>
  );
}

export default UniversalHeader;