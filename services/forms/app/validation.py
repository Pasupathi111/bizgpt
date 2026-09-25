"""JSON Schema validation shared by prefill (partial) and submit (full)."""

from jsonschema import Draft202012Validator, FormatChecker

_format_checker = FormatChecker()


def _validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=_format_checker)


def full_errors(schema: dict, values: dict) -> list[dict]:
    """All validation errors for a complete submission, keyed by field."""
    errors = []
    for err in sorted(_validator(schema).iter_errors(values), key=lambda e: list(e.path)):
        field = '.'.join(str(p) for p in err.path)
        if not field and err.validator == 'required':
            field = err.message.split("'")[1] if "'" in err.message else ''
        errors.append({'field': field, 'message': err.message})
    return errors


def apply_prefill(schema: dict, prefill: dict) -> tuple[dict, list[dict]]:
    """
    Keep prefill values that are individually valid; reject the rest.
    Unknown fields are rejected so the LLM can't smuggle extra data in.
    """
    props = schema.get('properties', {})
    accepted, rejected = {}, []
    for name, value in (prefill or {}).items():
        if name not in props:
            rejected.append({'field': name, 'reason': 'unknown field'})
            continue
        if value in (None, ''):
            continue
        field_schema = {'$schema': schema.get('$schema'), **props[name]} if schema.get('$schema') else props[name]
        errs = list(_validator(field_schema).iter_errors(value))
        if errs:
            rejected.append({'field': name, 'reason': errs[0].message})
        else:
            accepted[name] = value
    return accepted, rejected


def missing_required(schema: dict, values: dict) -> list[str]:
    return [name for name in schema.get('required', []) if values.get(name) in (None, '', [])]


def with_defaults(schema: dict, values: dict) -> dict:
    merged = {
        name: prop['default']
        for name, prop in schema.get('properties', {}).items()
        if 'default' in prop
    }
    merged.update(values)
    return merged
