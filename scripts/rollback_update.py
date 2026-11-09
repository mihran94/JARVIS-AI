from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.updates import rollback

if __name__ == '__main__':
    if input('Select the previous code version for next startup? Type YES: ') != 'YES':
        raise SystemExit('Cancelled.')
    try:
        print(rollback(ROOT))
    except (OSError, ValueError) as error:
        print(error)
        raise SystemExit(1)
