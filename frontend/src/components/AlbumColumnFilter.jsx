import { useEffect, useMemo, useRef, useState } from "react";
import { Filter, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function normalize(value) {
  return String(value || "").toLowerCase();
}

function AlbumColumnFilter({
  align = "left",
  label,
  options,
  selectedValues,
  onApply,
  buttonClassName = "",
  optionClassName = "",
  mobile = false,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [draftValues, setDraftValues] = useState(() => new Set());
  const containerRef = useRef(null);
  const active = Array.isArray(selectedValues);
  const displayCount = active ? selectedValues.length : options.length;

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const visibleOptions = useMemo(() => {
    const term = normalize(query).trim();
    if (!term) return options;
    return options.filter((option) => normalize(option.label).includes(term));
  }, [options, query]);

  const selectedVisibleCount = visibleOptions.filter((option) =>
    draftValues.has(option.value)
  ).length;
  const allVisibleSelected =
    visibleOptions.length > 0 && selectedVisibleCount === visibleOptions.length;

  const toggleValue = (value) => {
    setDraftValues((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const selectVisible = () => {
    setDraftValues((current) => {
      const next = new Set(current);
      visibleOptions.forEach((option) => next.add(option.value));
      return next;
    });
  };

  const clearVisible = () => {
    setDraftValues((current) => {
      const next = new Set(current);
      visibleOptions.forEach((option) => next.delete(option.value));
      return next;
    });
  };

  const applyFilter = () => {
    const selected = [...draftValues].filter((value) =>
      options.some((option) => option.value === value)
    );
    onApply(selected.length === options.length ? null : selected);
    setOpen(false);
  };

  const clearFilter = () => {
    setDraftValues(new Set(options.map((option) => option.value)));
    onApply(null);
    setOpen(false);
  };

  const toggleOpen = () => {
    setOpen((current) => {
      if (!current) {
        setDraftValues(
          new Set(active ? selectedValues : options.map((option) => option.value))
        );
        setQuery("");
      }
      return !current;
    });
  };

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <Button
        type="button"
        variant={active ? "secondary" : "outline"}
        size="xs"
        aria-label={`Filter ${label}`}
        aria-expanded={open}
        onClick={toggleOpen}
        className={`h-7 w-full justify-between px-2 ${buttonClassName}`}
      >
        <span className="truncate text-xs">
          {active ? `${displayCount} selected` : "All"}
        </span>
        <Filter className={active ? "text-primary" : "text-muted-foreground"} />
      </Button>

      {open && (
        <div
          className={`absolute top-full z-50 mt-1 w-72 rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-lg ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <div className="flex items-center gap-2 rounded-md border border-input px-2">
            <Search className="size-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search"
              className="h-8 border-0 px-0 shadow-none focus-visible:ring-0"
            />
            {query && (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="Clear search"
                onClick={() => setQuery("")}
                className={mobile ? "min-h-11 min-w-11" : ""}
              >
                <X />
              </Button>
            )}
          </div>

          <div className="mt-3 flex items-center justify-between gap-2 text-xs">
            <button
              type="button"
              className={`px-2 text-primary hover:underline ${mobile ? "min-h-11" : ""}`}
              onClick={allVisibleSelected ? clearVisible : selectVisible}
            >
              {allVisibleSelected ? "Clear shown" : "Select shown"}
            </button>
            <button
              type="button"
              className={`px-2 text-muted-foreground hover:text-foreground ${mobile ? "min-h-11" : ""}`}
              onClick={() => setDraftValues(new Set())}
            >
              Clear all
            </button>
          </div>

          <div className="mt-2 max-h-64 overflow-y-auto rounded-md border border-border bg-background">
            {visibleOptions.length > 0 ? (
              visibleOptions.map((option) => {
                const checked = draftValues.has(option.value);

                return (
                  <label
                    key={option.value}
                    className={`flex cursor-pointer items-center gap-2 px-2 py-1.5 text-xs hover:bg-muted ${optionClassName}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleValue(option.value)}
                      className="size-3.5 accent-primary"
                    />
                    <span className="min-w-0 truncate" title={option.label}>
                      {option.label}
                    </span>
                  </label>
                );
              })
            ) : (
              <div className="px-2 py-6 text-center text-xs text-muted-foreground">
                No matches
              </div>
            )}
          </div>

          <div className="mt-3 flex justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={clearFilter} className={mobile ? "min-h-11" : ""}>
              Clear Filter
            </Button>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setOpen(false)}
                className={mobile ? "min-h-11" : ""}
              >
                Cancel
              </Button>
              <Button type="button" size="sm" onClick={applyFilter} className={mobile ? "min-h-11" : ""}>
                Apply
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AlbumColumnFilter;
