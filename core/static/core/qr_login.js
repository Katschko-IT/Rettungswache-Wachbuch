/**
 * QR-Login client implementation.
 * CSP compliant, no inline scripts, textContent for all dynamic text.
 */
(function () {
  "use strict";

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    const match = document.cookie.match(/(?:^|;)\s*rwsth_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function base64urlToBuffer(base64url) {
    const padding = "=".repeat((4 - (base64url.length % 4)) % 4);
    const base64 = (base64url + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray.buffer;
  }

  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (let i = 0; i < bytes.length; i++) {
      str += String.fromCharCode(bytes[i]);
    }
    return window.btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  function revivePublicKeyOptions(raw) {
    const copy = { ...raw };
    if (copy.challenge) {
      copy.challenge = base64urlToBuffer(copy.challenge);
    }
    if (copy.allowCredentials) {
      copy.allowCredentials = copy.allowCredentials.map((item) => ({
        ...item,
        id: base64urlToBuffer(item.id),
      }));
    }
    return copy;
  }

  function serializeCredential(credential) {
    const response = credential.response;
    const raw = {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(response.clientDataJSON),
        authenticatorData: bufferToBase64url(response.authenticatorData),
        signature: bufferToBase64url(response.signature),
        userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
      },
      clientExtensionResults: credential.getClientExtensionResults ? credential.getClientExtensionResults() : {},
    };
    return raw;
  }

  async function postJson(url, payload, extraHeaders = {}) {
    const headers = {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
      "X-Requested-With": "XMLHttpRequest",
      ...extraHeaders,
    };
    const response = await fetch(url, {
      method: "POST",
      headers,
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    return { status: response.status, ok: response.ok, data };
  }

  // --- Warteseite Controller ---
  function initWaitPage(container) {
    const startUrl = container.getAttribute("data-start-url") || "/anmelden/qr/start/";
    const imgEl = container.querySelector("[data-qr-image]");
    const placeholderEl = container.querySelector("[data-qr-placeholder]");
    const checkWordEl = container.querySelector("[data-check-word]");
    const manualCodeEl = container.querySelector("[data-manual-code]");
    const countdownEl = container.querySelector("[data-countdown]");
    const statusMsgEl = container.querySelector("[data-status-message]");
    const retryBtn = container.querySelector("[data-retry-button]");

    let currentLoginId = null;
    let currentSecret = null;
    let pollInterval = null;
    let countdownInterval = null;
    let remainingSeconds = 120;

    function setStatus(text, className = "") {
      if (statusMsgEl) {
        statusMsgEl.textContent = text;
        statusMsgEl.className = "qr-status-region " + className;
      }
    }

    function stopTimers() {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
      if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
      }
    }

    function startCountdown(seconds) {
      remainingSeconds = seconds;
      if (countdownEl) {
        countdownEl.textContent = String(remainingSeconds);
      }
      countdownInterval = setInterval(() => {
        remainingSeconds -= 1;
        if (countdownEl) {
          countdownEl.textContent = String(Math.max(0, remainingSeconds));
        }
        if (remainingSeconds <= 0) {
          stopTimers();
          setStatus("QR-Code ist abgelaufen. Bitte erneuern.", "status-expired");
          if (retryBtn) {
            retryBtn.hidden = false;
          }
        }
      }, 1000);
    }

    async function pollStatus() {
      if (!currentLoginId || !currentSecret) {
        return;
      }
      const statusUrl = `/anmelden/qr/${currentLoginId}/status/`;
      try {
        const res = await postJson(statusUrl, {}, { "X-QR-Secret": currentSecret });
        if (!res.ok) {
          if (res.status === 429) {
            return; // Rate limited, wait for next tick
          }
          if (res.status === 410) {
            stopTimers();
            setStatus("QR-Code ist abgelaufen.", "status-expired");
            if (retryBtn) retryBtn.hidden = false;
            return;
          }
          return;
        }

        const state = res.data.state;
        if (state === "approved") {
          stopTimers();
          setStatus("Anmeldung freigegeben! Anmeldung wird abgeschlossen …", "status-approved");
          await performExchange();
        } else if (state === "denied") {
          stopTimers();
          setStatus("Anmeldung wurde auf dem Mobilgerät abgelehnt.", "status-denied");
          if (retryBtn) retryBtn.hidden = false;
        } else if (state === "expired") {
          stopTimers();
          setStatus("QR-Code ist abgelaufen.", "status-expired");
          if (retryBtn) retryBtn.hidden = false;
        } else if (state === "revoked") {
          stopTimers();
          setStatus("Anmeldung wurde widerrufen.", "status-denied");
          if (retryBtn) retryBtn.hidden = false;
        }
      } catch (err) {
        // Network hiccup, keep polling
      }
    }

    async function performExchange() {
      const exchangeUrl = `/anmelden/qr/${currentLoginId}/exchange/`;
      try {
        const res = await postJson(exchangeUrl, { qr_secret: currentSecret }, { "X-QR-Secret": currentSecret });
        if (res.ok && res.data.ok && res.data.redirect) {
          window.location.href = res.data.redirect;
        } else {
          setStatus("Anmeldung konnte nicht abgeschlossen werden.", "status-error");
          if (retryBtn) retryBtn.hidden = false;
        }
      } catch (err) {
        setStatus("Verbindungsfehler beim Austausch.", "status-error");
        if (retryBtn) retryBtn.hidden = false;
      }
    }

    async function startSession() {
      stopTimers();
      if (retryBtn) retryBtn.hidden = true;
      if (imgEl) imgEl.hidden = true;
      if (placeholderEl) {
        placeholderEl.hidden = false;
        placeholderEl.textContent = "QR-Code wird erzeugt …";
      }
      setStatus("Warte auf Initialisierung …");

      try {
        const res = await postJson(startUrl, {});
        if (!res.ok || !res.data.ok) {
          setStatus("QR-Login konnte nicht gestartet werden.", "status-error");
          if (retryBtn) retryBtn.hidden = false;
          return;
        }

        const data = res.data;
        currentLoginId = data.login_id;
        // Extract secret from qr_url fragment
        const secretMatch = data.qr_url.match(/#secret=([^&]+)/);
        currentSecret = secretMatch ? decodeURIComponent(secretMatch[1]) : "";

        if (imgEl && data.qr_image) {
          imgEl.src = data.qr_image;
          imgEl.hidden = false;
          if (placeholderEl) placeholderEl.hidden = true;
        }
        if (checkWordEl) {
          checkWordEl.textContent = data.check_word;
        }
        if (manualCodeEl) {
          manualCodeEl.textContent = data.manual_code;
        }

        setStatus("Warte auf Bestätigung durch das Smartphone …");
        startCountdown(data.expires_in || 120);

        // Poll every 1000ms
        pollInterval = setInterval(pollStatus, 1000);
      } catch (err) {
        setStatus("Verbindungsfehler beim Start.", "status-error");
        if (retryBtn) retryBtn.hidden = false;
      }
    }

    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        startSession();
      });
    }

    startSession();
  }

  // --- Bestätigungsseite Controller ---
  function initConfirmPage(container) {
    const loginId = container.getAttribute("data-login-id");
    const secretInput = container.querySelector("[data-qr-secret-input]");
    const manualContainer = container.querySelector("[data-manual-code-container]");
    const passkeyBtn = container.querySelector("[data-qr-passkey-button]");
    const passkeyStatus = container.querySelector("[data-qr-passkey-status]");
    const countdownEl = container.querySelector("[data-countdown]");

    // Extract secret from URL hash: #secret=...
    const hash = window.location.hash || "";
    const match = hash.match(/secret=([^&]+)/);
    let secret = match ? decodeURIComponent(match[1]) : "";

    if (secret && secretInput) {
      secretInput.value = secret;
      if (manualContainer) {
        manualContainer.hidden = true;
      }
    } else {
      if (manualContainer && container.getAttribute("data-manual-granted") !== "1") {
        manualContainer.hidden = false;
      }
    }

    // Countdown
    let remaining = parseInt(countdownEl ? countdownEl.getAttribute("data-countdown") || "120" : "120", 10);
    const timer = setInterval(() => {
      remaining -= 1;
      if (countdownEl) {
        countdownEl.textContent = String(Math.max(0, remaining));
      }
      if (remaining <= 0) {
        clearInterval(timer);
        const approveBtn = container.querySelector("[data-approve-button]");
        if (approveBtn) {
          approveBtn.disabled = true;
          approveBtn.textContent = "Abgelaufen";
        }
      }
    }, 1000);

    // Passkey Re-auth on confirm page
    if (passkeyBtn) {
      passkeyBtn.addEventListener("click", async () => {
        const optionsUrl = passkeyBtn.getAttribute("data-options-url");
        const verifyUrl = passkeyBtn.getAttribute("data-verify-url");
        if (passkeyStatus) {
          passkeyStatus.textContent = "Passkey wird abgefragt …";
          passkeyStatus.hidden = false;
        }
        try {
          const optRes = await postJson(optionsUrl, {});
          if (!optRes.ok) {
            throw new Error("Passkey-Optionen nicht verfügbar.");
          }
          const options = revivePublicKeyOptions(optRes.data);
          const credential = await navigator.credentials.get({ publicKey: options });
          const serialized = serializeCredential(credential);
          const verRes = await postJson(verifyUrl, { credential: serialized });
          if (!verRes.ok || !verRes.data.ok) {
            throw new Error("Passkey-Prüfung fehlgeschlagen.");
          }
          if (passkeyStatus) {
            passkeyStatus.textContent = "Passkey erfolgreich geprüft. Bitte Freigabe absenden.";
          }
          passkeyBtn.disabled = true;
          passkeyBtn.textContent = "Passkey verifiziert ✓";
        } catch (err) {
          if (passkeyStatus) {
            passkeyStatus.textContent = err.message || "Passkey-Prüfung abgebrochen.";
          }
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const waitContainer = document.querySelector("[data-qr-wait-container]");
    if (waitContainer) {
      initWaitPage(waitContainer);
    }
    const confirmPanel = document.querySelector("[data-qr-confirm-panel]");
    if (confirmPanel) {
      initConfirmPage(confirmPanel);
    }
  });
})();
