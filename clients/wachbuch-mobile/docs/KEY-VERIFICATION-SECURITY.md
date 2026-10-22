# Key verification: trust boundaries and remaining acceptance

## Implemented contract

- Own fingerprint and QR are derived from the locally unlocked P-256 private scalar (`Q = d * G`), not server-reported fingerprints or the private JWK's claimed public coordinates. Locking the session removes the displayed own QR immediately.
- Colleague fingerprints are computed locally from canonical, on-curve P-256 public JWKs. Missing, non-canonical and off-curve keys cannot be marked verified. A reported fingerprint mismatch is diagnostic, never a trust anchor.
- Fingerprints retain the server interop contract: the first 128 bits of SHA-256 over `crv|x|y`, four groups of eight hexadecimal digits (35 display characters including spaces).
- Verification decisions are scoped by login account, exact server URL and colleague ID. Unscoped legacy decisions are discarded rather than inherited by whichever account logs in next.
- Storage operations are serialized and reload current persisted data before updating it, preventing overlapping stores from losing other accounts' decisions or resurrecting revoked decisions within this app isolate.
- Account/API changes clear visible trust state. Late loading, scanning and persistence callbacks do not update another account's sheet.
- A changed colleague key requires a new out-of-band comparison; marking it verified records the currently computed fingerprint. A QR match must identify exactly one colleague.
- A valid public key is not proof of its owner's identity. Compare fingerprints via an independently trusted channel or in person. The backend remains untrusted for key ownership.

## Reproducibility

All Flutter workflows use Flutter 3.47.7. `pub get --enforce-lockfile`, localization generation, analysis and the complete test suite must pass without changing the committed lockfile. Native Android/iOS build and dependency-security workflows remain required CI evidence; no store workflow is invoked by this change.

## Not claimed

- Real-device camera permission/scanning, cross-device QR readability and secure-storage upgrade acceptance are still external acceptance tasks; widget tests do not replace them.
- Web/PWA QR verification and persistent key-change warnings are not implemented by this client change. The server's own fingerprint display is only partial parity.
- This is not an independent cryptographic audit or a claim of constant-time private-scalar arithmetic. No change to the message encryption protocol is claimed.
- An ignored update compares the offered version, and an update dialog without a usable download target is dismissible. Launch failure/retry UX remains follow-up work.
