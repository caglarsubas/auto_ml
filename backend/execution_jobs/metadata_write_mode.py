"""Read the actual metadata connection modes without probing writes."""

from django.db import connection


class MetadataWriteModeMismatch(Exception):
    pass


def check_metadata_write_mode():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pg_catalog.current_setting('transaction_read_only'),
                pg_catalog.current_setting('default_transaction_read_only')
        """)
        row = cursor.fetchone()
    if row != ("off", "off"):
        raise MetadataWriteModeMismatch
