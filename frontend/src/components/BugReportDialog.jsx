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
import { submitBugReport } from "../services/albumApi";

const initialForm = {
  description: "",
  screenshotDataUrl: "",
};

async function captureScreenFrame() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new Error("Screen capture is not supported in this browser.");
  }

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: {
      displaySurface: "browser",
    },
    audio: false,
  });

  try {
    const video = document.createElement("video");
    const loaded = new Promise((resolve, reject) => {
      video.onloadedmetadata = resolve;
      video.onerror = () => reject(new Error("Could not read the screen capture."));
    });
    video.srcObject = stream;
    video.muted = true;
    await loaded;
    await video.play();

    if (!video.videoWidth || !video.videoHeight) {
      throw new Error("The captured screen did not include a video frame.");
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not prepare screenshot capture.");

    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png");
  } finally {
    stream.getTracks().forEach((track) => track.stop());
  }
}

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
      const screenshotDataUrl = await captureScreenFrame();
      setForm((current) => ({ ...current, screenshotDataUrl }));
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Report a bug</DialogTitle>
          <DialogDescription>
            Capture what you are seeing and add a short note.
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
                  Your browser will ask which screen, window, or tab to share.
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
              <img
                src={form.screenshotDataUrl}
                alt="Captured bug report screenshot"
                className="max-h-64 w-full rounded-md border border-border object-contain"
              />
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
