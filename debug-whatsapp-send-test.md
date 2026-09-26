# Debug Session: whatsapp-send-test
- **Status**: [OPEN]
- **Issue**: Restart the live WhatsApp container, verify Biz GPT can talk to it, and test sending Biz GPT WhatsApp messages.
- **Debug Server**: not started; using existing service logs and live API responses for runtime evidence
- **Log File**: docker logs `bizgpt-whatsapp` and live HTTP responses

## Reproduction Steps
1. Restart the live `bizgpt-whatsapp` container from the `bizgpt` compose project.
2. Verify `/health` and `/api/whatsapp/test-connection`.
3. Send a plain-text test message through the Biz GPT WhatsApp service.
4. If blocked, compare the service response and container logs to determine the cause.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | The container still loads stale env after restart. | Medium | Low | Pending |
| B | Biz GPT to WhatsApp service connectivity is healthy, but Meta policy blocks the send. | High | Low | Pending |
| C | The WhatsApp test number only allows approved recipients, so outbound sends fail for this recipient. | High | Low | Pending |
| D | The Biz GPT send path fails locally before the request reaches Meta. | Low | Low | Pending |
| E | Meta accepts the send but delivery fails later due to downstream recipient restrictions. | Low | Medium | Pending |

## Log Evidence
- Container restart succeeded and `/health` returned `{"status":"ok","database":true}`.
- Running container env shows the updated `WHATSAPP_ACCESS_TOKEN` and the expected `WHATSAPP_PHONE_NUMBER_ID=1263949493476238`.
- `POST /api/whatsapp/test-connection` returned:
  - `whatsapp.ok=true`
  - `openwebui.ok=true`
  - `openwebui.agent_model_found=true`
- `POST /api/whatsapp/messages/send` to `7305585999` with text `Biz GPT test WhatsApp message` returned:
  - `This customer has not messaged in the last 24 hours. WhatsApp only allows an approved template now.`
- `POST /api/whatsapp/messages/template` to `7305585999` with template `hello_world` returned:
  - `(#131030) Recipient phone number not in allowed list`

## Verification Conclusion
- Hypothesis A: Rejected. Restarted container loaded the new env correctly.
- Hypothesis B: Confirmed. Biz GPT and the WhatsApp service are healthy, but Meta policy blocks the free-text send.
- Hypothesis C: Confirmed. The approved template is still blocked because the recipient is not on the Meta test allowlist.
- Hypothesis D: Rejected. The Biz GPT send path is functioning and returning live Meta-policy errors.
- Hypothesis E: Rejected. Meta is rejecting the request before delivery rather than accepting then failing later.
