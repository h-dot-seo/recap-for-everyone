"""Resolve supported source identity fields without guessing or rewriting them."""


def _optional_identity(value):
    # Preserve the importers' existing missing/null/empty-string fallback. Other
    # falsey values (0, False, empty containers) are malformed, not missing IDs.
    if value is None or isinstance(value, str) and value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('source identity fields must be text, null or absent')
    return value


def aliased_identity(record, alias):
    primary = _optional_identity(record.get('id'))
    secondary = _optional_identity(record.get(alias))
    if primary is not None and secondary is not None and primary != secondary:
        raise ValueError('conflicting source identity aliases')
    identity = primary if primary is not None else secondary
    if identity is None:
        raise ValueError('source identity requires nonempty text')
    return identity


def optional_message_identity(payload):
    return _optional_identity(payload.get('id'))
