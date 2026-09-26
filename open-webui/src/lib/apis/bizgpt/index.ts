import { WEBUI_API_BASE_URL } from '$lib/constants';

export type DashboardSeries = {
	workflow_runs: number[];
	form_submissions: number[];
	messages: number[];
	tool_calls: number[];
};

export type DashboardIntegration = {
	id: string;
	name: string;
	kind: string;
	status: 'connected' | 'down' | 'restricted' | 'not_connected' | 'not_configured' | 'unavailable';
	detail?: string;
	account?: string | null;
};

export type DashboardActivity = {
	type: 'form' | 'workflow' | 'email';
	title: string;
	detail: string;
	status: string;
	at: number;
};

export type DashboardInboxMessage = {
	id: string;
	from: string;
	subject: string;
	at: number | null;
	link: string;
	unread?: boolean;
};

export type DashboardData = {
	generated_at: number;
	user: { name: string; role: string };
	scope: 'workspace' | 'personal';
	cards: {
		workflows: { total: number; active: number; available: boolean };
		forms: { types: number; custom: number; submissions: number; available: boolean };
		integrations: { connected: number; total: number };
		nango: { up: boolean; connections: number };
		inbox: { available: boolean; unread: number; unread_capped: boolean; reason: string | null };
	};
	activity: { days: string[]; series: DashboardSeries };
	recent_activity: DashboardActivity[];
	integrations: DashboardIntegration[];
	inbox: {
		available: boolean;
		mailbox: string;
		unread: number;
		unread_capped: boolean;
		breakdown?: { total: number; unread: number; important: number; starred: number; others: number; capped: boolean };
		recent: DashboardInboxMessage[];
	} | null;
	workflows: { id: string; name: string; status: string; configured: boolean }[];
	links: { dify_console: string | null; nango_dashboard: string | null };
};

export const getDashboard = async (token: string, days = 7): Promise<DashboardData> => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/bizgpt/dashboard?days=${days}`, {
		headers: { Accept: 'application/json', authorization: `Bearer ${token}` }
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw body?.detail ?? `Dashboard request failed (${res.status})`;
	}
	return res.json();
};
