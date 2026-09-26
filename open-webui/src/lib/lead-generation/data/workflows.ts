// Sample lead-generation workflows and templates (static demo data).
import type { Handle, WFEdge, WFNode, Workflow } from '../types';

const n = (
	id: string,
	kind: string,
	title: string,
	subtitle: string,
	desc: string,
	x: number,
	y: number,
	config: Record<string, any> = {}
): WFNode => ({ id, kind, title, subtitle, desc, x, y, config: { ...defaultConfig(kind), ...config } });

const e = (from: string, to: string, handle: Handle = 'out', label?: string): WFEdge => ({
	id: `${from}-${to}`,
	from,
	to,
	handle,
	label: label ?? (handle === 'true' ? 'Yes' : handle === 'false' ? 'No' : undefined)
});

/** Config a freshly dropped node starts with. */
export function defaultConfig(kind: string): Record<string, any> {
	switch (kind) {
		case 'form-trigger':
			return { form: 'Website Contact Form', fields: 'name, email, company, job_title, phone, source' };
		case 'webhook-trigger':
			return { method: 'POST', path: '/hooks/lead-intake', auth: 'API Key' };
		case 'schedule-trigger':
			return { cron: '0 9 * * 1-5', timezone: 'Asia/Kolkata' };
		case 'gmail-trigger':
			return { mailbox: 'sales@bizgpt.ai', label: 'INBOX', poll_interval: '1 min' };
		case 'csv-trigger':
			return { accept: '.csv, .xlsx', max_rows: 5000 };
		case 'llm':
			return {
				model: 'claude-sonnet-5',
				temperature: 0.3,
				prompt: 'You are a B2B sales analyst. Using {{lead}} and {{enriched_data}}, assess fit, buying intent and write a 2-sentence summary.'
			};
		case 'prompt':
			return { template: 'lead_summary_v3', variables: 'lead, company' };
		case 'knowledge':
			return { dataset: 'Product FAQ & Pricing', top_k: 3, score_threshold: 0.6 };
		case 'classifier':
			return { model: 'claude-haiku-4-5', classes: 'Sales lead, Support, Partnership, Spam' };
		case 'score':
			return { model: 'Rules + LLM', threshold: 70, weights: 'title 30, company size 20, intent 30, source 20' };
		case 'extractor':
			return { source: '{{trigger.body}}', fields: 'name, email, company, job_title, phone' };
		case 'http':
			return { method: 'GET', url: 'https://api.enrich.io/v2/company?domain={{lead.email_domain}}', timeout: 10 };
		case 'database':
			return { connection: 'Postgres · leads_db', query: "SELECT * FROM leads WHERE status = 'new' LIMIT 50" };
		case 'sheet':
			return { spreadsheet: 'Lead Tracker 2026', sheet: 'Inbound', mode: 'Append row' };
		case 'webhook':
			return { method: 'POST', url: 'https://hooks.example.com/leads' };
		case 'if-else':
			return { variable: 'lead_score', operator: '>', value: 70 };
		case 'router':
			return { variable: 'lead_score', routes: 'Hot ≥ 80, Warm 50–79, Cold < 50' };
		case 'code':
			return { language: 'Python 3', code: 'def main(leads: list) -> dict:\n    unique = {l["email"].lower(): l for l in leads}\n    return {"leads": list(unique.values())}' };
		case 'iterator':
			return { items: '{{prospects}}', parallel: 5 };
		case 'wait':
			return { duration: 3, unit: 'days' };
		case 'crm':
			return { provider: 'HubSpot', object: 'Contact', pipeline: 'Sales Pipeline', stage: 'MQL' };
		case 'gmail':
			return { account: 'sales@bizgpt.ai', to: '{{lead.email}}', subject: 'Great to meet you, {{lead.first_name}}!', template: 'welcome_v2' };
		case 'outlook':
			return { account: 'sales@bizgpt.ai', to: '{{lead.email}}', subject: 'Your requested brochure' };
		case 'whatsapp':
			return { to: 'Sales Team (group)', message: '🔥 Hot lead: {{lead.name}} ({{lead.company}}) scored {{lead_score}}' };
		case 'campaign':
			return { platform: 'HubSpot Sequences', sequence: 'Nurture · 6-week education', owner: 'Marketing' };
		default:
			return {};
	}
}

