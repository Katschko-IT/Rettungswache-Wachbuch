(() => {
  const doc = document;
  const root = doc.documentElement;

  function csrfToken() {
    const meta = doc.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function setStatus(el, text) {
    if (!el) {
      return;
    }
    el.hidden = !text;
    el.textContent = text || "";
  }

  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach((value) => {
      binary += String.fromCharCode(value);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function base64urlToBuffer(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/");
    const pad = "=".repeat((4 - (padded.length % 4)) % 4);
    const raw = atob(padded + pad);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      bytes[i] = raw.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function revivePublicKeyOptions(options) {
    const copy = structuredClone(options);
    copy.challenge = base64urlToBuffer(copy.challenge);
    if (copy.user && copy.user.id) {
      copy.user.id = base64urlToBuffer(copy.user.id);
    }
    if (copy.excludeCredentials) {
      copy.excludeCredentials = copy.excludeCredentials.map((item) => ({
        ...item,
        id: base64urlToBuffer(item.id),
      }));
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
      response: {},
      clientExtensionResults: credential.getClientExtensionResults(),
    };
    if (response.attestationObject) {
      raw.response = {
        clientDataJSON: bufferToBase64url(response.clientDataJSON),
        attestationObject: bufferToBase64url(response.attestationObject),
      };
    } else {
      raw.response = {
        clientDataJSON: bufferToBase64url(response.clientDataJSON),
        authenticatorData: bufferToBase64url(response.authenticatorData),
        signature: bufferToBase64url(response.signature),
        userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
      };
    }
    return raw;
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || wbT("request_failed", "Anfrage fehlgeschlagen."));
    }
    return data;
  }

  async function runPasskeyLogin(statusEl) {
    setStatus(statusEl, wbT("passkey_checking", "Passkey wird geprüft …"));
    const optionsResponse = await fetch("/anmelden/passkey/optionen/", { credentials: "same-origin" });
    if (!optionsResponse.ok) {
      throw new Error(wbT("passkey_unavailable", "Passkeys sind hier nicht verfügbar."));
    }
    const options = revivePublicKeyOptions(await optionsResponse.json());
    const credential = await navigator.credentials.get({ publicKey: options });
    const result = await postJson("/anmelden/passkey/pruefen/", {
      credential: serializeCredential(credential),
    });
    window.location.href = result.redirect || "/";
  }

  async function runPasskeyMfa(statusEl) {
    setStatus(statusEl, wbT("passkey_checking", "Passkey wird geprüft …"));
    const optionsResponse = await fetch("/anmelden/mfa/passkey/optionen/", { credentials: "same-origin" });
    if (!optionsResponse.ok) {
      throw new Error(wbT("passkey_confirm_impossible", "Passkey-Bestätigung nicht möglich."));
    }
    const options = revivePublicKeyOptions(await optionsResponse.json());
    const credential = await navigator.credentials.get({ publicKey: options });
    const result = await postJson("/anmelden/mfa/passkey/pruefen/", {
      credential: serializeCredential(credential),
    });
    window.location.href = result.redirect || "/";
  }

  async function runPasskeyRegister(statusEl) {
    setStatus(statusEl, wbT("passkey_registering", "Passkey wird registriert …"));
    const optionsResponse = await fetch("/konto/mfa/passkey/optionen/", { credentials: "same-origin" });
    if (!optionsResponse.ok) {
      throw new Error(wbT("passkey_register_impossible", "Passkey-Registrierung nicht möglich."));
    }
    const options = revivePublicKeyOptions(await optionsResponse.json());
    const credential = await navigator.credentials.create({ publicKey: options });
    await postJson("/konto/mfa/passkey/pruefen/", {
      credential: serializeCredential(credential),
      device_name: navigator.platform || "Passkey",
    });
    window.location.reload();
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      output[i] = raw.charCodeAt(i);
    }
    return output;
  }

  async function runPushSubscribe(statusEl, config) {
    setStatus(statusEl, "Berechtigung wird angefragt …");
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error(wbT("notifications_not_allowed", "Benachrichtigungen wurden nicht erlaubt."));
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.vapidPublicKey),
    });
    await postJson(config.subscribeUrl, subscription.toJSON());
    window.location.reload();
  }

  async function runPushUnsubscribe(statusEl, config) {
    setStatus(statusEl, "Push wird deaktiviert …");
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await subscription.unsubscribe();
    }
    await postJson(config.subscribeUrl, { action: "unsubscribe" });
    window.location.reload();
  }

  function setOnlineState() {
    root.dataset.connection = navigator.onLine ? "online" : "offline";
    const chip = doc.querySelector("[data-connection-chip]");
    if (!chip) {
      return;
    }
    chip.hidden = navigator.onLine;
    chip.textContent = wbT("offline_banner", "Offline – angezeigte Daten können veraltet sein");
  }

  window.addEventListener("online", setOnlineState);
  window.addEventListener("offline", setOnlineState);
  setOnlineState();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(() => {});
    });
  }

  let deferredPrompt = null;
  const installBanner = doc.querySelector("[data-install-banner]");
  const installButton = doc.querySelector("[data-install-button]");
  const dismissButton = doc.querySelector("[data-install-dismiss]");

  function hideInstallBanner() {
    if (installBanner) {
      installBanner.hidden = true;
    }
  }

  function installDismissed() {
    try {
      return Boolean(
        localStorage.getItem("rwsth-install-dismissed") ||
          localStorage.getItem("rwsth-installed")
      );
    } catch (_error) {
      return false;
    }
  }

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    // Ein einmal abgelehnter oder installierter Hinweis darf nicht bei jedem
    // Seitenaufruf erneut erscheinen.
    if (
      installBanner &&
      !installDismissed() &&
      !window.matchMedia("(display-mode: standalone)").matches
    ) {
      installBanner.hidden = false;
    }
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    hideInstallBanner();
    try {
      localStorage.setItem("rwsth-installed", "1");
    } catch (_error) {
      /* ignore quota / private mode */
    }
  });

  if (installButton) {
    installButton.addEventListener("click", async () => {
      if (!deferredPrompt) {
        return;
      }
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      hideInstallBanner();
    });
  }

  if (dismissButton) {
    dismissButton.addEventListener("click", () => {
      hideInstallBanner();
      try {
        localStorage.setItem("rwsth-install-dismissed", String(Date.now()));
      } catch (_error) {
        /* ignore */
      }
    });
  }

  try {
    if (localStorage.getItem("rwsth-install-dismissed")) {
      hideInstallBanner();
    }
  } catch (_error) {
    /* ignore */
  }

  doc.querySelectorAll("[data-clear-cache-on-submit]").forEach((form) => {
    form.addEventListener("submit", () => {
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ type: "CLEAR_CACHES" });
      }
    });
  });

  const loginBtn = doc.querySelector("[data-passkey-login]");
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const status = doc.querySelector("[data-passkey-login-status]");
      try {
        await runPasskeyLogin(status);
      } catch (error) {
        setStatus(status, error.message || wbT("passkey_login_failed", "Passkey-Anmeldung fehlgeschlagen."));
      }
    });
  }

  const mfaBtn = doc.querySelector("[data-passkey-mfa]");
  if (mfaBtn) {
    mfaBtn.addEventListener("click", async () => {
      const status = doc.querySelector("[data-passkey-mfa-status]");
      try {
        await runPasskeyMfa(status);
      } catch (error) {
        setStatus(status, error.message || wbT("passkey_confirm_failed", "Passkey-Bestätigung fehlgeschlagen."));
      }
    });
  }

  const registerBtn = doc.querySelector("[data-passkey-register]");
  if (registerBtn) {
    registerBtn.addEventListener("click", async () => {
      const status = doc.querySelector("[data-passkey-register-status]");
      try {
        await runPasskeyRegister(status);
      } catch (error) {
        setStatus(status, error.message || wbT("passkey_register_failed", "Passkey-Registrierung fehlgeschlagen."));
      }
    });
  }

  const pushConfigEl = doc.getElementById("push-config");
  if (pushConfigEl) {
    const config = JSON.parse(pushConfigEl.textContent || "{}");
    const status = doc.querySelector("[data-push-status]");
    const subscribeBtn = doc.querySelector("[data-push-subscribe]");
    const unsubscribeBtn = doc.querySelector("[data-push-unsubscribe]");
    if (subscribeBtn) {
      subscribeBtn.addEventListener("click", async () => {
        try {
          await runPushSubscribe(status, config);
        } catch (error) {
          setStatus(status, error.message || wbT("push_enable_failed", "Push konnte nicht aktiviert werden."));
        }
      });
    }
    if (unsubscribeBtn) {
      unsubscribeBtn.addEventListener("click", async () => {
        try {
          await runPushUnsubscribe(status, config);
        } catch (error) {
          setStatus(status, error.message || wbT("push_disable_failed", "Push konnte nicht deaktiviert werden."));
        }
      });
    }
  }

  const SESSION_KEY = "rwsth-e2ee-private-jwk";
  const te = new TextEncoder();
  const td = new TextDecoder();

  function bytesToB64url(bytes) {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let binary = "";
    view.forEach((value) => {
      binary += String.fromCharCode(value);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function b64urlToBytes(value) {
    return new Uint8Array(base64urlToBuffer(value));
  }

  async function deriveWrapKey(passphrase, saltB64, iterations) {
    const baseKey = await crypto.subtle.importKey("raw", te.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt: b64urlToBytes(saltB64), iterations, hash: "SHA-256" },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }

  async function generateIdentity(passphrase) {
    const pair = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    const publicJwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
    const privateJwk = await crypto.subtle.exportKey("jwk", pair.privateKey);
    const salt = bytesToB64url(crypto.getRandomValues(new Uint8Array(16)));
    // BSI TR-02102 / OWASP: PBKDF2-SHA256 with high iteration count (Web Crypto has no Argon2).
    const iterations = 600000;
    const wrapKey = await deriveWrapKey(passphrase, salt, iterations);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const wrapped = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      wrapKey,
      te.encode(JSON.stringify(privateJwk)),
    );
    return {
      public_jwk: { kty: publicJwk.kty, crv: publicJwk.crv, x: publicJwk.x, y: publicJwk.y },
      wrapped_private_jwk: `${bytesToB64url(iv)}.${bytesToB64url(new Uint8Array(wrapped))}`,
      kdf_salt: salt,
      kdf_iterations: iterations,
      private_jwk: privateJwk,
    };
  }

  async function unlockIdentity(bundle, passphrase) {
    const [ivB64, dataB64] = String(bundle.wrapped_private_jwk || "").split(".");
    if (!ivB64 || !dataB64) {
      throw new Error(wbT("key_envelope_corrupt", "Gespeicherter Schlüsselumschlag ist beschädigt."));
    }
    const wrapKey = await deriveWrapKey(passphrase, bundle.kdf_salt, bundle.kdf_iterations || 600000);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64urlToBytes(ivB64) },
      wrapKey,
      b64urlToBytes(dataB64),
    );
    const privateJwk = JSON.parse(td.decode(plain));
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(privateJwk));
    return privateJwk;
  }

  function loadSessionPrivateJwk() {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_error) {
      return null;
    }
  }

  async function importPrivateKey(jwk) {
    return crypto.subtle.importKey("jwk", jwk, { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
  }

  async function importPublicKey(jwk) {
    return crypto.subtle.importKey("jwk", jwk, { name: "ECDH", namedCurve: "P-256" }, false, []);
  }

  async function wrapKeyForRecipient(messageKeyRaw, recipientPublicJwk) {
    const ephemeral = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    const recipientKey = await importPublicKey(recipientPublicJwk);
    const bits = await crypto.subtle.deriveBits({ name: "ECDH", public: recipientKey }, ephemeral.privateKey, 256);
    const hkdfBase = await crypto.subtle.importKey("raw", bits, "HKDF", false, ["deriveKey"]);
    const aesKey = await crypto.subtle.deriveKey(
      { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(32), info: te.encode("wachbuch-e2ee-v1") },
      hkdfBase,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt"],
    );
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const wrapped = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aesKey, messageKeyRaw);
    const epk = await crypto.subtle.exportKey("jwk", ephemeral.publicKey);
    return {
      epk: { kty: epk.kty, crv: epk.crv, x: epk.x, y: epk.y },
      wrapped_key: `${bytesToB64url(iv)}.${bytesToB64url(new Uint8Array(wrapped))}`,
    };
  }

  async function unwrapMessageKey(wrap, privateJwk) {
    const privateKey = await importPrivateKey(privateJwk);
    const epk = await importPublicKey(wrap.epk);
    const bits = await crypto.subtle.deriveBits({ name: "ECDH", public: epk }, privateKey, 256);
    const hkdfBase = await crypto.subtle.importKey("raw", bits, "HKDF", false, ["deriveKey"]);
    const aesKey = await crypto.subtle.deriveKey(
      { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(32), info: te.encode("wachbuch-e2ee-v1") },
      hkdfBase,
      { name: "AES-GCM", length: 256 },
      false,
      ["decrypt"],
    );
    const [ivB64, dataB64] = String(wrap.wrapped_key || "").split(".");
    return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64urlToBytes(ivB64) }, aesKey, b64urlToBytes(dataB64));
  }

  async function encryptForRecipients(plaintext, recipients) {
    const messageKeyRaw = crypto.getRandomValues(new Uint8Array(32));
    const messageKey = await crypto.subtle.importKey("raw", messageKeyRaw, { name: "AES-GCM" }, false, ["encrypt"]);
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, messageKey, te.encode(plaintext));
    const key_wraps = {};
    for (const recipient of recipients) {
      if (!recipient.public_jwk) {
        continue;
      }
      key_wraps[String(recipient.user_id)] = await wrapKeyForRecipient(messageKeyRaw, recipient.public_jwk);
    }
    return {
      ciphertext: bytesToB64url(new Uint8Array(ciphertext)),
      nonce: bytesToB64url(nonce),
      key_wraps,
    };
  }

  async function decryptEnvelope(envelope, privateJwk) {
    if (!envelope.is_encrypted) {
      return envelope.legacy_body || "";
    }
    if (!envelope.wrap) {
      throw new Error(wbT("no_envelope", "Kein Schlüsselumschlag für dich – Nachricht nicht lesbar."));
    }
    const rawKey = await unwrapMessageKey(envelope.wrap, privateJwk);
    const messageKey = await crypto.subtle.importKey("raw", rawKey, { name: "AES-GCM" }, false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64urlToBytes(envelope.nonce) },
      messageKey,
      b64urlToBytes(envelope.ciphertext),
    );
    return td.decode(plain);
  }

  async function ensureUnlocked(statusEl) {
    let privateJwk = loadSessionPrivateJwk();
    if (privateJwk) {
      return privateJwk;
    }
    const passphrase = await window.requestCryptoUnlock();
    if (!passphrase) {
      throw new Error(wbT("unlock_cancelled", "Entsperren abgebrochen."));
    }
    const response = await fetch("/konto/crypto/bundle.json", { credentials: "same-origin" });
    const bundle = await response.json();
    if (!bundle.configured) {
      throw new Error(wbT("setup_keys_first", "Bitte zuerst unter Mein Konto Schlüssel einrichten."));
    }
    setStatus(statusEl, wbT("keys_unlocking", "Schlüssel werden entsperrt …"));
    privateJwk = await unlockIdentity(bundle, passphrase);
    setStatus(statusEl, "");
    return privateJwk;
  }

  const cryptoSetupForm = doc.querySelector("[data-crypto-setup]");
  if (cryptoSetupForm) {
    cryptoSetupForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = doc.querySelector("[data-crypto-status]");
      const passphrase = cryptoSetupForm.querySelector("[name='passphrase']").value;
      const confirm = cryptoSetupForm.querySelector("[name='passphrase2']").value;
      if (passphrase.length < 10) {
        setStatus(status, wbT("passphrase_too_short", "Passphrase mindestens 10 Zeichen."));
        return;
      }
      if (passphrase !== confirm) {
        setStatus(status, wbT("passphrases_mismatch", "Passphrasen stimmen nicht überein."));
        return;
      }
      try {
        setStatus(status, wbT("keys_generating", "Schlüssel werden erzeugt …"));
        const identity = await generateIdentity(passphrase);
        await postJson("/konto/crypto/", {
          public_jwk: identity.public_jwk,
          wrapped_private_jwk: identity.wrapped_private_jwk,
          kdf_salt: identity.kdf_salt,
          kdf_iterations: identity.kdf_iterations,
          replace: cryptoSetupForm.dataset.replace === "1",
        });
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(identity.private_jwk));
        window.location.reload();
      } catch (error) {
        setStatus(status, error.message || wbT("key_setup_failed", "Schlüsselsetup fehlgeschlagen."));
      }
    });
  }

  const cryptoUnlockForm = doc.querySelector("[data-crypto-unlock]");
  if (cryptoUnlockForm) {
    cryptoUnlockForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = doc.querySelector("[data-crypto-status]");
      try {
        const bundleResponse = await fetch("/konto/crypto/bundle.json", { credentials: "same-origin" });
        const bundle = await bundleResponse.json();
        await unlockIdentity(bundle, cryptoUnlockForm.querySelector("[name='passphrase']").value);
        setStatus(status, wbT("keys_unlocked", "Schlüssel entsperrt."));
        window.location.reload();
      } catch (error) {
        setStatus(status, error.message || wbT("unlock_failed", "Entsperren fehlgeschlagen."));
      }
    });
  }

  async function renderEncryptedFeed(rootEl, feed, privateJwk) {
    for (const item of feed) {
      const bodyEl = rootEl.querySelector(`[data-msg-body="${item.id}"]`);
      if (!bodyEl) {
        continue;
      }
      try {
        bodyEl.textContent = await decryptEnvelope(item, privateJwk);
      } catch (_error) {
        bodyEl.textContent = item.is_encrypted
          ? wbT("encrypted_unreadable", "Verschlüsselt – nicht entschlüsselbar (fehlende Schlüssel).")
          : (item.legacy_body || "");
      }
    }
  }

  const chatRoot = doc.querySelector("[data-e2ee-chat]");
  if (chatRoot) {
    const status = chatRoot.querySelector("[data-crypto-status]");
    const feed = JSON.parse(chatRoot.querySelector("[data-feed-json]").textContent || "[]");
    const members = JSON.parse(chatRoot.querySelector("[data-members-json]").textContent || "[]");
    const compose = chatRoot.querySelector("[data-e2ee-compose]");
    (async () => {
      try {
        if (!chatRoot.dataset.hasKeys) {
          return;
        }
        const privateJwk = await ensureUnlocked(status);
        await renderEncryptedFeed(chatRoot, feed, privateJwk);
      } catch (error) {
        setStatus(status, error.message || wbT("decrypt_failed", "Entschlüsseln fehlgeschlagen."));
      }
    })();
    if (compose) {
      compose.addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = compose.querySelector("[name='body']");
        const text = (input.value || "").trim();
        if (!text) {
          return;
        }
        try {
          const privateJwk = await ensureUnlocked(status);
          const recipients = members.filter((item) => item.has_keys && item.public_jwk);
          if (!recipients.length) {
            throw new Error(wbT("no_keyed_colleagues", "Noch keine Kollegen mit Schlüsseln."));
          }
          // Ensure self is included for later reading.
          const payload = await encryptForRecipients(text, recipients);
          await postJson(window.location.pathname, payload);
          window.location.reload();
        } catch (error) {
          setStatus(status, error.message || wbT("send_failed", "Senden fehlgeschlagen."));
        }
      });
    }
  }

  const privateRoot = doc.querySelector("[data-e2ee-private]");
  if (privateRoot) {
    const status = privateRoot.querySelector("[data-crypto-status]");
    const feed = JSON.parse(privateRoot.querySelector("[data-feed-json]").textContent || "[]");
    const peers = JSON.parse(privateRoot.querySelector("[data-members-json]").textContent || "[]");
    const compose = privateRoot.querySelector("[data-e2ee-compose]");
    (async () => {
      try {
        const privateJwk = await ensureUnlocked(status);
        await renderEncryptedFeed(privateRoot, feed, privateJwk);
      } catch (error) {
        setStatus(status, error.message || wbT("decrypt_failed", "Entschlüsseln fehlgeschlagen."));
      }
    })();
    if (compose) {
      compose.addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = compose.querySelector("[name='body']");
        const text = (input.value || "").trim();
        if (!text) {
          return;
        }
        try {
          await ensureUnlocked(status);
          const recipients = peers.filter((item) => item.has_keys && item.public_jwk);
          const payload = await encryptForRecipients(text, recipients);
          await postJson(window.location.pathname, payload);
          window.location.reload();
        } catch (error) {
          setStatus(status, error.message || wbT("send_failed", "Senden fehlgeschlagen."));
        }
      });
    }
  }

  const mailRoot = doc.querySelector("[data-e2ee-mail]");
  if (mailRoot) {
    const status = mailRoot.querySelector("[data-crypto-status]");
    const colleagues = JSON.parse(mailRoot.querySelector("[data-members-json]").textContent || "[]");
    const compose = mailRoot.querySelector("[data-e2ee-mail-compose]");
    if (compose) {
      compose.addEventListener("submit", async (event) => {
        event.preventDefault();
        const subject = (compose.querySelector("[name='subject']").value || "").trim();
        const body = (compose.querySelector("[name='body']").value || "").trim();
        const selected = [...compose.querySelectorAll("[name='recipient_ids']:checked")].map((el) => Number(el.value));
        if (!selected.length || !body) {
          setStatus(status, wbT("recipient_and_text_required", "Empfänger und Text sind nötig."));
          return;
        }
        try {
          const privateJwk = await ensureUnlocked(status);
          const viewerId = Number(mailRoot.dataset.viewerId);
          const recipients = colleagues.filter((item) => selected.includes(item.user_id) && item.public_jwk);
          const self = colleagues.find((item) => item.user_id === viewerId);
          // Always wrap for sender + recipients; sender public key from bundle.
          const bundle = await (await fetch("/konto/crypto/bundle.json", { credentials: "same-origin" })).json();
          const allRecipients = [
            ...recipients,
            { user_id: viewerId, public_jwk: bundle.public_jwk, has_keys: true },
          ];
          const payload = await encryptForRecipients(JSON.stringify({ subject, body }), allRecipients);
          payload.recipient_ids = selected;
          const result = await postJson(window.location.pathname, payload);
          window.location.href = result.redirect || window.location.pathname;
          void privateJwk;
          void self;
        } catch (error) {
          setStatus(status, error.message || wbT("send_failed", "Senden fehlgeschlagen."));
        }
      });
    }
  }

  const mailDetail = doc.querySelector("[data-e2ee-mail-detail]");
  if (mailDetail) {
    const status = mailDetail.querySelector("[data-crypto-status]");
    const envelope = JSON.parse(mailDetail.querySelector("[data-envelope-json]").textContent || "{}");
    (async () => {
      try {
        const privateJwk = await ensureUnlocked(status);
        const plain = await decryptEnvelope(envelope, privateJwk);
        const parsed = JSON.parse(plain);
        mailDetail.querySelector("[data-mail-subject]").textContent = parsed.subject || "(ohne Betreff)";
        mailDetail.querySelector("[data-mail-body]").textContent = parsed.body || "";
      } catch (error) {
        setStatus(status, error.message || wbT("mail_undecryptable", "Mail nicht entschlüsselbar."));
      }
    })();
  }

  const demoDeck = doc.querySelector("[data-demo-deck]");
  if (demoDeck) {
    const slides = [...demoDeck.querySelectorAll("[data-demo-slide]")];
    const prevBtn = demoDeck.querySelector("[data-demo-prev]");
    const nextBtn = demoDeck.querySelector("[data-demo-next]");
    const musicBtn = demoDeck.querySelector("[data-demo-music]");
    const countEl = demoDeck.querySelector("[data-demo-count]");
    const bar = demoDeck.querySelector("[data-demo-bar]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const autoplay = new URLSearchParams(window.location.search).get("autoplay") === "1" && !reduceMotion;
    const AUTO_MS = 6200;
    let index = 0;
    let timer = null;
    let audioCtx = null;
    let masterGain = null;
    let padOsc = null;
    let phraseTimer = null;
    let playing = false;

    function show(nextIndex) {
      index = (nextIndex + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => {
        const on = slideIndex === index;
        slide.classList.toggle("is-on", on);
        slide.setAttribute("aria-hidden", on ? "false" : "true");
      });
      demoDeck.setAttribute("data-demo-index", String(index));
      if (countEl) {
        countEl.textContent = `${index + 1} / ${slides.length}`;
      }
    }

    function armAuto() {
      window.clearInterval(timer);
      if (autoplay) {
        timer = window.setInterval(() => {
          show(index + 1);
        }, AUTO_MS);
      }
    }

    function startPhrase() {
      if (!audioCtx || !masterGain || !playing) {
        return;
      }
      const seq = [261.63, 329.63, 392, 440, 392, 329.63];
      seq.forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.value = 0;
        osc.connect(gain);
        gain.connect(masterGain);
        const t0 = audioCtx.currentTime + idx * 0.95;
        gain.gain.setValueAtTime(0, t0);
        gain.gain.linearRampToValueAtTime(0.18, t0 + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, t0 + 1.4);
        osc.start(t0);
        osc.stop(t0 + 1.5);
      });
    }

    function startMusic() {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor || playing) {
        return;
      }
      audioCtx = audioCtx || new AudioContextCtor();
      masterGain = audioCtx.createGain();
      masterGain.gain.value = 0.07;
      masterGain.connect(audioCtx.destination);
      const notes = [196, 246.94, 293.66, 329.63, 392, 329.63, 293.66, 246.94];
      notes.forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.value = 0;
        osc.connect(gain);
        gain.connect(masterGain);
        const t0 = audioCtx.currentTime + idx * 0.85;
        gain.gain.setValueAtTime(0, t0);
        gain.gain.linearRampToValueAtTime(0.22, t0 + 0.12);
        gain.gain.exponentialRampToValueAtTime(0.001, t0 + 1.6);
        osc.start(t0);
        osc.stop(t0 + 1.7);
      });
      padOsc = audioCtx.createOscillator();
      const padGain = audioCtx.createGain();
      padOsc.type = "triangle";
      padOsc.frequency.value = 98;
      padGain.gain.value = 0.04;
      padOsc.connect(padGain);
      padGain.connect(masterGain);
      padOsc.start();
      playing = true;
      if (musicBtn) {
        musicBtn.setAttribute("aria-pressed", "true");
      }
      phraseTimer = window.setInterval(startPhrase, 6800);
    }

    function stopMusic() {
      playing = false;
      window.clearInterval(phraseTimer);
      phraseTimer = null;
      if (padOsc) {
        try {
          padOsc.stop();
        } catch (_error) {
          /* already stopped */
        }
        padOsc.disconnect();
        padOsc = null;
      }
      if (masterGain) {
        masterGain.disconnect();
        masterGain = null;
      }
      if (audioCtx) {
        audioCtx.close();
        audioCtx = null;
      }
      if (musicBtn) {
        musicBtn.setAttribute("aria-pressed", "false");
      }
    }

    demoDeck.classList.add("is-js");
    if (bar) {
      bar.hidden = false;
    }
    show(0);
    armAuto();

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        show(index - 1);
        armAuto();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        show(index + 1);
        armAuto();
      });
    }
    if (musicBtn) {
      musicBtn.addEventListener("click", () => {
        if (playing) {
          stopMusic();
          return;
        }
        if (audioCtx && audioCtx.state === "suspended") {
          audioCtx.resume();
        }
        startMusic();
      });
    }
    doc.addEventListener("keydown", (event) => {
      const tag = event.target && event.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        show(index + 1);
        armAuto();
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        show(index - 1);
        armAuto();
      }
    });
  }

  doc.addEventListener("click", (event) => {
    const btn = event.target.closest && event.target.closest(".copy-iban");
    if (!btn) {
      return;
    }
    const el = doc.getElementById(btn.dataset.target);
    if (!el) {
      return;
    }
    const text = el.textContent.trim().replace(/\s+/g, "");
    navigator.clipboard.writeText(text).then(() => {
      const old = btn.textContent;
      btn.textContent = wbT("copied", "Kopiert");
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = old;
        btn.classList.remove("copied");
      }, 2000);
    });
  });
})();

