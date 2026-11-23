"""Create or reset the single LeadPilot local operator (interactive terminal)."""
import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from leadpilot_ai.auth_api import create_operator


def main():
    parser = argparse.ArgumentParser(description='Create/reset local LeadPilot admin login')
    parser.add_argument('--reset', action='store_true', help='Reset existing account password and revoke sessions')
    args = parser.parse_args()
    print('LeadPilot AI local operator setup. Password input is hidden.')
    username = input('Username: ').strip()
    password = getpass.getpass('Password (12–128 characters): ')
    confirmation = getpass.getpass('Confirm password: ')
    if password != confirmation:
        print('ERROR: Passwords do not match.', file=sys.stderr)
        return 1
    try:
        result = create_operator(username, password, reset=args.reset)
    except ValueError as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1
    print('SUCCESS:', result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