const inbound: Workflow = {
	id: 'wf-inbound',
	name: 'Lead Generation',
	description: 'Qualify inbound form leads with AI, score them and route to CRM or nurture.',
	category: 'Inbound',
	status: 'active',
	trigger: 'Form Submission',
	runs: 1284,
	successRate: 98.6,
	leads: 412,
	lastRun: '2 min ago',
	owner: 'Pasupathi S',
	updated: 'Today, 10:42 AM',
	version: 'v1.4',
	tags: ['Inbound', 'AI Scoring', 'HubSpot'],
	nodes: [
		n('n1', 'form-trigger', 'Trigger', 'Form Submission', 'New lead form submission', 40, 60),
		n('n2', 'extractor', 'Extract Data', 'Text Extractor', 'Extract lead information from form / email', 310, 60),
		n('n3', 'http', 'Enrich Lead', 'HTTP Request', 'Get company info from LinkedIn / Web', 580, 60),
		n('n4', 'llm', 'AI Analysis', 'LLM', 'Analyze lead quality and generate summary', 850, 60),
		n('n5', 'score', 'Lead Scoring', 'Lead Scoring', 'Score fit & intent from AI + enrichment', 40, 280),
		n('n6', 'if-else', 'Decision', 'If/Else', 'Is qualified lead? (Score > 70)', 310, 280),
		n('n7', 'crm', 'Create Lead', 'Save to CRM', 'Store lead in database / CRM (e.g., HubSpot)', 580, 280),
		n('n8', 'gmail', 'Send Email', 'Gmail / Outlook', 'Send welcome email to the lead', 850, 280),
		n('n9', 'campaign', 'Add to Nurture', 'Add to Campaign', 'Add to nurture sequence (Marketing)', 520, 490),
		n('n10', 'whatsapp', 'Notify Sales', 'WhatsApp', 'Alert the sales team about a hot lead', 850, 490)
	],
	edges: [
		e('n1', 'n2'),
		e('n2', 'n3'),
		e('n3', 'n4'),
		e('n4', 'n5'),
		e('n5', 'n6'),
		e('n6', 'n7', 'true'),
		e('n6', 'n9', 'false'),
		e('n7', 'n8'),
		e('n7', 'n10')
	]
};

const linkedin: Workflow = {
	id: 'wf-linkedin',
	name: 'LinkedIn Prospect Enrichment',
	description: 'Pull a Sales Navigator list every morning, enrich each prospect and write persona notes.',
	category: 'Outbound',
	status: 'active',
	trigger: 'Schedule',
	runs: 186,
	successRate: 96.2,
	leads: 2310,
	lastRun: '3 h ago',
	owner: 'Anitha R',
	updated: 'Yesterday',
	version: 'v2.1',
	tags: ['Outbound', 'Enrichment'],
	nodes: [
		n('l1', 'schedule-trigger', 'Trigger', 'Daily 9:00 AM', 'Runs every weekday morning', 40, 60),
		n('l2', 'http', 'Fetch Prospects', 'HTTP Request', 'Load saved list from LinkedIn Sales Navigator', 310, 60, { url: 'https://api.linkedin.com/v2/salesNavigator/lists/{{list_id}}' }),
		n('l3', 'iterator', 'For Each Prospect', 'Iterator', 'Process up to 50 prospects in parallel', 580, 60),
		n('l4', 'http', 'Enrich Company', 'HTTP Request', 'Firmographics from Apollo / Clearbit', 850, 60, { url: 'https://api.apollo.io/v1/organizations/enrich?domain={{domain}}' }),
		n('l5', 'llm', 'Persona Summary', 'LLM', 'Write persona notes & opening line', 40, 280),
		n('l6', 'score', 'ICP Fit Score', 'Lead Scoring', 'Match against ideal customer profile', 310, 280),
		n('l7', 'sheet', 'Save to Sheet', 'Google Sheets', 'Append enriched prospect to tracker', 580, 280),
		n('l8', 'crm', 'Sync to CRM', 'Save to CRM', 'Upsert contact with persona notes', 850, 280)
	],
	edges: [e('l1', 'l2'), e('l2', 'l3'), e('l3', 'l4'), e('l4', 'l5'), e('l5', 'l6'), e('l6', 'l7'), e('l7', 'l8')]
};

