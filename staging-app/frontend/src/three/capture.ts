// Module-level holder for the screenshot function. SceneCanvas registers the
// real capturer (it has access to the WebGLRenderer via useThree); the
// validation flow calls captureScreenshot() from anywhere.
type Capturer = () => string | null;

let capturer: Capturer = () => null;

export function registerCapturer(fn: Capturer) {
  capturer = fn;
}

// Returns a JPEG data URL of the current render, or null if not ready.
export function captureScreenshot(): string | null {
  return capturer();
}
