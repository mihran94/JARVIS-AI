"""Local device actions invoked from the Quantum Core Device controls."""
from hashlib import sha256
import os
import re
from pathlib import Path
import subprocess
import sys
from time import monotonic


POWER_PLANS = {
    'balanced': ('Balanced', '381b4222-f694-41f0-9685-ff5bb260df2e'),
    'saver': ('Power Saver', 'a1841308-3541-4fab-bc81-f71556f20b4a'),
    'high': ('High Performance', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'),
}
APP_LINKS = {
    'phone-link': ('Phone Link', 'ms-phone:'),
    'whatsapp': ('WhatsApp', 'whatsapp:'),
}
DEVICE_ACTIONS = frozenset({'camera', 'camera-sources', 'brightness', 'power-plan', 'kali', *APP_LINKS})
CAMERA_SECONDS = 8
CAMERA_RESULTS = {
    'face': 'Face detected in the camera preview.',
    'clear': 'Scan complete. No face was detected.',
    'missing-opencv': 'Install requirements-device.txt to use the face preview.',
    'source-missing': 'The selected camera is no longer available. Reconnect it and refresh camera sources.',
    'unavailable': 'The camera could not be read. Check the webcam and Windows camera permissions.',
}


class DeviceError(RuntimeError):
    """An action could not be completed."""


def system_executable(name):
    return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / name)


def set_brightness(level):
    if type(level) is not int or not 10 <= level <= 100:
        raise DeviceError('Choose a brightness from 10 to 100 percent.')
    try:
        import screen_brightness_control as brightness
    except ImportError:
        raise DeviceError('Install requirements-device.txt to change display brightness.') from None
    try:
        brightness.set_brightness(level)
        readings = brightness.get_brightness()
    except Exception:
        raise DeviceError('Brightness control could not verify the display setting.') from None
    if not readings:
        raise DeviceError('The displays did not report their brightness.')
    return 'Reported display brightness: ' + ', '.join(f'{reading}%' for reading in readings) + '.'


def set_power_plan(plan):
    if not isinstance(plan, str) or plan not in POWER_PLANS:
        raise DeviceError('Choose Balanced, Power Saver, or High Performance.')
    label, guid = POWER_PLANS[plan]
    program = system_executable('powercfg.exe')
    try:
        subprocess.run([program, '/setactive', guid], check=True, capture_output=True, timeout=8)
        active = subprocess.run([program, '/getactivescheme'], check=True, capture_output=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        raise DeviceError(f'Windows could not activate or verify {label}. Check available power plans.') from None
    if guid.encode('ascii') not in active.stdout.lower().replace(b'\x00', b''):
        raise DeviceError(f'Windows did not report {label} as active.')
    return f'Windows power plan: {label}.'


def open_kali():
    program = system_executable('wsl.exe')
    try:
        available = subprocess.run(
            [program, '--list', '--quiet'], check=True, capture_output=True, timeout=8,
        )
        output = available.stdout.replace(b'\x00', b'').decode('utf-8', errors='replace')
        if not any(line.strip() == 'kali-linux' for line in output.splitlines()):
            raise DeviceError('The kali-linux distribution is not installed in WSL.')
        subprocess.Popen([program, '--distribution', 'kali-linux'],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    except (OSError, subprocess.SubprocessError):
        raise DeviceError('Windows could not open the installed Kali WSL console.') from None
    return 'Kali WSL console launch requested.'


def windows_camera_sources():
    """Return named OpenCV capture options with stable identifiers for this enumeration."""
    try:
        import cv2
        from cv2_enumerate_cameras import enumerate_cameras
    except ImportError:
        raise DeviceError('Install requirements-device.txt to list camera sources.') from None

    sources = {}
    try:
        for backend, label in ((cv2.CAP_DSHOW, 'DirectShow'), (cv2.CAP_MSMF, 'Media Foundation')):
            for info in enumerate_cameras(backend):
                key = sha256(f'{backend}:{info.index}:{info.name}:{info.path}'.encode('utf-8')).hexdigest()
                sources[key] = {
                    'name': f'{info.name} ({label})',
                    'index': info.index,
                    'backend': backend,
                }
    except (OSError, RuntimeError, NotImplementedError):
        raise DeviceError('Windows could not list cameras. Reconnect the phone or webcam and retry.') from None
    return sources


def scan_camera(source=None):
    if source is not None and (not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{64}', source)):
        raise DeviceError('Choose a camera from the source list.')
    command = [sys.executable, str(Path(__file__).resolve()), '--camera-preview']
    if source is not None:
        command.append(source)
    try:
        result = subprocess.run(
            command,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
        )
    except subprocess.TimeoutExpired:
        raise DeviceError('The camera did not respond in time. The preview process was closed.') from None
    except OSError:
        raise DeviceError('Windows could not start the camera preview.') from None
    lines = result.stdout.splitlines()
    key = lines[-1].strip() if lines else ''
    if result.returncode != 0 or key not in CAMERA_RESULTS:
        raise DeviceError(CAMERA_RESULTS['unavailable'])
    if key not in ('face', 'clear'):
        raise DeviceError(CAMERA_RESULTS[key])
    return CAMERA_RESULTS[key]


def camera_preview(source=None):
    try:
        import cv2
    except ImportError:
        return 'missing-opencv'
    title = 'JARVIS camera preview - press Q or Esc to close'
    capture_args = (0,)
    if source is not None:
        try:
            selected = windows_camera_sources().get(source)
        except DeviceError:
            return 'source-missing'
        if selected is None:
            return 'source-missing'
        capture_args = (selected['index'], selected['backend'])
    camera = cv2.VideoCapture(*capture_args)
    shown = False
    detected = False
    try:
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / 'haarcascade_frontalface_default.xml'))
        if not camera.isOpened() or cascade.empty():
            return 'unavailable'
        stop_at = monotonic() + CAMERA_SECONDS
        while monotonic() < stop_at:
            ok, frame = camera.read()
            if not ok:
                return 'unavailable'
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
            for x, y, width, height in faces:
                cv2.rectangle(frame, (x, y), (x + width, y + height), (255, 243, 0), 2)
                detected = True
            cv2.imshow(title, frame)
            shown = True
            if (cv2.waitKey(1) & 0xff) in (ord('q'), 27):
                break
            try:
                visible = cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE)
            except cv2.error:
                break
            if visible < 1:
                break
        return 'face' if detected else 'clear'
    finally:
        camera.release()
        if shown:
            cv2.destroyAllWindows()


def run_device_action(action, value=None):
    if sys.platform != 'win32':
        raise DeviceError('These device controls run on Windows.')
    if action == 'brightness':
        return set_brightness(value)
    if action == 'power-plan':
        return set_power_plan(value)
    if action == 'camera':
        return scan_camera(value)
    if value is not None:
        raise DeviceError('This action takes no arguments.')
    if action == 'camera-sources':
        return [{'id': key, 'name': item['name']} for key, item in windows_camera_sources().items()]
    if action == 'kali':
        return open_kali()
    if action in APP_LINKS:
        label, link = APP_LINKS[action]
        try:
            os.startfile(link)
        except OSError:
            raise DeviceError(f'Windows could not open {label}. Check that the app is installed.') from None
        return f'{label} launch requested. Choose the contact in the app.'
    raise DeviceError('Unknown device action.')


if __name__ == '__main__' and len(sys.argv) in (2, 3) and sys.argv[1] == '--camera-preview':
    print(camera_preview(sys.argv[2] if len(sys.argv) == 3 else None))
