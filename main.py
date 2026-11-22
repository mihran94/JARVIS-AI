import sys

if sys.version_info < (3, 12):
    raise SystemExit('JARVIS requires Python 3.12 or newer. Python 3.12 is recommended.')

def main():
    if '--hud' in sys.argv[1:]:
        sys.argv.remove('--hud')  # Existing Windows shortcuts open the premium desktop.
    from desktop.app import main as desktop_main
    return desktop_main()


if __name__ == '__main__':
    raise SystemExit(main())
