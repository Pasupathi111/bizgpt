// Monthly Report POC API: served by services/monthly-report through the Biz GPT backend
// (/api/v1/bizgpt/monthly-report, see backend/open_webui/bizgpt/monthly_report.py).
import { WEBUI_API_BASE_URL } from '$lib/constants';

export const API = `${WEBUI_API_BASE_URL}/bizgpt/monthly-report`;

const auth = () => ({ Authorization: `Bearer ${localStorage.token ?? ''}` });

export const api = async (path: string, init: RequestInit = {}) => {
	const json = typeof init.body === 'string';
	const res = await fetch(`${API}${path}`, {
		...init,
		headers: { ...(json ? { 'Content-Type': 'application/json' } : {}), ...auth(), ...(init.headers ?? {}) }
	});
	const data = await res.json().catch(() => ({}));
	if (!res.ok) {
		const detail = data?.detail;
		throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`);
	}
	return data;
};

export const blobUrl = async (path: string) => {
	const res = await fetch(`${API}${path}`, { headers: auth() });
	if (!res.ok) throw new Error(`Could not load file (${res.status})`);
	return URL.createObjectURL(await res.blob());
};
