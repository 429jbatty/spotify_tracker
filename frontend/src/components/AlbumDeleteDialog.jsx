import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { deleteAlbum } from "../services/albumApi";
import { StatusMessage } from "./albumEditor/FormBits";

function AlbumDeleteDialog({ album, disabled, onAlbumDeleted, onDataChanged }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const handleDelete = async () => {
    if (!album?.id) return;

    setPending(true);
    setError(null);
    try {
      await deleteAlbum(album.id);
      await onDataChanged?.();
      setOpen(false);
      onAlbumDeleted?.(album);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="destructive" disabled={disabled || pending}>
          <Trash2 className="size-4" />
          Delete album
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete album?</DialogTitle>
          <DialogDescription>
            This will permanently delete {album?.artist} - {album?.name}, including
            listen history, metadata, and artwork references.
          </DialogDescription>
        </DialogHeader>

        {error && <StatusMessage error={error} />}

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="destructive"
            disabled={pending}
            onClick={handleDelete}
          >
            {pending ? "Deleting..." : "Delete album"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AlbumDeleteDialog;
