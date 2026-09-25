import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

DB_PATH = Path(os.getenv('AUTOMATION_DB_PATH', '/data/executions.jsonl'))

app = FastAPI(title='BizGPT Automation', version='1.0.0')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_executions() -> list[dict]:
    if not DB_PATH.exists():
        return []
    return [json.loads(line) for line in DB_PATH.read_text().splitlines() if line.strip()]


def append_execution(data: dict) -> dict:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    execution = {
        'execution_id': f'exec_{secrets.token_hex(4)}',
        'status': 'completed',
        'received_at': now_iso(),
        **data,
    }
    with DB_PATH.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(execution) + '\n')
    return execution


@app.get('/health')
def health():
    return {'status': 'ok', 'executions': len(read_executions())}


@app.post('/webhooks/leads')
async def receive_leads(request: Request):
    payload = await request.json()
    outputs = payload.get('outputs') or {}
    generated_leads = outputs.get('generated_leads') or []
    execution = append_execution(
        {
            'kind': 'lead_generation',
            'source': {
                'form_type': payload.get('form_type'),
                'form_id': payload.get('form_id'),
                'reference': payload.get('reference'),
                'workflow_run_id': payload.get('workflow_run_id'),
            },
            'company_name': payload.get('values', {}).get('company_name'),
            'campaign_goal': payload.get('values', {}).get('campaign_goal'),
            'lead_count': len(generated_leads),
            'generated_leads': generated_leads,
            'recommended_sequence': outputs.get('recommended_sequence') or [],
            'next_action': outputs.get('next_action'),
            'market_summary': outputs.get('market_summary'),
            'values': payload.get('values') or {},
        }
    )
    return {
        'status': 'accepted',
        'execution_id': execution['execution_id'],
        'execution_url': f'http://localhost:8091/executions/{execution["execution_id"]}',
        'saved_leads': execution['lead_count'],
        'message': f'Stored {execution["lead_count"]} generated leads for follow-up.',
    }


@app.get('/api/executions')
def list_executions(limit: int = 20):
    executions = list(reversed(read_executions()))
    return executions[: max(1, min(limit, 100))]


@app.get('/api/executions/{execution_id}')
def get_execution(execution_id: str):
    for execution in reversed(read_executions()):
        if execution.get('execution_id') == execution_id:
            return execution
    raise HTTPException(404, 'execution not found')


@app.get('/executions/{execution_id}')
def execution_page(execution_id: str):
    execution = get_execution(execution_id)
    leads = execution.get('generated_leads') or []
    sequence = execution.get('recommended_sequence') or []
    rows = ''.join(
        f"""
        <tr>
          <td>{lead.get('name', '')}</td>
          <td>{lead.get('title', '')}</td>
          <td>{lead.get('email', '')}</td>
          <td>{lead.get('score', '')}</td>
        </tr>
        """
        for lead in leads
    )
    steps = ''.join(f'<li>{item}</li>' for item in sequence)
    html = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Automation Execution {execution_id}</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 0; background: #f7f7fb; color: #111827; }}
          .wrap {{ max-width: 960px; margin: 0 auto; padding: 32px 20px; }}
          .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 20px; margin-bottom: 20px; }}
          h1, h2 {{ margin: 0 0 12px; }}
          .meta {{ color: #6b7280; font-size: 14px; }}
          table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
          th, td {{ border-top: 1px solid #e5e7eb; padding: 10px 8px; text-align: left; }}
          th {{ color: #6b7280; font-weight: 600; }}
          .badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #eef2ff; color: #3730a3; font-size: 12px; }}
        </style>
      </head>
      <body>
        <div class="wrap">
          <div class="card">
            <h1>Automation Execution</h1>
            <p class="meta">Execution ID: {execution.get('execution_id')} | Received: {execution.get('received_at')}</p>
            <p><span class="badge">{execution.get('status')}</span></p>
            <p><strong>Company:</strong> {execution.get('company_name') or 'Unknown'}</p>
            <p><strong>Campaign goal:</strong> {execution.get('campaign_goal') or 'Not provided'}</p>
            <p><strong>Market summary:</strong> {execution.get('market_summary') or 'Not provided'}</p>
            <p><strong>Next action:</strong> {execution.get('next_action') or 'Not provided'}</p>
          </div>
          <div class="card">
            <h2>Generated Leads</h2>
            <table>
              <thead>
                <tr><th>Name</th><th>Title</th><th>Email</th><th>Score</th></tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
          <div class="card">
            <h2>Recommended Sequence</h2>
            <ol>{steps}</ol>
          </div>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(html)
