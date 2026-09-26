"""
Form type registry: one JSON file per form type.

Built-in types come from FORMS_CONFIG_DIR (read-only, in git). Custom types are
created at runtime through the API (Form Builder) and stored in FORMS_CUSTOM_DIR.
"""

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field


class ActionSpec(BaseModel):
    # record: store only and issue a reference number
    # webhook: POST {form_type, form_id, values, context} to url
    # dify_workflow: run a Dify workflow with the values as inputs
    type: str = 'record'
    reference_prefix: str = 'REF'
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    dify_base_url_env: str = 'DIFY_BASE_URL'
    dify_api_key_env: str | None = None
    dify_app_id: str | None = None


class FormType(BaseModel):
    id: str
    title: str
    description: str = ''
    keywords: list[str] = Field(default_factory=list)
    json_schema: dict = Field(alias='schema')
    ui_schema: dict = Field(default_factory=dict)
    action: ActionSpec = Field(default_factory=ActionSpec)
    submit_label: str = 'Review'
    success_message: str = 'Submitted. Reference {reference}.'

    model_config = {'populate_by_name': True}

    def fields(self) -> list[dict]:
        """Flat field summary for the LLM (top-level properties)."""
        required = set(self.json_schema.get('required', []))
        out = []
        for name, prop in self.json_schema.get('properties', {}).items():
            field = {
                'name': name,
                'title': prop.get('title', name),
                'type': prop.get('type', 'string'),
                'required': name in required,
            }
            for key in ('description', 'enum', 'format', 'pattern', 'default', 'minimum', 'maximum'):
                if key in prop:
                    field[key] = prop[key]
            out.append(field)
        return out


FORM_TYPE_ID = re.compile(r'^[a-z][a-z0-9_]{2,49}$')
# Custom forms may only record. webhook/dify actions name URLs and env vars, which must stay admin-on-disk only.
CUSTOM_ACTION_TYPES = {'record'}


class FormTypeError(ValueError):
    pass


def parse_form_type(data: dict) -> FormType:
    form_type = FormType.model_validate(data)
    Draft202012Validator.check_schema(form_type.json_schema)
    if form_type.json_schema.get('type') != 'object':
        raise FormTypeError('schema must be a JSON object schema')
    return form_type


class Registry:
    def __init__(self, config_dir: str, custom_dir: str | None = None):
        self.config_dir = Path(config_dir)
        self.custom_dir = Path(custom_dir) if custom_dir else None
        self.types: dict[str, FormType] = {}
        self.sources: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        types, sources = {}, {}
        for path in sorted(self.config_dir.glob('*.json')):
            try:
                form_type = parse_form_type(json.loads(path.read_text()))
            except FormTypeError as e:
                raise ValueError(f'{path.name}: {e}') from e
            types[form_type.id] = form_type
            sources[form_type.id] = 'builtin'
        if self.custom_dir and self.custom_dir.is_dir():
            for path in sorted(self.custom_dir.glob('*.json')):
                try:
                    form_type = parse_form_type(json.loads(path.read_text()))
                except Exception:
                    continue  # one bad custom file must not take the service down
                if form_type.id not in types:
                    types[form_type.id] = form_type
                    sources[form_type.id] = 'custom'
        self.types, self.sources = types, sources

    def save_custom(self, data: dict) -> FormType:
        if not self.custom_dir:
            raise FormTypeError('custom form types are not enabled (FORMS_CUSTOM_DIR)')
        form_type_id = str(data.get('id', ''))
        if not FORM_TYPE_ID.match(form_type_id):
            raise FormTypeError('id must be 3-50 chars: lowercase letters, digits, underscores; start with a letter')
        if self.sources.get(form_type_id) == 'builtin':
            raise FormTypeError(f'{form_type_id!r} is a built-in form type and cannot be changed here')
        form_type = parse_form_type(data)
        if form_type.action.type not in CUSTOM_ACTION_TYPES:
            raise FormTypeError(f'custom form types support action types: {sorted(CUSTOM_ACTION_TYPES)}')
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        path = self.custom_dir / f'{form_type_id}.json'
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(form_type.model_dump(by_alias=True), indent=2, ensure_ascii=False))
        tmp.replace(path)
        self.types[form_type_id] = form_type
        self.sources[form_type_id] = 'custom'
        return form_type

    def delete_custom(self, form_type_id: str) -> None:
        if self.sources.get(form_type_id) != 'custom':
            raise FormTypeError(f'{form_type_id!r} is not a custom form type')
        (self.custom_dir / f'{form_type_id}.json').unlink(missing_ok=True)
        self.types.pop(form_type_id, None)
        self.sources.pop(form_type_id, None)

    def get(self, form_type_id: str) -> FormType | None:
        return self.types.get(form_type_id)
