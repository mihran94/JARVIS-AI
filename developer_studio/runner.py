"""Experimental Docker-only runner. No host Python execution fallback."""
from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

MAX_OUTPUT = 65536


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunResult:
    status: str
    exit_code: int | None
    output: str


def approval_digest(source, image):
    return hashlib.sha256((image + '\0' + source).encode('utf-8')).hexdigest()


def container_args(name, image):
    return ['create', '--name', name, '--interactive', '--pull=never',
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--user=65534:65534',
            '--memory=256m', '--memory-swap=256m', '--cpus=1', '--pids-limit=32',
            '--ulimit=cpu=5:5', '--ulimit=nofile=64:64', '--log-driver=none',
            '--tmpfs=/tmp:rw,noexec,nosuid,size=16m', '--workdir=/tmp',
            '--entrypoint=/usr/local/bin/python', image, '-I', '-B', '-u', '-']


def run_python(source, image, approved_digest, cancelled=lambda: False):
    if not source.strip() or len(source.encode('utf-8')) > 200000:
        raise RunnerError('Source must contain 1 to 200,000 UTF-8 bytes.')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise RunnerError('Select an already installed, trusted Python 3.12 image by its sha256 image ID.')
    if approved_digest != approval_digest(source, image):
        raise RunnerError('Approval does not match this source and image.')
    if cancelled():
        return RunResult('cancelled', None, '')
    docker = shutil.which('docker')
    if not docker:
        raise RunnerError('Docker is unavailable. Code was not run on the host.')
    host = 'npipe:////./pipe/docker_engine' if os.name == 'nt' else 'unix:///var/run/docker.sock'
    # Ignore saved contexts, remote endpoints, TLS selectors and client proxy defaults.
    env = {k: v for k, v in os.environ.items() if not k.startswith('DOCKER_')}
    name = 'jarvis-run-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='jarvis-docker-') as config:
        base = [docker, '--config', config, '--host', host]
        def command(args):
            return subprocess.run(base + args, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=10, check=False, env=env, shell=False)
        try:
            info = command(['image', 'inspect', image])
            if info.returncode:
                raise RunnerError('Image unavailable or local Docker daemon not ready. No image is downloaded automatically.')
            data = json.loads(info.stdout)[0]
            if data.get('Os') != 'linux' or data.get('Config', {}).get('Volumes'):
                raise RunnerError('A Linux Python image without declared volumes is required.')
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
            raise RunnerError('Could not verify the local Docker image.') from None
        if cancelled():
            return RunResult('cancelled', None, '')
        process = None
        try:
            created = command(container_args(name, image))
            if created.returncode:
                raise RunnerError('Docker refused the restricted container configuration.')
            if cancelled():
                return RunResult('cancelled', None, '')
            process = subprocess.Popen(base + ['start', '--attach', '--interactive', name],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env, shell=False, bufsize=0)
            output = bytearray()
            overflow = threading.Event()
            io_failed = threading.Event()
            def read():
                try:
                    while True:
                        part = process.stdout.read(4096)
                        if not part:
                            break
                        remaining = MAX_OUTPUT - len(output)
                        output.extend(part[:remaining])
                        if len(part) > remaining:
                            overflow.set()
                            break
                except OSError:
                    io_failed.set()
            def write():
                try:
                    pending = memoryview(source.encode('utf-8'))
                    while pending:
                        written = process.stdin.write(pending)
                        if not written:
                            raise OSError('Container input closed.')
                        pending = pending[written:]
                    process.stdin.close()
                except (OSError, ValueError):
                    io_failed.set()
            reader = threading.Thread(target=read, daemon=True)
            writer = threading.Thread(target=write, daemon=True)
            reader.start(); writer.start()
            deadline = time.monotonic() + 20
            status = None
            while True:
                if cancelled():
                    status = 'cancelled'; break
                if overflow.is_set():
                    status = 'output_limit'; break
                if time.monotonic() >= deadline:
                    status = 'timeout'; break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            if status:
                process.kill()
            process.wait(timeout=5)
            reader.join(timeout=1)
            writer.join(timeout=1)
            if reader.is_alive() or writer.is_alive():
                status = status or 'io_error'
            if overflow.is_set():
                status = status or 'output_limit'
            if io_failed.is_set():
                status = status or 'io_error'
            status = status or ('completed' if process.returncode == 0 else 'failed')
            return RunResult(status, process.returncode, output.decode('utf-8', errors='replace'))
        except (OSError, subprocess.TimeoutExpired):
            raise RunnerError('Docker execution failed or timed out.') from None
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            try:
                removed = command(['rm', '--force', name])
                if removed.returncode:
                    raise RunnerError('Container cleanup could not be confirmed: ' + name)
            except (OSError, subprocess.TimeoutExpired):
                raise RunnerError('Container cleanup timed out; check local Docker for ' + name) from None
