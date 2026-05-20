import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { updateAlbumUserTags } from "../services/albumApi";
import { createAlbumFilter } from "./utils/albumFilters";
import { USER_TAG_GROUPS, getUserTagLabel } from "./utils/userTags";

function TagButton({ active, disabled, children, onClick }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        "rounded-md border px-2 py-1 text-xs font-medium transition-colors",
        active
          ? "border-primary bg-primary/12 text-foreground"
          : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
        disabled ? "cursor-not-allowed opacity-60" : "",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function AlbumUserTags({ album, onAlbumUpdated, onDataChanged, onFilterSelect }) {
  const { toast } = useToast();
  const [selectedTags, setSelectedTags] = useState(album.your_tags || []);
  const [savingTagId, setSavingTagId] = useState(null);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setSelectedTags(album.your_tags || []);
  }, [album.your_tags]);

  const handleToggleTag = async (tagId) => {
    const nextTags = selectedTags.includes(tagId)
      ? selectedTags.filter((value) => value !== tagId)
      : [...selectedTags, tagId];

    setSavingTagId(tagId);
    try {
      const updatedAlbum = await updateAlbumUserTags(album.id, nextTags);
      setSelectedTags(updatedAlbum.your_tags || []);
      onAlbumUpdated?.(updatedAlbum);
      await onDataChanged?.();
    } catch (error) {
      toast({
        title: "Could not update tags",
        description: error.message || "An error occurred while saving your tags.",
        variant: "destructive",
      });
    } finally {
      setSavingTagId(null);
    }
  };

  return (
    <section className="space-y-4 border-t pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Your Tags</h3>
          {selectedTags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {selectedTags.map((tagId) => (
                <button
                  key={tagId}
                  type="button"
                  onClick={() =>
                    onFilterSelect?.(
                      createAlbumFilter("your-tag", tagId, getUserTagLabel(tagId))
                    )
                  }
                  className="disabled:pointer-events-none"
                  disabled={!onFilterSelect}
                >
                  <Badge variant="secondary" className="bg-primary/10 text-foreground">
                    {getUserTagLabel(tagId)}
                  </Badge>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Add a few personal tags for how this album sounds, feels, or stands out.
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setIsEditing((current) => !current)}
        >
          {isEditing ? "Done" : "Edit Tags"}
        </Button>
      </div>

      {isEditing && (
        <div className="space-y-4">
          {USER_TAG_GROUPS.map((group) => (
            <div key={group.id} className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.label}
              </h4>
              <div className="flex flex-wrap gap-2">
                {group.tags.map((tag) => (
                  <TagButton
                    key={tag.id}
                    active={selectedTags.includes(tag.id)}
                    disabled={savingTagId === tag.id}
                    onClick={() => handleToggleTag(tag.id)}
                  >
                    {tag.label}
                  </TagButton>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default AlbumUserTags;