const chatbot: Workflow = {
	id: 'wf-chatbot',
	name: 'Website Chatbot Lead Capture',
	description: 'Detect buying intent in website chat, capture contact details and alert sales instantly.',
	category: 'Conversational',
	status: 'active',
	trigger: 'Webhook',
	runs: 3921,
	successRate: 99.1,
	leads: 268,
	lastRun: '12 min ago',
	owner: 'Pasupathi S',
	updated: 'Sep 22, 2026',
	version: 'v3.0',
	tags: ['Chatbot', 'WhatsApp'],
	nodes: [
		n('c1', 'webhook-trigger', 'Trigger', 'Chat Message', 'New message from website widget', 40, 60),
		n('c2', 'classifier', 'Detect Intent', 'Classifier', 'Pricing, demo, support or chit-chat?', 310, 60),
		n('c3', 'if-else', 'Buying Intent?', 'If/Else', 'Intent is pricing or demo request', 580, 60, { variable: 'intent', operator: 'in', value: 'pricing, demo' }),
		n('c4', 'extractor', 'Capture Contact', 'Text Extractor', 'Ask for and extract name, email, phone', 850, 60),
		n('c5', 'crm', 'Create Deal', 'Save to CRM', 'Create HubSpot deal in "New" stage', 40, 290, { object: 'Deal', stage: 'New' }),
		n('c6', 'whatsapp', 'Notify Sales', 'WhatsApp', 'Ping the on-call rep with chat summary', 310, 290),
		n('c7', 'knowledge', 'Answer from KB', 'Knowledge Retrieval', 'Reply using product docs & FAQ', 760, 290)
	],
	edges: [e('c1', 'c2'), e('c2', 'c3'), e('c3', 'c4', 'true'), e('c3', 'c7', 'false'), e('c4', 'c5'), e('c5', 'c6')]
};

const cold: Workflow = {
	id: 'wf-cold',
	name: 'Cold Email Outreach Sequence',
	description: 'Personalise intro emails with AI, wait for replies and follow up automatically.',
	category: 'Outbound',
	status: 'draft',
	trigger: 'Schedule',
	runs: 0,
	successRate: 0,
	leads: 0,
	lastRun: 'Never',
	owner: 'Karthik M',
	updated: 'Sep 24, 2026',
	version: 'v0.3',
	tags: ['Outbound', 'Email'],
	nodes: [
		n('o1', 'schedule-trigger', 'Trigger', 'Weekdays 10:00', 'Batch send during business hours', 40, 60, { cron: '0 10 * * 1-5' }),
		n('o2', 'database', 'Fetch Leads', 'Database Query', 'Uncontacted leads from leads_db', 310, 60),
		n('o3', 'iterator', 'For Each Lead', 'Iterator', 'Throttle to 40 emails / hour', 580, 60),
		n('o4', 'llm', 'Personalise Email', 'LLM', 'Write a 90-word intro using enrichment', 850, 60),
		n('o5', 'gmail', 'Send Intro', 'Gmail / Outlook', 'Send from rep mailbox with tracking', 40, 280),
		n('o6', 'wait', 'Wait 3 Days', 'Wait / Delay', 'Give the lead time to reply', 310, 280),
		n('o7', 'if-else', 'Replied?', 'If/Else', 'Reply detected on thread', 580, 280, { variable: 'thread.replied', operator: '==', value: 'true' }),
		n('o8', 'crm', 'Mark Engaged', 'Save to CRM', 'Move to "Engaged" and assign owner', 850, 280, { stage: 'Engaged' }),
		n('o9', 'gmail', 'Send Follow-up', 'Gmail / Outlook', 'Polite bump with a case study', 790, 490, { subject: 'Re: {{previous_subject}}' })
	],
	edges: [e('o1', 'o2'), e('o2', 'o3'), e('o3', 'o4'), e('o4', 'o5'), e('o5', 'o6'), e('o6', 'o7'), e('o7', 'o8', 'true'), e('o7', 'o9', 'false')]
};

