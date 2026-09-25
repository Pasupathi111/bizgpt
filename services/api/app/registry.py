import json
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class DifySpec(BaseModel):
    base_url_env: str = 'DIFY_BASE_URL'
    api_key_env: str = ''
    app_id: str = ''
    app_mode: str = 'workflow'
    response_mode: str = 'blocking'


class InputSpec(BaseModel):
    source: str = 'dify_parameters'
    json_schema: dict = Field(default_factory=dict, alias='schema')
    ui_schema: dict = Field(default_factory=dict)

    model_config = {'populate_by_name': True}


class ExecutionSpec(BaseModel):
    requires_confirmation: bool = False
    expose_as_form: bool = True
    expose_as_tool: bool = True


class AccessSpec(BaseModel):
    allowed_groups: list[str] = Field(default_factory=list)


class WorkflowEntry(BaseModel):
    id: str
    name: str
    description: str = ''
    tags: list[str] = Field(default_factory=list)
    provider: str = 'dify'
    dify: DifySpec
    input: InputSpec = Field(default_factory=InputSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    access: AccessSpec = Field(default_factory=AccessSpec)

    def configured(self) -> bool:
        config = self.configuration()
        return config['configured']

    def configuration(self) -> dict:
        matched_app = self._matched_dify_app()
        env_base_url = os.getenv(self.dify.base_url_env, '').strip()
        env_api_key = os.getenv(self.dify.api_key_env, '').strip() if self.dify.api_key_env else ''
        app_base_url = str(matched_app.get('base_url') or '').strip() if matched_app else ''
        app_api_key = str(matched_app.get('api_key') or '').strip() if matched_app else ''

        base_url = env_base_url or app_base_url
        api_key = env_api_key or app_api_key
        base_url_source = 'env' if env_base_url else 'dify_apps' if app_base_url else 'missing'
        api_key_source = 'env' if env_api_key else 'dify_apps' if app_api_key else 'missing'

        missing: list[str] = []
        if not base_url:
            missing.append(self.dify.base_url_env or 'DIFY_BASE_URL')
        if not api_key:
            if self.dify.api_key_env:
                missing.append(f'{self.dify.api_key_env} or DIFY_APPS[{self._app_lookup_label()}].api_key')
            else:
                missing.append(f'DIFY_APPS[{self._app_lookup_label()}].api_key')

        if base_url_source == 'env' and api_key_source == 'env':
            source = 'env'
        elif base_url_source == 'dify_apps' and api_key_source == 'dify_apps':
            source = 'dify_apps'
        elif base_url and api_key:
            source = 'mixed'
        else:
            source = 'unconfigured'

        return {
            'configured': bool(base_url and api_key),
            'source': source,
            'base_url': base_url,
            'api_key': api_key,
            'base_url_source': base_url_source,
            'api_key_source': api_key_source,
            'matched_app': {
                'id': matched_app.get('id'),
                'name': matched_app.get('name'),
                'type': matched_app.get('type'),
            }
            if matched_app
            else None,
            'missing': missing,
        }

    def _matched_dify_app(self) -> dict | None:
        candidates = {value for value in (_canonical_id(self.id), _canonical_id(self.name), _canonical_id(self.dify.app_id)) if value}
        expected_mode = _canonical_id(self.dify.app_mode)
        for app in _dify_apps():
            app_type = _canonical_id(str(app.get('type') or ''))
            if app_type and expected_mode and app_type != expected_mode:
                continue
            app_candidates = {
                value for value in (_canonical_id(str(app.get('id') or '')), _canonical_id(str(app.get('name') or ''))) if value
            }
            if candidates & app_candidates:
                return app
        return None

    def _app_lookup_label(self) -> str:
        return self.dify.app_id or self.id or self.name


class RegistryFile(BaseModel):
    version: int = 1
    workflows: list[WorkflowEntry] = Field(default_factory=list)


class WorkflowRegistry:
    def __init__(self, path: str):
        self.path = Path(path)
        self.file = RegistryFile()
        self.by_id: dict[str, WorkflowEntry] = {}
        self.reload()

    def reload(self):
        raw = yaml.safe_load(self.path.read_text()) if self.path.exists() else {'version': 1, 'workflows': []}
        self.file = RegistryFile.model_validate(raw or {'version': 1, 'workflows': []})
        self.by_id = {workflow.id: workflow for workflow in self.file.workflows}

    def list(self) -> list[WorkflowEntry]:
        return list(self.by_id.values())

    def get(self, workflow_id: str) -> WorkflowEntry | None:
        return self.by_id.get(workflow_id)


def _canonical_id(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', value.lower())


def _dify_apps() -> list[dict]:
    raw = os.getenv('DIFY_APPS', '').strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
