"""Gmail -> Monthly Report: new site-photo emails become report photos, then the normal workflow continues.

AI decides only what the email is about (project, month). The application decides everything else:
which emails are new, where the photos go, file checks, and never importing an email twice.
"""

import logging
import re

from . import ai, config
from .gmail import QUERY, Gmail, GmailError
from .store import Store

log = logging.getLogger('monthly-report.gmail')

# Bounces and auto-replies carry Google's own icons as images; they are never site photos.
AUTOMATED_SENDER = re.compile(r'^(mailer-daemon|postmaster)@', re.I)
AUTOMATED_SUBJECT = re.compile(r'^(delivery status notification|undeliver(ed|able)|mail delivery (failed|subsystem)|returned mail)', re.I)


async def import_from_gmail(store: Store, gmail: Gmail, add_photo, auth: str, *, project_id: str | None = None,
                            month: str | None = None, created_by: str | None = None, limit: int = 25,
                            only_month: str | None = None) -> dict:
    """Import new site-photo emails. project_id/month (from the coordinator) override what the email says.

    add_photo(report_id, filename, data) -> bool stores one validated image.
    Returns {imported: [...], needs_info: [...], skipped: [...], reports: [report ids to analyse]}.
    """
    cfg = config.load_config()
    out = {'imported': [], 'needs_info': [], 'skipped': [], 'reports': []}
    ids = await gmail.search(QUERY, page_size=limit)
    for message_id in ids:
        seen = store.gmail_seen(message_id)
        if seen and seen['status'] in ('imported', 'ignored'):
            continue
        email = await gmail.read(message_id)
        summary = {'message_id': message_id, 'subject': email['subject'], 'from': email['from'], 'photos': len(email['images'])}
        if not email['images']:
            store.gmail_record(message_id, email['subject'], email['from'], 'ignored', detail='no image attachments')
            out['skipped'].append({**summary, 'reason': 'no image attachments'})
            continue
        if AUTOMATED_SENDER.match(email['from_email']) or AUTOMATED_SUBJECT.match(email['subject'].strip()):
            store.gmail_record(message_id, email['subject'], email['from'], 'ignored', detail='bounce / automated email')
            out['skipped'].append({**summary, 'reason': 'bounce / automated email'})
            continue

        target_project, target_month = project_id, month
        if not (target_project and target_month):
            try:
                info = ai.normalise_email(ai.parse_json(await ai.complete(
                    [{'role': 'user', 'content': ai.email_prompt(email, cfg)}], auth)), cfg,
                    email_text=f"{email['subject']}\n{email['body']}")
            except ai.ModelError as e:
                out['skipped'].append({**summary, 'reason': f'could not read the email: {e}'})
                continue
            if not info['is_site_photos']:
                store.gmail_record(message_id, email['subject'], email['from'], 'ignored', detail='not site photos')
                out['skipped'].append({**summary, 'reason': 'not a site-photo email'})
                continue
            target_project = target_project or info['project_id']
            target_month = target_month or info['month']
        if only_month and target_month and target_month != only_month:
            # Asked for one month: another month's email stays pending (not recorded) for when that month is asked.
            out['skipped'].append({**summary, 'reason': f'other month ({target_month})'})
            continue
        if not (target_project and target_month):
            store.gmail_record(message_id, email['subject'], email['from'], 'needs_info', photos=len(email['images']),
                               detail='project or month not stated')
            out['needs_info'].append({**summary, 'project_id': target_project, 'month': target_month})
            continue

        report = store.find_open_report(target_project, target_month) or store.create_report(
            target_project, target_month, created_by or email['from_email'])
        added, failed = 0, []
        for att in email['images']:
            try:
                data = await gmail.download(message_id, att)
            except GmailError as e:
                failed.append(f'{att["filename"]}: {e}')
                continue
            if add_photo(report['id'], att['filename'], data):
                added += 1
            else:
                failed.append(f'{att["filename"]}: not a readable image')
        if not added:
            # Nothing stored (e.g. the Gmail server cannot download attachments): keep the email pending so it is retried.
            store.gmail_record(message_id, email['subject'], email['from'], 'failed', report['id'], 0, '; '.join(failed)[:2000])
            out['skipped'].append({**summary, 'reason': 'no photo could be downloaded', 'failed': failed})
            continue
        store.gmail_record(message_id, email['subject'], email['from'], 'imported', report['id'], added,
                           '; '.join(failed) or None)
        store.event(report['id'], 'gmail_imported', email['from_email'], f'{added} photo(s) from "{email["subject"]}"')
        out['imported'].append({**summary, 'report_id': report['id'], 'project_id': target_project, 'month': target_month,
                                'added': added, 'failed': failed})
        if report['id'] not in out['reports'] and added:
            out['reports'].append(report['id'])
    return out
