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
	href?: string | null;
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

// ---------- Integrations → WhatsApp (admin; proxied to the WhatsApp service) ----------

export type WhatsAppCheck = { ok: boolean; status?: string; detail?: string | null; [key: string]: unknown };

export type WhatsAppAccount = {
	phone_number_id: string;
	business_account_id: string | null;
	display_phone_number: string | null;
	verified_name: string | null;
	agent_model: string;
	auto_reply: boolean;
	is_active: boolean;
	stats: {
		contacts: number;
		conversations: number;
		messages_inbound: number;
		messages_outbound: number;
		messages_failed: number;
		messages_24h: number;
	};
};

export type WhatsAppOverview = {
	reachable: boolean;
	detail?: string;
	account?: WhatsAppAccount;
	status?: {
		status: 'ok' | 'degraded';
		whatsapp_api: WhatsAppCheck;
		openwebui: WhatsAppCheck;
		database: WhatsAppCheck;
		webhook: WhatsAppCheck & { verify_token_set: boolean; signature_verification: boolean; path: string };
	} | null;
};

export type WhatsAppConversation = {
	id: string;
	contact: { wa_id: string; profile_name: string | null };
	openwebui_chat_id: string | null;
	status: string;
	last_message_at: string | null;
	within_service_window: boolean;
};

const whatsappRequest = async (token: string, path = '', init: RequestInit = {}) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/bizgpt/whatsapp${path}`, {
		...init,
		headers: { Accept: 'application/json', 'Content-Type': 'application/json', authorization: `Bearer ${token}` }
	});
	const body = await res.json().catch(() => ({}));
	if (!res.ok) throw body?.detail ?? `WhatsApp request failed (${res.status})`;
	return body;
};

export const getWhatsApp = (token: string): Promise<WhatsAppOverview> => whatsappRequest(token);

export const updateWhatsAppSettings = (
	token: string,
	settings: Partial<Pick<WhatsAppAccount, 'agent_model' | 'auto_reply' | 'is_active'>>
): Promise<WhatsAppAccount> => whatsappRequest(token, '/settings', { method: 'PUT', body: JSON.stringify(settings) });

export const testWhatsApp = (
	token: string
): Promise<{ ok: boolean; whatsapp: WhatsAppCheck; openwebui: WhatsAppCheck }> =>
	whatsappRequest(token, '/test', { method: 'POST' });

export const getWhatsAppConversations = (token: string, limit = 8): Promise<WhatsAppConversation[]> =>
	whatsappRequest(token, `/conversations?limit=${limit}`);
