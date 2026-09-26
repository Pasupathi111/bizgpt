// Test-run presets, run history and workspace variables (static demo data).
import type { RunRecord } from '../types';

export const TEST_INPUTS: Record<string, string> = {
	'Form Data': JSON.stringify(
		{
			name: 'Rajesh Kumar',
			email: 'rajesh@abctech.com',
			company: 'ABC Technologies',
			job_title: 'CTO',
			phone: '+91 98765 43210',
			source: 'Website'
		},
		null,
		2
	),
	Email: JSON.stringify(
		{
			from: 'Meera Iyer <meera.iyer@northwind.io>',
			subject: 'Pricing for 200 seats?',
			body: 'Hi team, I am the VP Operations at Northwind. We are evaluating AI assistants for our support org of ~200 agents. Could you share enterprise pricing and a demo slot next week? Thanks, Meera — +91 99887 66554',
			source: 'Email'
		},
		null,
		2
	),
	'Manual Input': JSON.stringify(
		{
			name: 'Arun P',
			email: 'arun.p@gmail.com',
			company: '',
			job_title: 'Student',
			phone: '',
			source: 'Instagram'
		},
		null,
		2
	)
};

export const RUN_HISTORY: RunRecord[] = [
	{ id: 'run_8f2a91', workflowId: 'wf-inbound', workflowName: 'Lead Generation', status: 'success', trigger: 'Form Submission', durationMs: 12400, startedAt: 'Today, 10:44 AM', lead: 'Rajesh Kumar · ABC Technologies', score: 85, nodes: 9 },
	{ id: 'run_8f2a77', workflowId: 'wf-chatbot', workflowName: 'Website Chatbot Lead Capture', status: 'success', trigger: 'Webhook', durationMs: 4210, startedAt: 'Today, 10:31 AM', lead: 'Sneha Rao · Brightline', score: 78, nodes: 6 },
	{ id: 'run_8f2a52', workflowId: 'wf-inbox', workflowName: 'Inbox Lead Detector', status: 'success', trigger: 'New Email', durationMs: 6980, startedAt: 'Today, 10:18 AM', lead: 'Meera Iyer · Northwind', score: 91, nodes: 7 },
	{ id: 'run_8f2a33', workflowId: 'wf-inbound', workflowName: 'Lead Generation', status: 'success', trigger: 'Form Submission', durationMs: 10870, startedAt: 'Today, 09:57 AM', lead: 'Arun P · —', score: 32, nodes: 8 },
	{ id: 'run_8f2a10', workflowId: 'wf-inbound', workflowName: 'Lead Generation', status: 'failed', trigger: 'Form Submission', durationMs: 3120, startedAt: 'Today, 09:40 AM', lead: 'Vikram S · Zenlytics', score: null, nodes: 3 },
	{ id: 'run_8f29f4', workflowId: 'wf-linkedin', workflowName: 'LinkedIn Prospect Enrichment', status: 'success', trigger: 'Schedule', durationMs: 184300, startedAt: 'Today, 09:00 AM', lead: '48 prospects', score: null, nodes: 8 },
	{ id: 'run_8f29c1', workflowId: 'wf-chatbot', workflowName: 'Website Chatbot Lead Capture', status: 'success', trigger: 'Webhook', durationMs: 3890, startedAt: 'Yesterday, 6:12 PM', lead: 'Farhan Ali · Kite Labs', score: 64, nodes: 4 },
	{ id: 'run_8f29a0', workflowId: 'wf-inbox', workflowName: 'Inbox Lead Detector', status: 'success', trigger: 'New Email', durationMs: 5420, startedAt: 'Yesterday, 4:47 PM', lead: 'Vendor pitch (non-lead)', score: null, nodes: 5 },
	{ id: 'run_8f2981', workflowId: 'wf-inbound', workflowName: 'Lead Generation', status: 'success', trigger: 'Form Submission', durationMs: 11960, startedAt: 'Yesterday, 3:05 PM', lead: 'Lakshmi N · Orbit Retail', score: 88, nodes: 9 },
	{ id: 'run_8f2966', workflowId: 'wf-events', workflowName: 'Event & Webinar Follow-up', status: 'success', trigger: 'File Upload', durationMs: 96200, startedAt: 'Sep 18, 2026', lead: '312 attendees', score: null, nodes: 8 }
];

export interface Variable {
	key: string;
	value: string;
	type: 'secret' | 'string' | 'number';
	scope: string;
}

export const VARIABLES: Variable[] = [
	{ key: 'HUBSPOT_API_KEY', value: 'pat-na1-2c8f••••••••••••', type: 'secret', scope: 'All workflows' },
	{ key: 'APOLLO_API_KEY', value: 'apl_••••••••••••', type: 'secret', scope: 'LinkedIn Prospect Enrichment' },
	{ key: 'LEAD_SCORE_THRESHOLD', value: '70', type: 'number', scope: 'All workflows' },
	{ key: 'SALES_WHATSAPP_GROUP', value: 'Sales Team – India', type: 'string', scope: 'Lead Generation' },
	{ key: 'SENDER_MAILBOX', value: 'sales@bizgpt.ai', type: 'string', scope: 'All workflows' },
	{ key: 'DEFAULT_LLM', value: 'claude-sonnet-5', type: 'string', scope: 'All workflows' }
];
