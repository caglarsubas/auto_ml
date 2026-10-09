"""Trusted installation administrator CLI; never called by an MCP client."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from access_control.authority import actor_snapshot, grant_snapshot
from access_control.models import MCPAccessEvent, MCPDatasetGrant
from declaration.models import Declaration


class Command(BaseCommand):
    help = 'Grant/revoke a named local MCP actor access to one dataset; requires trusted database administration.'

    def add_arguments(self, parser):
        parser.add_argument('--actor', required=True)
        parser.add_argument('--file-id', required=True, type=int)
        parser.add_argument('--role', choices=['read', 'prepare'])
        parser.add_argument('--expires-at')
        parser.add_argument('--revoke', action='store_true')

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options['actor'], is_active=True)
            dataset = Declaration.objects.get(pk=options['file_id'])
        except (get_user_model().DoesNotExist, Declaration.DoesNotExist) as exc:
            raise CommandError('Select an active existing actor and dataset.') from exc
        expires = parse_datetime(options['expires_at']) if options['expires_at'] else None
        if options['expires_at'] and (not expires or timezone.is_naive(expires) or expires <= timezone.now()):
            raise CommandError('Expiry must be a future ISO-8601 timestamp with a UTC offset.')
        if not options['revoke'] and not options['role']:
            raise CommandError('Supply --role read/prepare or --revoke.')
        with transaction.atomic():
            grant = MCPDatasetGrant.objects.select_for_update().filter(actor=actor, dataset=dataset).first()
            if options['revoke']:
                if not grant:
                    raise CommandError('No grant exists to revoke.')
                grant.active = False
            else:
                grant = grant or MCPDatasetGrant(actor=actor, dataset=dataset)
                grant.role, grant.active, grant.expires_at = options['role'], True, expires
            grant.save()
            MCPAccessEvent.objects.create(actor=actor, grant=grant, actor_snapshot=actor_snapshot(actor),
                grant_snapshot=grant_snapshot(grant), file_id=dataset.pk, operation='grant_changed',
                tool_name='mcp_dataset_grant', authority_source='trusted_local_cli',
                outcome='completed', finished_at=timezone.now())
        self.stdout.write(f'MCP grant {grant.pk}: actor_id={actor.pk}, file_id={dataset.pk}, active={grant.active}, role={grant.role}')
