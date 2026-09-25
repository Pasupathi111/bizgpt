#!/usr/bin/env python3
"""
Tiny fake Dify API for local testing without a real Dify server.
    python3 dev/mock_dify.py        # listens on :5055
Then set DIFY_BASE_URL=http://host.docker.internal:5055 and any api_key.

Supports:
- streaming workflow responses (for dify_pipe)
- blocking workflow responses (for forms -> Dify workflow actions)
- streaming chat responses (for chatflow/chat apps)
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = (
    '## Lead assessment: {company}\n\n'
    '| Field | Value |\n|---|---|\n'
    '| Score | **82 / 100** |\n| Tier | 🔥 Hot |\n| Budget | Confirmed |\n\n'
    '### Suggested reply\n\nHi, thanks for reaching out. Based on your team size and timeline, '
    'I would love to set up a 30-minute demo this week...'
)


def lead_outputs(inputs: dict) -> dict:
    company = inputs.get('company_name') or inputs.get('company') or inputs.get('query', '').split(',')[0][:40] or 'Unknown'
    employee_count = str(inputs.get('employee_count') or '120')
    budget = str(inputs.get('budget_status') or 'Confirmed')
    timeline = str(inputs.get('timeline') or '6 weeks')
    qualification = 'Hot' if budget.lower() not in ('unknown', 'none', 'no') else 'Warm'
    return {
        'company': company,
        'lead_score': 82,
        'qualification': qualification,
        'budget': budget,
        'timeline': timeline,
        'workflow_steps': [
            {'title': 'Extract lead details', 'status': 'completed', 'details': 'Pulled company, budget, and timeline from the request.'},
            {'title': 'Score lead', 'status': 'completed', 'details': 'Rated buying readiness based on budget and rollout urgency.'},
            {'title': 'Draft reply', 'status': 'completed', 'details': 'Prepared a suggested response for the sales team.'},
        ],
        'summary': f'{company} looks like a {qualification.lower()} lead with roughly {employee_count} employees and a target timeline of {timeline}.',
        'draft_reply': (
            f'Hi {company}, thanks for reaching out. Based on your team size and timeline, '
            'I would love to schedule a 30-minute demo this week.'
        ),
    }


def company_lead_generation_outputs(inputs: dict) -> dict:
    company = inputs.get('company_name') or 'Unknown Company'
    website = inputs.get('website') or f'www.{company.lower().replace(" ", "")}.com'
    industry = inputs.get('industry') or 'Software'
    region = inputs.get('target_region') or 'Global'
    roles = [role.strip() for role in str(inputs.get('target_roles') or 'CTO, Head of Support, RevOps').split(',') if role.strip()]
    lead_count = max(1, min(int(inputs.get('lead_count') or 5), 20))
    icp_notes = str(inputs.get('icp_notes') or 'Mid-market companies with active digital transformation initiatives.')
    goal = str(inputs.get('campaign_goal') or 'Book discovery calls for the sales team.')
    leads = []
    first_names = ['Maya', 'Arjun', 'Elena', 'Jordan', 'Priya', 'Daniel', 'Asha', 'Marcus']
    last_names = ['Patel', 'Nair', 'Lopez', 'Carter', 'Singh', 'Kim', 'Brown', 'Shah']

    for idx in range(lead_count):
        first = first_names[idx % len(first_names)]
        last = last_names[idx % len(last_names)]
        role = roles[idx % len(roles)]
        leads.append(
            {
                'name': f'{first} {last}',
                'title': role,
                'company': company,
                'email': f'{first.lower()}.{last.lower()}@{website.removeprefix("https://").removeprefix("http://").removeprefix("www.")}',
                'linkedin': f'https://www.linkedin.com/in/{first.lower()}-{last.lower()}',
                'score': 88 - idx * 4,
                'reason': f'Matches the ICP for {industry} buyers in {region} and is relevant to the goal: {goal}',
            }
        )

    return {
        'company': company,
        'campaign_goal': goal,
        'market_summary': f'{company} fits a {industry} outreach campaign focused on {region}. ICP notes: {icp_notes}',
        'workflow_steps': [
            {'title': 'Analyze company profile', 'status': 'completed', 'details': f'Reviewed {company}, {website}, and the target market context.'},
            {'title': 'Build ICP filter', 'status': 'completed', 'details': f'Used roles {", ".join(roles)} with notes: {icp_notes}'},
            {'title': 'Generate leads', 'status': 'completed', 'details': f'Prepared {lead_count} draft leads for outbound outreach.'},
            {'title': 'Draft next action', 'status': 'completed', 'details': 'Created a recommended outreach sequence for the SDR team.'},
        ],
        'generated_leads': leads,
        'recommended_sequence': [
            'Day 1: personalized email with industry pain point',
            'Day 3: LinkedIn connect with short note',
            'Day 6: follow-up email with case study',
            'Day 9: call task for highest scoring leads',
        ],
        'next_action': f'Push the top {min(3, lead_count)} leads into CRM and launch the first-touch sequence.',
    }


class Handler(BaseHTTPRequestHandler):
    def _sse(self, events):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for event in events:
            self.wfile.write(f'data: {json.dumps(event)}\n\n'.encode())
            self.wfile.flush()
            time.sleep(0.05 if event.get('event') in ('text_chunk', 'message') else 0.8)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/v1/workflows/run':
            inputs = body.get('inputs', {}) or {}
            response_mode = body.get('response_mode', 'streaming')
            query = inputs.get('query', '')
            company = inputs.get('company_name') or query.split(',')[0][:40] or 'Unknown'
            workflow_kind = 'company_lead_generation' if 'target_roles' in inputs or 'lead_count' in inputs else 'lead_qualifier'
            outputs = company_lead_generation_outputs(inputs) if workflow_kind == 'company_lead_generation' else lead_outputs(inputs)

            if response_mode == 'blocking':
                payload = {
                    'data': {
                        'id': 'mock-workflow-run-1',
                        'workflow_run_id': 'mock-workflow-run-1',
                        'task_id': 'mock-task-1',
                        'status': 'succeeded',
                        'outputs': outputs,
                        'elapsed_time': 0.8,
                    }
                }
                encoded = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return

            events = [{'event': 'workflow_started', 'data': {}}]
            titles = (
                ('Start', 'Analyze company profile', 'Build ICP filter', 'Generate leads', 'Draft next action')
                if workflow_kind == 'company_lead_generation'
                else ('Start', 'Extract lead details', 'Score lead', 'Draft reply')
            )
            for title in titles:
                events.append({'event': 'node_started', 'data': {'title': title}})
            for word in REPORT.format(company=company).split(' '):
                events.append({'event': 'text_chunk', 'data': {'text': word + ' '}})
            events.append({'event': 'workflow_finished', 'data': {'status': 'succeeded', 'outputs': outputs}})
            self._sse(events)
        elif self.path == '/v1/chat-messages':
            answer = 'Employees get **24 days** of paid leave per year, accrued monthly.'
            events = [{'event': 'node_started', 'data': {'title': 'Knowledge Retrieval'}}]
            events += [{'event': 'message', 'answer': w + ' '} for w in answer.split(' ')]
            events.append(
                {
                    'event': 'message_end',
                    'conversation_id': 'mock-conv-1',
                    'metadata': {
                        'retriever_resources': [
                            {'document_name': 'HR-Leave-Policy.pdf', 'content': 'Annual leave: 24 days...', 'score': 0.91}
                        ]
                    },
                }
            )
            self._sse(events)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    print('Mock Dify on http://0.0.0.0:5055')
    ThreadingHTTPServer(('0.0.0.0', 5055), Handler).serve_forever()