const events: Workflow = {
	id: 'wf-events',
	name: 'Event & Webinar Follow-up',
	description: 'Clean attendee lists, score engagement and route hot, warm and cold leads.',
	category: 'Events',
	status: 'paused',
	trigger: 'File Upload',
	runs: 42,
	successRate: 92.8,
	leads: 1870,
	lastRun: 'Sep 18, 2026',
	owner: 'Divya K',
	updated: 'Sep 18, 2026',
	version: 'v1.2',
	tags: ['Events', 'Router'],
	nodes: [
		n('v1', 'csv-trigger', 'Trigger', 'CSV Upload', 'Attendee export from Zoom / Hopin', 40, 60),
		n('v2', 'extractor', 'Parse Attendees', 'Text Extractor', 'Normalise names, emails, companies', 310, 60),
		n('v3', 'code', 'Dedupe & Clean', 'Code (Python)', 'Drop duplicates and personal emails', 580, 60),
		n('v4', 'score', 'Score Engagement', 'Lead Scoring', 'Attendance time, Q&A, poll answers', 850, 60),
		n('v5', 'router', 'Route by Score', 'Router', 'Hot ≥ 80 · Warm 50–79 · Cold < 50', 40, 420),
		n('v6', 'gmail', 'Book a Demo', 'Gmail / Outlook', 'Send calendar link from the AE', 340, 320),
		n('v7', 'campaign', 'Nurture Track', 'Add to Campaign', 'Webinar recap + 4-week nurture', 340, 480),
		n('v8', 'sheet', 'Archive', 'Google Sheets', 'Log cold leads for quarterly review', 340, 640)
	],
	edges: [e('v1', 'v2'), e('v2', 'v3'), e('v3', 'v4'), e('v4', 'v5'), e('v5', 'v6', 'out', 'Hot'), e('v5', 'v7', 'out', 'Warm'), e('v5', 'v8', 'out', 'Cold')]
};

const inbox: Workflow = {
	id: 'wf-inbox',
	name: 'Inbox Lead Detector',
	description: 'Watch the sales inbox, spot real leads with AI, log them and draft a reply.',
	category: 'Inbound',
	status: 'active',
	trigger: 'New Email',
	runs: 764,
	successRate: 97.4,
	leads: 131,
	lastRun: '26 min ago',
	owner: 'Pasupathi S',
	updated: 'Sep 25, 2026',
	version: 'v1.1',
	tags: ['Gmail', 'Classifier'],
	nodes: [
		n('m1', 'gmail-trigger', 'Trigger', 'New Email', 'New message in sales@ inbox', 40, 60),
		n('m2', 'classifier', 'Classify Email', 'Classifier', 'Sales lead, support, vendor or spam', 310, 60),
		n('m3', 'llm', 'Summarise Thread', 'LLM', 'Key ask, budget and timeline', 580, 60),
		n('m4', 'if-else', 'Lead Detected?', 'If/Else', 'Class is "Sales lead"', 850, 60, { variable: 'class', operator: '==', value: 'Sales lead' }),
		n('m5', 'extractor', 'Extract Contact', 'Text Extractor', 'Signature → name, title, phone', 40, 300),
		n('m6', 'crm', 'Log in CRM', 'Save to CRM', 'Create contact + attach email', 310, 300),
		n('m7', 'gmail', 'Draft Reply', 'Gmail / Outlook', 'Save AI-drafted reply for review', 580, 300, { mode: 'Save as draft' }),
		n('m8', 'code', 'Label & Archive', 'Code (Python)', 'Apply label, skip the rest', 1010, 300)
	],
	edges: [e('m1', 'm2'), e('m2', 'm3'), e('m3', 'm4'), e('m4', 'm5', 'true'), e('m4', 'm8', 'false'), e('m5', 'm6'), e('m6', 'm7')]
};

