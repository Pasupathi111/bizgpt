// Full class strings (not interpolated) so Tailwind keeps them in the build.
export const TONES = {
	violet: {
		tile: 'bg-violet-100 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300',
		soft: 'bg-violet-50 hover:bg-violet-100/70 dark:bg-violet-500/10 dark:hover:bg-violet-500/15',
		text: 'text-violet-600 dark:text-violet-300',
		stroke: '#7c3aed'
	},
	emerald: {
		tile: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300',
		soft: 'bg-emerald-50 hover:bg-emerald-100/70 dark:bg-emerald-500/10 dark:hover:bg-emerald-500/15',
		text: 'text-emerald-600 dark:text-emerald-300',
		stroke: '#10b981'
	},
	orange: {
		tile: 'bg-orange-100 text-orange-600 dark:bg-orange-500/15 dark:text-orange-300',
		soft: 'bg-orange-50 hover:bg-orange-100/70 dark:bg-orange-500/10 dark:hover:bg-orange-500/15',
		text: 'text-orange-600 dark:text-orange-300',
		stroke: '#f97316'
	},
	sky: {
		tile: 'bg-sky-100 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300',
		soft: 'bg-sky-50 hover:bg-sky-100/70 dark:bg-sky-500/10 dark:hover:bg-sky-500/15',
		text: 'text-sky-600 dark:text-sky-300',
		stroke: '#3b82f6'
	},
	rose: {
		tile: 'bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300',
		soft: 'bg-rose-50 hover:bg-rose-100/70 dark:bg-rose-500/10 dark:hover:bg-rose-500/15',
		text: 'text-rose-600 dark:text-rose-300',
		stroke: '#f43f5e'
	}
} as const;

export type Tone = keyof typeof TONES;

export const STATUS_BADGE: Record<string, string> = {
	success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
	connected: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
	unread: 'bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300',
	draft: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
	info: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
	restricted: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
	not_connected: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
	not_configured: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
	expired: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
	down: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300',
	unavailable: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300',
	failed: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300'
};

export const STATUS_LABEL: Record<string, string> = {
	success: 'Success',
	connected: 'Connected',
	unread: 'Unread',
	draft: 'Open',
	info: 'Read',
	restricted: 'Admin only',
	not_connected: 'Not connected',
	not_configured: 'Not set up',
	expired: 'Expired',
	down: 'Down',
	unavailable: 'Unavailable',
	failed: 'Failed'
};

export const timeAgo = (ts: number | null | undefined): string => {
	if (!ts) return '';
	const s = Math.max(0, Date.now() / 1000 - ts);
	if (s < 60) return 'just now';
	if (s < 3600) return `${Math.floor(s / 60)} min ago`;
	if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
	const d = Math.floor(s / 86400);
	return d === 1 ? 'yesterday' : `${d} days ago`;
};
