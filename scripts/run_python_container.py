"""Explicit CLI approval gate for the experimental Docker runner."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from developer_studio.runner import approval_digest, run_python, RunnerError


def main():
    parser = argparse.ArgumentParser(description='Run one reviewed Python file inside local Docker only.')
    parser.add_argument('source', type=Path)
    parser.add_argument('--image', required=True, help='Trusted installed Python 3.12 sha256 image ID')
    parser.add_argument('--approve', help='Exact digest printed by a review invocation')
    args = parser.parse_args()
    try:
        with args.source.open('rb') as file:
            raw = file.read(200001)
        if len(raw) > 200000:
            raise RunnerError('Source exceeds 200,000 bytes.')
        source = raw.decode('utf-8')
        digest = approval_digest(source, args.image)
        if not args.approve:
            print('Review the source file and trusted image before executing. No code has run.')
            print('Approval digest: ' + digest)
            print('Rerun with --approve DIGEST only if you approve this exact source and image.')
            return 2
        result = run_python(source, args.image, args.approve)
        print('Status: ' + result.status)
        print('Exit code: ' + str(result.exit_code))
        print('--- Untrusted program output ---')
        # Escape terminal control sequences from generated programs.
        print(''.join(c if c in '\n\t' or c.isprintable() else '?' for c in result.output))
        return 0 if result.status == 'completed' else 1
    except (RunnerError, OSError, UnicodeError) as error:
        print(str(error) if isinstance(error, RunnerError) else 'Cannot read a UTF-8 source file.')
        return 1
    except KeyboardInterrupt:
        print('Interrupted. Container cleanup was requested.')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
