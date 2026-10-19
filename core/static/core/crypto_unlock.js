(() => {
  "use strict";

  const dialog = document.getElementById("crypto-unlock-dialog");
  const form = document.getElementById("crypto-unlock-form");
  const input = document.getElementById("crypto-unlock-input");
  const errorEl = document.getElementById("crypto-unlock-error");
  const cancelBtn = document.getElementById("crypto-unlock-cancel");
  const submitBtn = document.getElementById("crypto-unlock-submit");

  if (!dialog || !form || !input || !errorEl || !cancelBtn || !submitBtn) {
    return;
  }

  let pendingResolve = null;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = !message;
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }

  function reset() {
    input.value = "";
    showError("");
    submitBtn.disabled = false;
    submitBtn.textContent = wbT("unlock", "Entsperren");
  }

  function close(reason) {
    if (dialog.open) {
      dialog.close(reason || "cancel");
    }
  }

  function focusInput() {
    window.requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  }

  dialog.addEventListener("close", () => {
    const resolve = pendingResolve;
    pendingResolve = null;
    if (resolve) {
      resolve(dialog.returnValue === "submit" ? input.value : null);
    }
  });

  cancelBtn.addEventListener("click", () => {
    close("cancel");
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!input.value) {
      showError(wbT("passphrase_required", "Bitte Passphrase eingeben."));
      input.focus();
      return;
    }
    dialog.returnValue = "submit";
    close("submit");
  });

  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelBtn.click();
    }
  });

  window.requestCryptoUnlock = function promptCryptoUnlock() {
    if (pendingResolve) {
      return Promise.resolve(null);
    }
    reset();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    focusInput();
    return new Promise((resolve) => {
      pendingResolve = resolve;
    });
  };
})();
