async function captureScreenFrame() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getDisplayMedia) {
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

function normalizeScreenshotColor(value) {
  if (!value.startsWith("oklch(")) return value;
  return oklchToRgb(value) || value;
}

function oklchToRgb(value) {
  const match = value.match(/^oklch\((.+)\)$/);
  if (!match) return null;

  const [colorParts, alphaPart] = match[1].split("/").map((part) => part.trim());
  const [lightnessToken, chromaToken, hueToken] = colorParts.split(/\s+/);
  const lightness = parseOklchNumber(lightnessToken, 1);
  const chroma = Number.parseFloat(chromaToken);
  const hue = Number.parseFloat(hueToken || "0");
  const alpha = alphaPart ? parseOklchNumber(alphaPart, 1) : 1;

  if (![lightness, chroma, hue, alpha].every(Number.isFinite)) return null;

  const hueRadians = (hue * Math.PI) / 180;
  const okLabA = chroma * Math.cos(hueRadians);
  const okLabB = chroma * Math.sin(hueRadians);

  const longL = lightness + 0.3963377774 * okLabA + 0.2158037573 * okLabB;
  const longM = lightness - 0.1055613458 * okLabA - 0.0638541728 * okLabB;
  const longS = lightness - 0.0894841775 * okLabA - 1.291485548 * okLabB;

  const l = longL ** 3;
  const m = longM ** 3;
  const s = longS ** 3;

  const red = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const green = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const blue = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;

  const rgb = [red, green, blue].map(linearSrgbToByte);
  const safeAlpha = Math.min(1, Math.max(0, alpha));
  if (safeAlpha < 1) return `rgba(${rgb.join(", ")}, ${roundAlpha(safeAlpha)})`;
  return `rgb(${rgb.join(", ")})`;
}

function parseOklchNumber(token, percentScale) {
  if (!token) return Number.NaN;
  if (token.endsWith("%")) {
    return Number.parseFloat(token) / 100 * percentScale;
  }
  return Number.parseFloat(token);
}

function linearSrgbToByte(value) {
  const clamped = Math.min(1, Math.max(0, value));
  const encoded =
    clamped <= 0.0031308
      ? 12.92 * clamped
      : 1.055 * clamped ** (1 / 2.4) - 0.055;
  return Math.round(encoded * 255);
}

function roundAlpha(value) {
  return Math.round(value * 1000) / 1000;
}

async function capturePageSnapshot() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Could not prepare screenshot capture.");

  context.scale(scale, scale);
  drawPageSnapshot(context, width, height);
  return canvas.toDataURL("image/png");
}

function drawPageSnapshot(context, width, height) {
  const rootStyle = window.getComputedStyle(document.documentElement);
  const bodyStyle = window.getComputedStyle(document.body);
  context.fillStyle = canvasColor(rootStyle.backgroundColor, "#ffffff");
  context.fillRect(0, 0, width, height);
  context.fillStyle = canvasColor(bodyStyle.backgroundColor, context.fillStyle);
  context.fillRect(0, 0, width, height);

  const elements = getSnapshotElements();
  elements.forEach((element) => drawElementBox(context, element));
  elements.forEach((element) => drawElementContent(context, element));
}

function getSnapshotElements() {
  return [...document.body.querySelectorAll("*")].filter((element) => {
    if (element.closest("[data-bug-report-dialog='true'], [data-slot='dialog-overlay']")) {
      return false;
    }

    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number.parseFloat(style.opacity) > 0 &&
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom >= 0 &&
      rect.right >= 0 &&
      rect.top <= window.innerHeight &&
      rect.left <= window.innerWidth
    );
  });
}

function drawElementBox(context, element) {
  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  const backgroundColor = canvasColor(style.backgroundColor, null);

  if (backgroundColor && !isTransparentColor(backgroundColor)) {
    context.fillStyle = backgroundColor;
    fillRoundedRect(context, rect, Number.parseFloat(style.borderRadius) || 0);
  }

  if (element.tagName === "IMG") {
    context.fillStyle = canvasColor(style.backgroundColor, "#e5e7eb");
    fillRoundedRect(context, rect, Number.parseFloat(style.borderRadius) || 0);
  }

  const borderWidth = Number.parseFloat(style.borderTopWidth) || 0;
  const borderColor = canvasColor(style.borderTopColor, null);
  if (borderWidth > 0 && borderColor && !isTransparentColor(borderColor)) {
    const radius = Number.parseFloat(style.borderRadius) || 0;
    context.lineWidth = borderWidth;
    context.strokeStyle = borderColor;
    strokeRoundedRect(context, insetRect(rect, borderWidth / 2), radius);
  }
}

