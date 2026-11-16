import sys

if sys.version_info < (3, 12):
    raise SystemExit('JARVIS requires Python 3.12 or newer. Python 3.12 is recommended.')

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--hud':
        try:
            from quantum_core.launcher import main as hud_main
        except ImportError:
            raise SystemExit(
                'Install the HUD dependencies with '
                'python -m pip install -r quantum_core/requirements.txt.'
            ) from None
        del sys.argv[1]
        return hud_main()
    from desktop.app import main as desktop_main
    return desktop_main()


if __name__ == '__main__':
    raise SystemExit(main())
