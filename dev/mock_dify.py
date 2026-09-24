#!/usr/bin/env python3
"""
Tiny fake Dify API for testing the Dify pipe without a real Dify server.
    python3 dev/mock_dify.py        # listens on :5055
Then set DIFY_BASE_URL=http://host.docker.internal:5055 and any api_key.
Speaks the same SSE events as Dify: workflow_started/node_started/text_chunk/
workflow_finished (workflows) and message/message_end (chat apps).
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
            query = body.get('inputs', {}).get('query', '')
            company = query.split(',')[0][:40] or 'Unknown'
            events = [{'event': 'workflow_started', 'data': {}}]
            for title in ('Start', 'Extract lead details', 'Score lead', 'Draft reply'):
                events.append({'event': 'node_started', 'data': {'title': title}})
            for word in REPORT.format(company=company).split(' '):
                events.append({'event': 'text_chunk', 'data': {'text': word + ' '}})
            events.append({'event': 'workflow_finished', 'data': {'status': 'succeeded', 'outputs': {}}})
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
