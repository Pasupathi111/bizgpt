// Node catalog: every node kind the builder can place on the canvas.

export interface Tone {
	bg: string;
	border: string;
	icon: string;
	soft: string;
}

export const TONES: Record<string, Tone> = {
	green: { bg: '#f0fdf4', border: '#bbf7d0', icon: '#16a34a', soft: '#dcfce7' },
	emerald: { bg: '#ecfdf5', border: '#a7f3d0', icon: '#059669', soft: '#d1fae5' },
	teal: { bg: '#f0fdfa', border: '#99f6e4', icon: '#0d9488', soft: '#ccfbf1' },
	sky: { bg: '#f0f9ff', border: '#bae6fd', icon: '#0284c7', soft: '#e0f2fe' },
	blue: { bg: '#eff6ff', border: '#bfdbfe', icon: '#2563eb', soft: '#dbeafe' },
	purple: { bg: '#faf5ff', border: '#e9d5ff', icon: '#7c3aed', soft: '#ede9fe' },
	violet: { bg: '#f5f3ff', border: '#ddd6fe', icon: '#6d28d9', soft: '#ede9fe' },
	fuchsia: { bg: '#fdf4ff', border: '#f5d0fe', icon: '#c026d3', soft: '#fae8ff' },
	pink: { bg: '#fdf2f8', border: '#fbcfe8', icon: '#db2777', soft: '#fce7f3' },
	rose: { bg: '#fff1f2', border: '#fecdd3', icon: '#e11d48', soft: '#ffe4e6' },
	red: { bg: '#fef2f2', border: '#fecaca', icon: '#dc2626', soft: '#fee2e2' },
	orange: { bg: '#fff7ed', border: '#fed7aa', icon: '#ea580c', soft: '#ffedd5' },
	amber: { bg: '#fffbeb', border: '#fde68a', icon: '#d97706', soft: '#fef3c7' },
	slate: { bg: '#f8fafc', border: '#cbd5e1', icon: '#475569', soft: '#e2e8f0' }
};

export interface NodeType {
	label: string;
	category: 'trigger' | 'ai' | 'data' | 'logic' | 'tools';
	icon: string;
	tone: string;
	/** default card subtitle when dropped on the canvas */
	subtitle: string;
	desc: string;
	/** has a Yes (right) and No (bottom) output */
	branching?: boolean;
}

export const CATEGORIES: { key: NodeType['category']; label: string }[] = [
	{ key: 'trigger', label: 'Triggers' },
	{ key: 'ai', label: 'LLM & AI' },
	{ key: 'data', label: 'Data' },
	{ key: 'logic', label: 'Logic' },
	{ key: 'tools', label: 'Tools' }
];

export const NODE_TYPES: Record<string, NodeType> = {
	'form-trigger': { label: 'Form Submission', category: 'trigger', icon: 'bolt', tone: 'green', subtitle: 'Form Submission', desc: 'Starts when a lead submits a form' },
	'webhook-trigger': { label: 'Webhook', category: 'trigger', icon: 'link', tone: 'green', subtitle: 'Webhook', desc: 'Starts on an incoming HTTP call' },
	'schedule-trigger': { label: 'Schedule', category: 'trigger', icon: 'clock', tone: 'green', subtitle: 'Cron Schedule', desc: 'Runs on a fixed schedule' },
	'gmail-trigger': { label: 'New Email', category: 'trigger', icon: 'inbox', tone: 'green', subtitle: 'Gmail / Outlook', desc: 'Starts when a new email arrives' },
	'csv-trigger': { label: 'File Upload', category: 'trigger', icon: 'upload', tone: 'green', subtitle: 'CSV Upload', desc: 'Starts when a lead list is uploaded' },

	llm: { label: 'LLM', category: 'ai', icon: 'cpu', tone: 'rose', subtitle: 'LLM', desc: 'Generate or analyse text with a model' },
	prompt: { label: 'Prompt', category: 'ai', icon: 'chat', tone: 'orange', subtitle: 'Prompt Template', desc: 'Render a reusable prompt' },
	knowledge: { label: 'Knowledge Base', category: 'ai', icon: 'book', tone: 'violet', subtitle: 'Knowledge Retrieval', desc: 'Retrieve context from documents' },
	classifier: { label: 'Question Classifier', category: 'ai', icon: 'funnel', tone: 'pink', subtitle: 'Classifier', desc: 'Classify text into categories' },
	score: { label: 'Lead Scoring', category: 'ai', icon: 'star', tone: 'orange', subtitle: 'Lead Scoring', desc: 'Score lead fit and intent (0–100)' },

	extractor: { label: 'Data Extractor', category: 'data', icon: 'docText', tone: 'blue', subtitle: 'Text Extractor', desc: 'Extract structured fields from text' },
	http: { label: 'HTTP Request', category: 'data', icon: 'globe', tone: 'purple', subtitle: 'HTTP Request', desc: 'Call any REST API' },
	database: { label: 'Database', category: 'data', icon: 'database', tone: 'sky', subtitle: 'Database Query', desc: 'Read or write rows' },
	sheet: { label: 'Google Sheets', category: 'data', icon: 'table', tone: 'emerald', subtitle: 'Append Row', desc: 'Write rows to a spreadsheet' },
	webhook: { label: 'Webhook Out', category: 'data', icon: 'link', tone: 'pink', subtitle: 'Webhook', desc: 'POST data to another system' },

	'if-else': { label: 'If/Else', category: 'logic', icon: 'branch', tone: 'amber', subtitle: 'If/Else', desc: 'Branch on a condition', branching: true },
	router: { label: 'Router', category: 'logic', icon: 'router', tone: 'fuchsia', subtitle: 'Router', desc: 'Route to one of many paths' },
	code: { label: 'Code', category: 'logic', icon: 'code', tone: 'slate', subtitle: 'Code (Python)', desc: 'Run custom Python / JS' },
	iterator: { label: 'Iterator', category: 'logic', icon: 'refresh', tone: 'teal', subtitle: 'Iterator', desc: 'Loop over a list of items' },
	wait: { label: 'Wait', category: 'logic', icon: 'clock', tone: 'slate', subtitle: 'Wait / Delay', desc: 'Pause before the next step' },

	crm: { label: 'CRM', category: 'tools', icon: 'database', tone: 'blue', subtitle: 'Save to CRM', desc: 'Create or update a CRM record' },
	gmail: { label: 'Gmail', category: 'tools', icon: 'mail', tone: 'red', subtitle: 'Gmail / Outlook', desc: 'Send an email' },
	outlook: { label: 'Outlook', category: 'tools', icon: 'mail', tone: 'sky', subtitle: 'Outlook', desc: 'Send an email via Outlook' },
	whatsapp: { label: 'WhatsApp', category: 'tools', icon: 'chat', tone: 'green', subtitle: 'WhatsApp', desc: 'Send a WhatsApp message' },
	campaign: { label: 'Nurture Campaign', category: 'tools', icon: 'users', tone: 'violet', subtitle: 'Add to Campaign', desc: 'Enrol lead in a nurture sequence' }
};

export const typeOf = (kind: string): NodeType => NODE_TYPES[kind] ?? NODE_TYPES.code;
export const toneOf = (kind: string): Tone => TONES[typeOf(kind).tone] ?? TONES.slate;
