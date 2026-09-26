#!/usr/bin/env python3
"""Post a signed, Meta-shaped test message to the webhook (no Meta account needed).

    python dev/send_test_webhook.py "What are your opening hours?" --from 919876543210 --name Priya
    python dev/send_test_webhook.py --url https://your-host/api/whatsapp/webhook "Hi"

Signs with WHATSAPP_APP_SECRET from the environment (or --secret). Stdlib only.
"""

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('text')
parser.add_argument('--url', default='http://localhost:8001/api/whatsapp/webhook')
parser.add_argument('--from', dest='sender', default='919876543210')
parser.add_argument('--name', default='Test Customer')
parser.add_argument('--phone-number-id', default=os.getenv('WHATSAPP_PHONE_NUMBER_ID', '000000000000000'))
parser.add_argument('--secret', default=os.getenv('WHATSAPP_APP_SECRET', ''))
args = parser.parse_args()

payload = {
    'object': 'whatsapp_business_account',
    'entry': [{'id': 'test', 'changes': [{'field': 'messages', 'value': {
        'messaging_product': 'whatsapp',
        'metadata': {'display_phone_number': '910000000000', 'phone_number_id': args.phone_number_id},
        'contacts': [{'profile': {'name': args.name}, 'wa_id': args.sender}],
        'messages': [{'from': args.sender, 'id': f'wamid.TEST{uuid.uuid4().hex}', 'timestamp': str(int(time.time())),
                      'type': 'text', 'text': {'body': args.text}}],
    }}]}],
}
raw = json.dumps(payload).encode()
req = urllib.request.Request(args.url, data=raw, method='POST', headers={'Content-Type': 'application/json'})
if args.secret:
    req.add_header('X-Hub-Signature-256', 'sha256=' + hmac.new(args.secret.encode(), raw, hashlib.sha256).hexdigest())
with urllib.request.urlopen(req, timeout=30) as resp:
    print(resp.status, resp.read().decode())