const ads: Workflow = {
	id: 'tpl-ads',
	name: 'Google Ads Lead Form Sync',
	description: 'Push Google Ads lead-form submissions into your CRM within seconds.',
	category: 'Paid Ads',
	status: 'draft',
	trigger: 'Webhook',
	runs: 0,
	successRate: 0,
	leads: 0,
	lastRun: 'Never',
	owner: 'Pasupathi S',
	updated: 'Template',
	version: 'v1.0',
	tags: ['Ads', 'CRM'],
	nodes: [
		n('a1', 'webhook-trigger', 'Trigger', 'Google Ads Lead', 'Lead form extension webhook', 40, 60),
		n('a2', 'extractor', 'Map Fields', 'Text Extractor', 'Map ad form columns to lead fields', 310, 60),
		n('a3', 'score', 'Lead Scoring', 'Lead Scoring', 'Campaign + keyword intent score', 580, 60),
		n('a4', 'crm', 'Create Lead', 'Save to CRM', 'Upsert with UTM + campaign', 850, 60),
		n('a5', 'outlook', 'Send Brochure', 'Outlook', 'Email the product brochure PDF', 850, 260)
	],
	edges: [e('a1', 'a2'), e('a2', 'a3'), e('a3', 'a4'), e('a4', 'a5')]
};

const partner: Workflow = {
	id: 'tpl-partner',
	name: 'Referral Partner Intake',
	description: 'Verify partner companies, assess fit with AI and route to partnerships or nurture.',
	category: 'Partnerships',
	status: 'draft',
	trigger: 'Form Submission',
	runs: 0,
	successRate: 0,
	leads: 0,
	lastRun: 'Never',
	owner: 'Pasupathi S',
	updated: 'Template',
	version: 'v1.0',
	tags: ['Partners', 'AI'],
	nodes: [
		n('p1', 'form-trigger', 'Trigger', 'Partner Form', 'Partner application submitted', 40, 60, { form: 'Partner Application' }),
		n('p2', 'http', 'Verify Company', 'HTTP Request', 'Check registry / GST records', 310, 60),
		n('p3', 'llm', 'Fit Assessment', 'LLM', 'Summarise overlap and partner fit', 580, 60),
		n('p4', 'if-else', 'Fit ≥ 60?', 'If/Else', 'Partner fit score threshold', 850, 60, { variable: 'fit_score', operator: '>=', value: 60 }),
		n('p5', 'crm', 'Create Partner', 'Save to CRM', 'Partner pipeline · "Review" stage', 1120, 60, { object: 'Company', pipeline: 'Partners', stage: 'Review' }),
		n('p6', 'campaign', 'Partner Nurture', 'Add to Campaign', 'Monthly partner newsletter', 1010, 280)
	],
	edges: [e('p1', 'p2'), e('p2', 'p3'), e('p3', 'p4'), e('p4', 'p5', 'true'), e('p4', 'p6', 'false')]
};

export const SAMPLE_WORKFLOWS: Workflow[] = [inbound, linkedin, chatbot, inbox, cold, events];

export interface Template {
	id: string;
	name: string;
	description: string;
	category: string;
	uses: string;
	minutes: number;
	popular?: boolean;
	workflow: Workflow;
}

export const TEMPLATES: Template[] = [
	{ id: 't-inbound', name: 'AI Inbound Lead Qualification', description: inbound.description, category: 'Inbound', uses: '12.4k', minutes: 5, popular: true, workflow: inbound },
	{ id: 't-chatbot', name: 'Website Chatbot Lead Capture', description: chatbot.description, category: 'Conversational', uses: '8.1k', minutes: 8, popular: true, workflow: chatbot },
	{ id: 't-linkedin', name: 'LinkedIn Prospect Enrichment', description: linkedin.description, category: 'Outbound', uses: '6.7k', minutes: 10, workflow: linkedin },
	{ id: 't-inbox', name: 'Inbox Lead Detector (Gmail / Outlook)', description: inbox.description, category: 'Inbound', uses: '5.2k', minutes: 6, workflow: inbox },
	{ id: 't-cold', name: 'Cold Email Outreach Sequence', description: cold.description, category: 'Outbound', uses: '4.9k', minutes: 12, workflow: cold },
	{ id: 't-events', name: 'Event & Webinar Follow-up', description: events.description, category: 'Events', uses: '3.3k', minutes: 9, workflow: events },
	{ id: 't-ads', name: ads.name, description: ads.description, category: 'Paid Ads', uses: '2.8k', minutes: 4, workflow: ads },
	{ id: 't-partner', name: partner.name, description: partner.description, category: 'Partnerships', uses: '1.1k', minutes: 7, workflow: partner }
];

export const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v));
