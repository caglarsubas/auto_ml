#!/usr/bin/env python3
"""Create a non-admin account only in an explicitly disposable test installation."""
import os
import sys
from pathlib import Path


def main():
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise SystemExit('Set DECLARAI_TEST_INSTALLATION=1 only for a disposable test database.')
    username = os.environ.get('E2E_USER', '')
    password = os.environ.get('E2E_PASSWORD', '')
    if not username or not password:
        raise SystemExit('E2E_USER and E2E_PASSWORD are required; no default credentials exist.')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.db import transaction
    with transaction.atomic():
        users = get_user_model().objects
        if users.filter(username=username).exists():
            raise SystemExit('The test account already exists; existing users are never modified.')
        users.create_user(username=username, password=password, is_staff=False, is_superuser=False)
    print('Created a disposable, non-admin E2E account.')


if __name__ == '__main__':
    main()
