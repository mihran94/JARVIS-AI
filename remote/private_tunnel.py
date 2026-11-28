"""Validate the installed Tailscale Serve route before enabling loopback HTTP."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit


def private_origin(config):
    if (not isinstance(config, dict) or config.get('AllowFunnel')
            or config.get('TCP', {}).get('443', {}).get('HTTPS') is not True):
        raise ValueError('Configure private Tailscale HTTPS Serve on port 443 first.')
    origins = []
    for host, site in config.get('Web', {}).items():
        url = urlsplit('https://' + host)
        if (url.hostname and url.hostname.endswith('.ts.net') and url.port == 443
                and not url.username and not url.password and not url.path
                and site.get('Handlers', {}).get('/', {}).get('Proxy') == 'http://127.0.0.1:8765'):
            origins.append('https://' + url.hostname)
    if len(origins) != 1:
        raise ValueError('Private Tailscale Serve must proxy HTTPS to http://127.0.0.1:8765.')
    return origins[0]


def discover_private_origin():
    executable = shutil.which('tailscale')
    if not executable:
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale/tailscale.exe'
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        raise ValueError('Tailscale is not installed. Connect this PC to your private tailnet first.')
    try:
        result = subprocess.run([executable, 'serve', 'status', '--json'],
                                capture_output=True, text=True, timeout=5, check=True,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return private_origin(json.loads(result.stdout))
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        raise ValueError('Could not verify the private Tailscale HTTPS route.') from None
