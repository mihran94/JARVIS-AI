# Local network diagnostics

In the Windows desktop app, open **Command Center → Local network diagnostics**.
In Quantum Core, open **Camera & Windows devices** and choose a report.

- **Cached neighbors** reads the OS IPv4 neighbor cache. It may omit devices
  the PC has not exchanged traffic with.
- **TCP listeners** shows listening sockets on this PC. Reachability depends
  on the Windows firewall and network configuration.
- **Established TCP** shows connections visible to the current permissions.

Reports are requested from buttons and displayed in the local interface.
They are not included in AI requests or saved to logging history.
