# Remote execution safety gate (integration prototype)

4 tests pass locally. This gate is a policy helper only, not an OS sandbox and not yet connected to the JARVIS server or Android client.

Call `require_remote_execution_authorization` **before** forwarding a remote coding command to any runner. All inputs must be independently verified by the Windows host, never trusted from the Android request payload. `isolation_verified` must only be true after a real OS-enforced restricted worker/container with network and filesystem limits is established. Do not accept a boolean asserted by a client. The gate is not sufficient alone: add per-request binding, anti-replay, expirations, revocation, scoped paths, audit and platform tests.

Do not merge the MiniMax SandboxRunner as a remotely exposed tool until enforcement exists.
