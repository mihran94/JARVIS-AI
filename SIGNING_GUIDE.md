# Jarvis-Blue digital signatures

## What is implemented
Two independent workflows are included:
1. Ed25519 signed update manifests, verified against public keys bundled with the installed app. Missing/unrecognized keys, missing/incorrect signatures, expired manifests and version downgrades are refused. The signature binds the format, version, download URL, archive SHA-256, release notes, expiry and key ID. The staged archive is hashed again and re-extracted before installation.
2. A Windows Authenticode release script for an existing EXE/MSI/DLL. It selects an owner-supplied certificate from CurrentUser/My, requires Code Signing usage and a valid trusted certificate chain, signs with SHA-256 and an RFC3161 timestamp, then verifies both trust and the expected publisher thumbprint.

No production private key, publisher certificate, signed executable or published signed update has been created by this change. Production update trust starts empty and updates fail closed until owner setup is complete. The app remains usable; updating requires activation. No executable build was run. Ed25519 update keys do not establish a Windows publisher identity.

## One-time owner update-key setup on Windows
Run in the project directory with its virtual environment. Choose a dedicated key directory outside this project, for example `%USERPROFILE%\JarvisBlueSigning`:

```bat
.venv\Scripts\python.exe tools\update_keys.py generate "%USERPROFILE%\JarvisBlueSigning"
.venv\Scripts\python.exe tools\update_keys.py pin "%USERPROFILE%\JarvisBlueSigning\update-public.json"
```

The first command asks for a new password twice. It creates an encrypted PKCS8 private PEM and public JSON. Passwords are never command-line arguments. The second copies only the public key into `core/update_trust.json`. Commit/push only that public trust file. Ship that pinned public key in the initial trusted app distribution before enabling remote updates. Keep the private PEM, password and a secure offline recovery copy outside GitHub, the project and chat uploads. File permissions on Windows depend on the directory ACL; use a directory restricted to your Windows account. The script does not change Windows trust stores or ACLs.

This setup is intentionally owner-operated: a private key created in a temporary remote workspace would not be an appropriate long-term signing identity. Never use the ephemeral keys created by tests for production. Lost keys cannot be recovered; rotation requires a deliberate release signed by an existing trusted key or an independently verified manual reinstall. The pin command refuses to overwrite existing trust.

## Signing a source update later
Only when an authorized release is ready:

1. Prepare a source archive and unsigned `latest.json` with `tools/prepare_source_release.py` as described in UPDATE_GUIDE.md.
2. Edit release notes before signing. Verify the ZIP contains no secrets and includes the expected public-key configuration.
3. Run:

```bat
.venv\Scripts\python.exe tools\sign_update.py release-output\latest.json --private-key "%USERPROFILE%\JarvisBlueSigning\update-private.pem" --days 14
```

4. Verify using the same trusted key configuration:

```bat
.venv\Scripts\python.exe -c "import json; from core.release_security import verify; verify(json.load(open('release-output/latest.json'))); print('Signature valid')"
```

5. Publish the unmodified signed JSON and matching ZIP. Renew the signed manifest before it expires if it must remain available; never edit signed fields after signing. A signature proves possession of the pinned private key, not that a release is bug-free. Protect the initial distribution and private key. A compromised local Windows account can replace app code or its trusted key; this mechanism does not protect against a compromised host. The updater is a compact application-specific design, not a full TUF implementation.

The repository is private. The current HTTPS downloader has no private GitHub authentication flow; signed private releases still need a supported authenticated delivery mechanism or separately accessible release hosting. Do not place tokens in release URLs. No feed URL has been enabled by this change.

## Windows publisher signing later
A trusted Windows publisher signature requires a valid code-signing certificate and access to its private key through the Windows certificate store/provider. A locally generated self-signed certificate does not automatically become trusted on other computers. This change does not buy a certificate or enroll a service. Obtain a certificate for the publisher's validated identity; the issuer determines the subject shown by Windows. Do not promise an arbitrary publisher name or that SmartScreen warnings will disappear.

On the Windows signing machine install the official Windows SDK SignTool, configure the certificate/provider, and sign an already-built artifact:

```powershell
.\tools\windows\Sign-WindowsRelease.ps1 `
  -ArtifactPath "C:\Release\Jarvis-Blue.exe" `
  -CertificateThumbprint "YOUR_40_HEX_CERTIFICATE_THUMBPRINT" `
  -TimestampUrl "https://YOUR_CERTIFICATE_PROVIDER_RFC3161_ENDPOINT" `
  -SignToolPath "C:\Program Files (x86)\Windows Kits\10\bin\SDK_VERSION\x64\signtool.exe"
```

Replace all placeholders. Never upload a PFX/private key to chat or commit it. Timestamping transmits the signature digest to the selected timestamp service. Sign the app binary before assembling an installer, then sign the final installer separately. Hardware-backed certificate providers may show their own PIN/authorization prompt. Changes to the artifact after signing invalidate the signature. This script supports a certificate exposed in CurrentUser/My; other signing services/KSP setups may need a provider-specific adapter.

## Validation and remaining activation
Thirteen updater/security tests pass, using temporary test keys only. All Python sources parse. Tests cover signed install/restore, private data preservation, invalid/missing signature, unknown/empty trust, expired manifest, signed downgrade, staged-archive/pending-manifest tampering, unsafe paths, checksum and rollback on copy failure. Test environment cryptography is 50.0.0; the existing app requirements specify >=42,<50, so testing with the installed supported application dependency set remains required. Windows PowerShell, SignTool, certificate-store operations, actual Authenticode signing and Windows UI remain untested here.

Production activation needs the owner's locally generated public trust file and a real Windows publisher certificate. Those items are not fabricated or silently replaced with test credentials.

References:
- https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/
- https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
