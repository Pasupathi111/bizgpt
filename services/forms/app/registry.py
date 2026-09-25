"""Form type registry: one JSON file per form type in FORMS_CONFIG_DIR."""

import json
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


class Registry:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.types: dict[str, FormType] = {}
        self.reload()

    def reload(self) -> None:
        types = {}
        for path in sorted(self.config_dir.glob('*.json')):
            form_type = FormType.model_validate(json.loads(path.read_text()))
            Draft202012Validator.check_schema(form_type.json_schema)
            if form_type.json_schema.get('type') != 'object':
                raise ValueError(f'{path.name}: schema must be a JSON object schema')
            types[form_type.id] = form_type
        self.types = types

    def get(self, form_type_id: str) -> FormType | None:
        return self.types.get(form_type_id)
