import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";

function UniversalHeader({ view, setView }) {
  return (
    <header className="border-b border-slate-200 bg-gradient-to-r from-slate-50 via-slate-50 to-emerald-50 shadow-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">

        {/* Left: App Title */}
        <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-slate-900 to-emerald-700 bg-clip-text text-transparent">
          Album Tracker
        </h1>

        {/* Center: View Navigation */}
        <Tabs value={view} onValueChange={setView}>
          <TabsList className="bg-slate-100 p-1">
            <TabsTrigger
              value="dashboard"
              className="relative px-4 py-2 text-sm font-medium transition-all data-[state=active]:bg-white data-[state=active]:text-emerald-700 data-[state=active]:shadow-sm hover:text-emerald-600"
            >
              Dashboard
            </TabsTrigger>
            <TabsTrigger
              value="table"
              className="relative px-4 py-2 text-sm font-medium transition-all data-[state=active]:bg-white data-[state=active]:text-emerald-700 data-[state=active]:shadow-sm hover:text-emerald-600"
            >
              All
            </TabsTrigger>
            <TabsTrigger
              value="card"
              className="relative px-4 py-2 text-sm font-medium transition-all data-[state=active]:bg-white data-[state=active]:text-emerald-700 data-[state=active]:shadow-sm hover:text-emerald-600"
            >
              Cards
            </TabsTrigger>
            <TabsTrigger
              value="timeline"
              className="relative px-4 py-2 text-sm font-medium transition-all data-[state=active]:bg-white data-[state=active]:text-emerald-700 data-[state=active]:shadow-sm hover:text-emerald-600"
            >
              Release Dates
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </header>
  );
}

export default UniversalHeader;