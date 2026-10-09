"""Native storage boundary; this does not confer project or execution authority."""
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission

TABLE_SUFFIXES = {'.csv', '.xls', '.xlsx'}


def invalid_reference(message):
    raise ValidationError({'error': message, 'error_code': 'managed_storage_reference_invalid'})


def managed_path(value, *, table=False):
    """Resolve a managed reference without opening it or disclosing host paths."""
    if not isinstance(value, str) or not value or len(value) > 4096 or '\x00' in value or '\\' in value:
        invalid_reference('Supply a valid managed storage reference.')
    path = Path(value)
    if '..' in path.parts:
        invalid_reference('Parent traversal is not allowed.')
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        resolved = (path if path.is_absolute() else root / path).resolve()
    except (OSError, RuntimeError, ValueError):
        invalid_reference('The storage reference cannot be resolved safely.')
    if not resolved.is_relative_to(root) or resolved == root:
        invalid_reference('The file must be inside managed artifact storage.')
    relative = resolved.relative_to(root)
    raw_relative = path.relative_to(root) if path.is_absolute() and path.is_relative_to(root) else path
    if any(part.startswith('.') for part in relative.parts + raw_relative.parts if part not in ('/', '.')):
        invalid_reference('Hidden storage references are not allowed.')
    if table and resolved.suffix.lower() not in TABLE_SUFFIXES:
        invalid_reference('Select a managed CSV or Excel table.')
    if resolved.exists() and not resolved.is_file():
        invalid_reference('The storage reference must identify a regular file.')
    return str(resolved)


def positive_file_id(value):
    if type(value) is int:
        result = value
    elif isinstance(value, str) and 1 <= len(value) <= 19 and value.isascii() and value.isdecimal() and value == str(int(value)):
        result = int(value)
    else:
        invalid_reference('file_id must be a canonical positive integer.')
    if not 0 < result <= 2**63 - 1:
        invalid_reference('file_id must be a canonical positive integer.')
    return result


class ManagedRequestReferences(BasePermission):
    """Validate request selectors before native handlers touch storage."""
    def has_permission(self, request, view):
        identifiers = []
        if view.kwargs.get('file_id') is not None:
            identifiers.append(positive_file_id(view.kwargs['file_id']))
        sources = [request.query_params]
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            sources.append(request.data)
        for values in sources:
            if not hasattr(values, 'get'):
                continue  # Handler owns the existing non-object payload error.
            if hasattr(values, 'getlist') and len(values.getlist('file_id')) > 1:
                invalid_reference('Supply file_id once.')
            if values.get('file_id') is not None:
                identifiers.append(positive_file_id(values['file_id']))
            for name in ('processed_file', 'file_override'):
                if values.get(name):
                    managed_path(values[name], table=True)
            if values.get('model_path'):
                managed_path(values['model_path'])
        if len(set(identifiers)) > 1:
            invalid_reference('Route, query and body file_id must agree.')
        return True
