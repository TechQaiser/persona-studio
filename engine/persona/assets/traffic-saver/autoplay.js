// Persona traffic saver: stop video and audio that start without a click.
//
// Muted autoplay (feeds, ads, background video) is allowed by every browser's
// own policy, and it's where most of a metered proxy's video traffic goes.
// This pauses any media element that starts playing while the page has no
// fresh user activation, so a click or key press on a player still plays it.
//
// It only listens and pauses: no built-in function is replaced, so nothing
// the page can inspect looks patched. The same file runs as the content
// script of the bundled extension (CloakBrowser) and as an init script
// (Playwright, Patchright).
(() => {
  const Media = HTMLMediaElement;
  const pause = Media.prototype.pause;
  const activation = navigator.userActivation;
  addEventListener("play", (event) => {
    const el = event.target;
    if (el instanceof Media && !(activation && activation.isActive)) pause.call(el);
  }, true);
})();
