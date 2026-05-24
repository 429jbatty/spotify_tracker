import { useState } from "react";
import { Bug, Camera, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { captureScreenshot } from "./utils/bugReportScreenshot";
import { submitBugReport } from "../services/albumApi";

const initialForm = {
  description: "",
  screenshotDataUrl: "",
  screenshotSource: "",
};

function BugReportDialog({ selectedUser }) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const resetState = () => {
    setForm(initialForm);
    setIsCapturing(false);
    setIsSubmitting(false);
    setError(null);
  };

  const handleOpenChange = (nextOpen) => {
    setOpen(nextOpen);
    if (!nextOpen) resetState();
  };

  const handleCaptureScreenshot = async () => {
    setIsCapturing(true);
    setError(null);
    try {
      const screenshot = await captureScreenshot();
      setForm((current) => ({
        ...current,
        screenshotDataUrl: screenshot.dataUrl,
        screenshotSource: screenshot.source,
      }));
    } catch (err) {
      setError(err.message || "Could not capture a screenshot.");
    } finally {
      setIsCapturing(false);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.description.trim() || !form.screenshotDataUrl) return;

    setIsSubmitting(true);
    setError(null);
    try {
      await submitBugReport({
        description: form.description.trim(),
        screenshot_data_url: form.screenshotDataUrl,
        screenshot_source: form.screenshotSource || null,
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        user_slug: selectedUser?.slug || null,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
          device_pixel_ratio: window.devicePixelRatio || 1,
        },
      });
      toast({
        title: "Bug report sent",
        description: "The report and screenshot were saved on the server.",
      });
      setOpen(false);
    } catch (err) {
      setError(err.message || "Could not send the bug report.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSubmit =
    Boolean(form.description.trim()) &&
    Boolean(form.screenshotDataUrl) &&
    !isCapturing &&
    !isSubmitting;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Bug className="size-4" />
          Report bug
        </Button>
      </DialogTrigger>
      <DialogContent
        data-bug-report-dialog="true"
        className="max-h-[90vh] overflow-y-auto sm:max-w-xl"
      >
        <DialogHeader>
          <DialogTitle>Report a bug</DialogTitle>
          <DialogDescription>
            Capture the current page and add a short note.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground" htmlFor="bug-description">
              What happened?
            </label>
            <textarea
              id="bug-description"
              className="min-h-28 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-3 focus:ring-ring/50"
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              maxLength={2000}
              placeholder="A couple sentences about what went wrong"
            />
          </div>

          <div className="space-y-3 rounded-md border border-border/70 bg-muted/20 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-foreground">Screenshot</p>
                <p className="text-xs text-muted-foreground">
                  Secure browsers may ask which tab to share. Otherwise the app will
                  capture the visible page.
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCaptureScreenshot}
                disabled={isCapturing || isSubmitting}
              >
                <Camera className="size-4" />
                {isCapturing ? "Capturing..." : "Capture"}
              </Button>
            </div>

            {form.screenshotDataUrl ? (
              <div className="space-y-2">
                <img
                  src={form.screenshotDataUrl}
                  alt="Captured bug report screenshot"
                  className="max-h-64 w-full rounded-md border border-border object-contain"
                />
                <p className="text-xs text-muted-foreground">
                  Captured{" "}
                  {form.screenshotSource === "screen"
                    ? "from browser screen sharing"
                    : "from the visible app page"}
                  .
                </p>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                No screenshot captured yet
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!canSubmit}>
              <Send className="size-4" />
              {isSubmitting ? "Sending..." : "Send report"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default BugReportDialog;
