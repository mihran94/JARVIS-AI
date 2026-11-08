import sys

if sys.version_info < (3, 12):
    raise SystemExit('JARVIS requires Python 3.12 or newer. Python 3.12 is recommended.')

from desktop.app import main

if __name__ == '__main__':
    raise SystemExit(main())