/* Sortierbare Listen (Einstellungen → Darstellung): Maus-Drag und Pfeiltasten. */
(() => {
  const lists = document.querySelectorAll("[data-sortable]");
  if (!lists.length) return;

  lists.forEach((list) => {
    const output = document.querySelector(
      `[data-sortable-output="${list.dataset.input}"]`
    );
    const sync = () => {
      if (!output) return;
      output.value = [...list.children]
        .map((item) => item.dataset.key)
        .filter(Boolean)
        .join(",");
    };

    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-move]");
      if (!button) return;
      const item = button.closest("li");
      if (!item) return;
      if (button.dataset.move === "up" && item.previousElementSibling) {
        list.insertBefore(item, item.previousElementSibling);
      } else if (button.dataset.move === "down" && item.nextElementSibling) {
        list.insertBefore(item.nextElementSibling, item);
      }
      sync();
    });

    let dragged = null;
    list.addEventListener("dragstart", (event) => {
      dragged = event.target.closest("li");
      if (dragged) dragged.classList.add("is-dragging");
    });
    list.addEventListener("dragend", () => {
      if (dragged) dragged.classList.remove("is-dragging");
      dragged = null;
      sync();
    });
    list.addEventListener("dragover", (event) => event.preventDefault());
    list.addEventListener("drop", (event) => {
      event.preventDefault();
      const target = event.target.closest("li");
      if (!target || !dragged || target === dragged) return;
      const rect = target.getBoundingClientRect();
      const after = event.clientY - rect.top > rect.height / 2;
      list.insertBefore(dragged, after ? target.nextSibling : target);
      sync();
    });

    sync();
  });
})();