function drawElementContent(context, element) {
  if (element.tagName === "SVG" || element.tagName === "PATH") return;

  const text = directTextContent(element);
  if (!text) return;

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  const paddingLeft = Number.parseFloat(style.paddingLeft) || 0;
  const paddingTop = Number.parseFloat(style.paddingTop) || 0;
  const paddingRight = Number.parseFloat(style.paddingRight) || 0;
  const fontSize = Number.parseFloat(style.fontSize) || 14;
  const lineHeight = resolveLineHeight(style.lineHeight, fontSize);
  const textRect = {
    left: rect.left + paddingLeft,
    top: rect.top + paddingTop,
    width: Math.max(0, rect.width - paddingLeft - paddingRight),
    height: Math.max(0, rect.height - paddingTop),
  };

  if (textRect.width <= 0 || textRect.height <= 0) return;

  context.save();
  context.beginPath();
  context.rect(textRect.left, textRect.top, textRect.width, textRect.height);
  context.clip();
  context.fillStyle = canvasColor(style.color, "#111827");
  context.font = `${style.fontStyle} ${style.fontWeight} ${fontSize}px ${style.fontFamily}`;
  context.textBaseline = "top";

  const lines = wrapCanvasText(context, text, textRect.width);
  lines.forEach((line, index) => {
    const y = textRect.top + index * lineHeight;
    if (y + lineHeight <= 0 || y >= window.innerHeight) return;
    context.fillText(line, textRect.left, y);
  });
  context.restore();
}

function directTextContent(element) {
  return [...element.childNodes]
    .filter((node) => node.nodeType === Node.TEXT_NODE)
    .map((node) => node.textContent.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join(" ");
}

function wrapCanvasText(context, text, maxWidth) {
  const words = text.split(/\s+/);
  const lines = [];
  let line = "";

  words.forEach((word) => {
    const candidate = line ? `${line} ${word}` : word;
    if (line && context.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  });

  if (line) lines.push(line);
  return lines;
}

function resolveLineHeight(lineHeight, fontSize) {
  if (lineHeight === "normal") return fontSize * 1.25;
  return Number.parseFloat(lineHeight) || fontSize * 1.25;
}

function canvasColor(value, fallback) {
  if (!value) return fallback;
  const normalized = normalizeScreenshotColor(value.trim());
  if (normalized.includes("oklch(")) return fallback;
  return normalized;
}

function isTransparentColor(value) {
  return (
    value === "transparent" ||
    value === "rgba(0, 0, 0, 0)" ||
    value.endsWith(", 0)")
  );
}

function fillRoundedRect(context, rect, radius) {
  if (radius > 0 && context.roundRect) {
    context.beginPath();
    context.roundRect(rect.left, rect.top, rect.width, rect.height, radius);
    context.fill();
    return;
  }

  context.fillRect(rect.left, rect.top, rect.width, rect.height);
}

function strokeRoundedRect(context, rect, radius) {
  if (radius > 0 && context.roundRect) {
    context.beginPath();
    context.roundRect(rect.left, rect.top, rect.width, rect.height, radius);
    context.stroke();
    return;
  }

  context.strokeRect(rect.left, rect.top, rect.width, rect.height);
}

function insetRect(rect, inset) {
  return {
    left: rect.left + inset,
    top: rect.top + inset,
    width: Math.max(0, rect.width - inset * 2),
    height: Math.max(0, rect.height - inset * 2),
  };
}

export async function captureScreenshot() {
  if (window.isSecureContext && navigator.mediaDevices?.getDisplayMedia) {
    try {
      return {
        dataUrl: await captureScreenFrame(),
        source: "screen",
      };
    } catch (error) {
      if (error.name === "NotAllowedError") {
        throw error;
      }
    }
  }

  return {
    dataUrl: await capturePageSnapshot(),
    source: "page",
  };
}
