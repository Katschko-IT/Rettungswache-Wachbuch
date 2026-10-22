(() => {
  "use strict";

  const dialogRoot = document.getElementById("dialog-root");
  const setup = document.getElementById("setup");
  if (!dialogRoot) return;

  let returnFocus = null;
  const objectUrls = new Set();
  const nativeCreateObjectURL = URL.createObjectURL.bind(URL);
  const nativeRevokeObjectURL = URL.revokeObjectURL.bind(URL);

  URL.createObjectURL = (object) => {
    const url = nativeCreateObjectURL(object);
    objectUrls.add(url);
    return url;
  };

  URL.revokeObjectURL = (url) => {
    objectUrls.delete(url);
    nativeRevokeObjectURL(url);
  };

  function cleanupObjectUrls() {
    for (const url of objectUrls) nativeRevokeObjectURL(url);
    objectUrls.clear();
  }

  function focusables(dialog) {
    return [...dialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )].filter((node) => !node.hasAttribute("hidden") && node.getClientRects().length);
  }

  function focusDialog() {
    if (dialogRoot.classList.contains("app-hidden")) return;
    const dialog = dialogRoot.querySelector('[role="dialog"]');
    if (!dialog) return;
    const heading = dialog.querySelector("h1, h2, h3");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    } else {
      dialog.setAttribute("tabindex", "-1");
      dialog.focus({ preventScroll: true });
    }
  }

  document.addEventListener(
    "click",
    (event) => {
      const opener = event.target.closest("[data-detail], [data-defect]");
      if (opener) returnFocus = opener;
    },
    true,
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (dialogRoot.classList.contains("app-hidden")) return;
      const dialog = dialogRoot.querySelector('[role="dialog"]');
      if (!dialog) return;

      if (event.key === "Tab") {
        const items = focusables(dialog);
        if (!items.length) {
          event.preventDefault();
          dialog.focus();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }

      if (event.key === "Escape") {
        queueMicrotask(() => {
          if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
        });
      }
    },
    true,
  );

  const observer = new MutationObserver(() => {
    if (!dialogRoot.classList.contains("app-hidden") && dialogRoot.querySelector('[role="dialog"]')) {
      requestAnimationFrame(focusDialog);
      return;
    }
    if (returnFocus?.isConnected) {
      requestAnimationFrame(() => returnFocus?.focus({ preventScroll: true }));
    }
  });
  observer.observe(dialogRoot, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class"],
  });

  if (setup) {
    new MutationObserver(() => {
      if (!setup.classList.contains("app-hidden") && returnFocus?.isConnected) {
        returnFocus = null;
      }
    }).observe(setup, { attributes: true, attributeFilter: ["class"] });
  }

  window.addEventListener("pagehide", cleanupObjectUrls, { once: true });
})();
