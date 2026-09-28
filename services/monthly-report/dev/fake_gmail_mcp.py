#!/usr/bin/env python3
"""A stand-in for the Gmail MCP server (google_workspace_mcp 1.29 output format) for local demos and tests.

    python3 dev/fake_gmail_mcp.py <photos_dir> [port]

Serves three emails built from the photos in <photos_dir>:
  1. "Taman Park - September 2026 site photos" with the IMG_01xx / IMG_02xx photos
  2. "Zone C drain works photos" (no project/month named) with the IMG_03xx photos
  3. "Team lunch" with no images
Needs only the standard library.
"""

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PHOTOS = Path(sys.argv[1] if len(sys.argv) > 1 else 'sample-photos')
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8010


def _emails():
    files = sorted(PHOTOS.glob('*.jpg'))
    return {
        '18f0000000000001': {'subject': 'Taman Park - September 2026 site photos', 'from': 'Site Team <site.team@example.com>',
                             'date': 'Tue, 22 Sep 2026 09:10:00 +0800',
                             'body': 'Hi, attached are the Taman Park photos for September 2026 (grass cutting and tree works).',
                             'files': [f for f in files if f.name.startswith(('IMG_01', 'IMG_02'))]},
        '18f0000000000002': {'subject': 'Zone C drain works photos', 'from': 'Site Team <site.team@example.com>',
                             'date': 'Wed, 23 Sep 2026 17:40:00 +0800', 'body': 'Photos from the drain cleaning.',
                             'files': [f for f in files if f.name.startswith('IMG_03')]},
        '18f0000000000003': {'subject': 'Team lunch', 'from': 'HR <hr@example.com>', 'date': 'Thu, 24 Sep 2026 12:00:00 +0800',
                             'body': 'Lunch at 1pm.', 'files': []},
    }


def tool(name: str, args: dict) -> str:
    emails = _emails()
    if name == 'search_gmail_messages':
        rows = [f'Message ID: {mid}\nThread ID: {mid}\n' for mid in emails]
        return f'Found {len(rows)} messages matching \'{args.get("query")}\':\n\n' + '\n'.join(rows)
    if name == 'get_gmail_message_content':
        e = emails[args['message_id']]
        lines = [f'Message ID: {args["message_id"]}', f'Subject: {e["subject"]}', f'From: {e["from"]}', f'Date: {e["date"]}',
                 'To: reports@example.com', 'Cc: [not present in Gmail response]', f'\n--- BODY ---\n{e["body"]}']
        if e['files']:
            lines.append('\n--- ATTACHMENTS ---')
            for i, f in enumerate(e['files']):
                lines.append(f'{i + 1}. {f.name} (image/jpeg, {f.stat().st_size / 1024:.1f} KB)\n   Attachment ID: att-{args["message_id"]}-{i}\n'
                             f"   Use get_gmail_attachment_content(message_id='{args['message_id']}', attachment_id='att-{args['message_id']}-{i}', attachment_index={i}) to download")
        return '\n'.join(lines)
    if name == 'get_gmail_attachment_content':
        _, mid, i = args['attachment_id'].split('-')
        data = base64.b64encode(emails[mid]['files'][int(i)].read_bytes()).decode()
        out = ['Attachment downloaded successfully!', f'Message ID: {mid}', f'Size: {len(data) * 3 / 4096:.1f} KB',
               '\n📎 Download URL: http://localhost:8010/attachments/unused', '\nThe file will expire after 1 hour.']
        if args.get('return_base64'):
            out += [f'\n📦 Base64 content ({len(data)} chars, standard base64):', data]
        return '\n'.join(out)
    raise KeyError(name)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if body.get('method') == 'tools/call':
            p = body['params']
            try:
                result = {'content': [{'type': 'text', 'text': tool(p['name'], p.get('arguments') or {})}], 'isError': False}
            except KeyError as e:
                result = {'content': [{'type': 'text', 'text': f'unknown {e}'}], 'isError': True}
            reply = {'jsonrpc': '2.0', 'id': body.get('id'), 'result': result}
        elif 'id' in body:
            reply = {'jsonrpc': '2.0', 'id': body['id'], 'result': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'serverInfo': {'name': 'fake-gmail'}}}
        else:
            self.send_response(202)
            self.end_headers()
            return
        raw = ('data: ' + json.dumps(reply) + '\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('mcp-session-id', 'fake-session')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    print(f'fake Gmail MCP on :{PORT} serving {PHOTOS}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
