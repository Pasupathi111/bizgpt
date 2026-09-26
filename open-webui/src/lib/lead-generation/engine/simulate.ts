// Deterministic run simulator: walks the graph from the trigger, evaluates
// branches against the test input and produces per-node outputs and logs.
import type { RunPlan, RunStep, WFEdge, WFNode, Workflow } from '../types';

export interface Lead {
	name: string;
	first_name: string;
	email: string;
	company: string;
	job_title: string;
	phone: string;
	source: string;
	message?: string;
}

const SENIOR = /\b(ceo|cto|cfo|coo|cio|founder|co-founder|owner|president|vp|vice president|head|director|chief)\b/i;
const MID = /\b(manager|lead|architect|principal|senior)\b/i;
const FREE_MAIL = /@(gmail|yahoo|hotmail|outlook|live|icloud|proton)\./i;

const titleCase = (s: string) => s.replace(/(^|[\s-])\w/g, (m) => m.toUpperCase());

export function normaliseLead(input: Record<string, any>): Lead {
	let { name = '', email = '', company = '', job_title = '', phone = '', source = 'Manual' } = input;
	const text = [input.subject, input.body, input.message].filter(Boolean).join(' ');

	if (input.from) {
		const m = String(input.from).match(/^\s*"?([^"<]*)"?\s*<([^>]+)>/);
		if (m) {
			name ||= m[1].trim();
			email ||= m[2].trim();
		} else email ||= String(input.from).trim();
	}
	if (!job_title && text) job_title = (text.match(SENIOR) || text.match(MID) || [''])[0];
	if (job_title) job_title = job_title.length <= 4 ? job_title.toUpperCase() : titleCase(job_title);
	if (!phone && text) phone = (text.match(/\+?\d[\d\s-]{8,}\d/) || [''])[0];
	if (!company && email && !FREE_MAIL.test(email)) {
		const domain = email.split('@')[1]?.split('.')[0] ?? '';
		company = titleCase(domain);
	}
	return {
		name: name || 'Unknown',
		first_name: (name || 'there').split(' ')[0],
		email,
		company,
		job_title,
		phone,
		source,
		message: text || undefined
	};
}

export function scoreLead(lead: Lead) {
	const factors: { factor: string; points: number }[] = [];
	const add = (factor: string, points: number) => points && factors.push({ factor, points });
	add('Base', 25);
	add(SENIOR.test(lead.job_title) ? 'Senior decision maker' : MID.test(lead.job_title) ? 'Mid-level role' : 'Junior / unknown role', SENIOR.test(lead.job_title) ? 30 : MID.test(lead.job_title) ? 15 : 0);
	add('Business email domain', lead.email && !FREE_MAIL.test(lead.email) ? 15 : 0);
	add('Company identified', lead.company ? 8 : 0);
	add('Phone provided', lead.phone ? 5 : 0);
	add('High-intent source', /website|email|referral|demo|pricing/i.test(lead.source) ? 7 : 0);
	add('Buying intent in message', /pricing|demo|quote|seats|evaluate|budget/i.test(lead.message ?? '') ? 5 : 0);
	const score = Math.min(98, factors.reduce((a, f) => a + f.points, 0));
	const grade = score >= 80 ? 'Hot' : score >= 50 ? 'Warm' : 'Cold';
	return { score, grade, factors };
}

function hash(s: string) {
	let h = 2166136261;
	for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
	return Math.abs(h);
}

const BASE_MS: Record<string, number> = {
	llm: 3100, classifier: 1500, knowledge: 1150, score: 780, extractor: 880, http: 1380, database: 420, sheet: 610,
	webhook: 520, crm: 1090, gmail: 1460, outlook: 1390, whatsapp: 870, campaign: 690, code: 140, iterator: 290,
	wait: 40, router: 18, 'if-else': 16
};

const industryFor = (company: string) =>
	/tech|labs|soft|data|ai|lytics|io/i.test(company) ? 'IT Services' : /retail|mart|store/i.test(company) ? 'Retail' : company ? 'Professional Services' : 'Unknown';

export function planRun(wf: Workflow, input: Record<string, any>): RunPlan {
	const lead = normaliseLead(input);
	const { score, grade, factors } = scoreLead(lead);
	const qualified = score > 70;
	const domain = lead.email.split('@')[1] ?? '';
	const enriched = {
		company_size: score >= 70 ? '50-200' : lead.company ? '11-50' : 'Unknown',
		industry: industryFor(lead.company),
		linkedin: lead.company ? `https://linkedin.com/company/${lead.company.toLowerCase().replace(/\s+/g, '-')}` : null,
		website: domain && !FREE_MAIL.test(lead.email) ? `https://${domain}` : null,
		location: lead.phone.startsWith('+91') ? 'India' : 'Unknown'
	};
	const summary = lead.company
		? `${lead.job_title || 'Contact'} at ${lead.company}. ${qualified ? 'Showing strong interest in AI solutions for their enterprise; good ICP fit.' : 'Moderate fit — recommend nurturing before sales outreach.'}`
		: `${lead.name} did not share a company and uses a personal email. Low buying signal — nurture only.`;

	const byId = new Map(wf.nodes.map((n) => [n.id, n]));
	const incoming = new Set(wf.edges.map((e) => e.to));
	const outgoing = (id: string) => wf.edges.filter((e) => e.from === id);

	const conditionTrue = (node: WFNode) => {
		const { variable, operator, value } = node.config;
		if (variable === 'lead_score' || variable === 'fit_score') {
			const v = Number(value);
			return operator === '>=' ? score >= v : operator === '<' ? score < v : operator === '<=' ? score <= v : score > v;
		}
		return score >= 60;
	};

	const outputFor = (node: WFNode): { output: Record<string, any>; log: string } => {
		switch (node.kind) {
			case 'form-trigger':
			case 'webhook-trigger':
			case 'gmail-trigger':
			case 'csv-trigger':
				return { output: { ...input }, log: `Received payload from ${lead.source} (${Object.keys(input).length} fields)` };
			case 'schedule-trigger':
				return { output: { fired_at: new Date().toISOString(), cron: node.config.cron }, log: `Manual test fire (cron ${node.config.cron})` };
			case 'extractor':
				return { output: { name: lead.name, email: lead.email, company: lead.company, job_title: lead.job_title, phone: lead.phone }, log: `Extracted 5 fields for ${lead.name}` };
			case 'http':
				return { output: { status: 200, data: enriched }, log: `GET ${String(node.config.url).split('?')[0]} → 200 OK` };
			case 'llm':
				return {
					output: { model: node.config.model, summary, intent: qualified ? 'High' : 'Low', usage: { prompt_tokens: 812, completion_tokens: 96 } },
					log: `${node.config.model} · 908 tokens · summary generated`
				};
			case 'classifier':
				return { output: { class: qualified ? 'Sales lead' : 'Other', confidence: qualified ? 0.94 : 0.71 }, log: `Classified as "${qualified ? 'Sales lead' : 'Other'}"` };
			case 'knowledge':
				return { output: { chunks: 3, top_score: 0.87, answer: 'Shared pricing overview and docs link.' }, log: 'Retrieved 3 chunks (top score 0.87)' };
			case 'score':
				return { output: { lead_score: score, grade, factors }, log: `Lead score ${score} (${grade})` };
			case 'if-else': {
				const ok = conditionTrue(node);
				return {
					output: { condition: `${node.config.variable} ${node.config.operator} ${node.config.value}`, result: ok, branch: ok ? 'Yes' : 'No' },
					log: `Condition ${node.config.variable} ${node.config.operator} ${node.config.value} → ${ok ? 'Yes' : 'No'}`
				};
			}
			case 'router':
				return { output: { route: grade }, log: `Routed to "${grade}"` };
			case 'crm':
				return {
					output: { provider: node.config.provider, record_id: `hs_${hash(lead.email || lead.name) % 9_000_000 + 1_000_000}`, object: node.config.object, stage: node.config.stage },
					log: `${node.config.provider}: ${node.config.object} created in "${node.config.stage}"`
				};
			case 'gmail':
			case 'outlook':
				return {
					output: { message_id: `<${hash(node.id + lead.email).toString(36)}@mail.bizgpt.ai>`, to: lead.email, subject: String(node.config.subject ?? '').replace('{{lead.first_name}}', lead.first_name), status: node.config.mode === 'Save as draft' ? 'draft_saved' : 'sent' },
					log: `Email ${node.config.mode === 'Save as draft' ? 'draft saved' : 'sent'} to ${lead.email || 'lead'}`
				};
			case 'whatsapp':
				return { output: { to: node.config.to, status: 'delivered' }, log: `WhatsApp alert delivered to ${node.config.to}` };
			case 'campaign':
				return { output: { sequence: node.config.sequence, enrolled: true, step: 1 }, log: `Enrolled in "${node.config.sequence}"` };
			case 'sheet':
				return { output: { spreadsheet: node.config.spreadsheet, rows_appended: 1 }, log: `Appended 1 row to ${node.config.sheet ?? 'sheet'}` };
			case 'database':
				return { output: { rows: 24 }, log: 'Query returned 24 rows' };
			case 'iterator':
				return { output: { items: 24, parallel: node.config.parallel }, log: `Iterating 24 items (parallel ${node.config.parallel})` };
			case 'wait':
				return { output: { resume_at: `+${node.config.duration} ${node.config.unit}`, skipped_in_test: true }, log: `Wait ${node.config.duration} ${node.config.unit} (skipped in test run)` };
			case 'code':
				return { output: { ok: true }, log: 'Code executed (exit 0)' };
			default:
				return { output: {}, log: 'Done' };
		}
	};

	const steps: RunStep[] = [];
	const visited = new Set<string>();
	const takenEdges = new Set<string>();
	const via = new Map<string, string[]>();
	const queue = wf.nodes.filter((n) => !incoming.has(n.id)).map((n) => n.id);

	while (queue.length) {
		const id = queue.shift()!;
		if (visited.has(id)) continue;
		const node = byId.get(id);
		if (!node) continue;
		visited.add(id);

		const { output, log } = outputFor(node);
		const ms = Math.round((BASE_MS[node.kind] ?? 30) * (0.8 + (hash(node.id + lead.email) % 40) / 100));
		steps.push({ nodeId: id, ms, output, log, via: via.get(id) ?? [] });

		let next: WFEdge[] = outgoing(id);
		if (node.kind === 'if-else') {
			const branch = output.result ? 'true' : 'false';
			next = next.filter((e) => e.handle === branch);
		} else if (node.kind === 'router') {
			const match = next.filter((e) => e.label === grade);
			next = match.length ? match : next.slice(0, 1);
		}
		for (const e of next) {
			takenEdges.add(e.id);
			via.set(e.to, [...(via.get(e.to) ?? []), e.id]);
			queue.push(e.to);
		}
	}

	const actionName: Record<string, string> = {
		crm: 'lead_created', gmail: 'email_sent', outlook: 'email_sent', whatsapp: 'sales_notified',
		campaign: 'added_to_nurture', sheet: 'row_appended', knowledge: 'kb_answer_sent', code: 'labelled'
	};
	const actions = [
		...new Set(
			steps
				.map((s) => {
					const node = byId.get(s.nodeId)!;
					if (node.kind === 'gmail' && /welcome/i.test(String(node.config.template ?? ''))) return 'welcome_email_sent';
					if (node.kind === 'gmail' && node.config.mode === 'Save as draft') return 'reply_drafted';
					return actionName[node.kind];
				})
				.filter(Boolean)
		)
	];

	return {
		steps,
		skippedNodes: wf.nodes.filter((n) => !visited.has(n.id)).map((n) => n.id),
		skippedEdges: wf.edges.filter((e) => !takenEdges.has(e.id)).map((e) => e.id),
		output: {
			lead_score: score,
			qualification: grade === 'Hot' ? 'High' : grade === 'Warm' ? 'Medium' : 'Low',
			summary,
			lead: { name: lead.name, email: lead.email, company: lead.company || null, job_title: lead.job_title || null },
			enriched_data: { company_size: enriched.company_size, industry: enriched.industry, linkedin: enriched.linkedin },
			actions
		}
	};
}
