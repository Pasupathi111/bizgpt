// Canvas geometry: node size, handle positions and edge paths.
import type { Handle, WFNode } from '../types';

export const NODE_W = 212;
export const NODE_H = 104;

export const outPoint = (n: WFNode, handle: Handle) =>
	handle === 'false' ? { x: n.x + NODE_W / 2, y: n.y + NODE_H } : { x: n.x + NODE_W, y: n.y + NODE_H / 2 };

export const inPoint = (n: WFNode) => ({ x: n.x, y: n.y + NODE_H / 2 });

export interface EdgeGeom {
	d: string;
	lx: number;
	ly: number;
}

/** Path from a source handle to a target input. Handles forward, backward (row wrap) and bottom exits. */
export function edgeGeom(s: { x: number; y: number }, t: { x: number; y: number }, handle: Handle): EdgeGeom {
	if (handle === 'false') {
		if (t.x > s.x + 24) {
			return {
				d: `M${s.x},${s.y} C${s.x},${t.y} ${s.x},${t.y} ${t.x},${t.y}`,
				lx: s.x,
				ly: s.y + (t.y - s.y) * 0.38
			};
		}
		return {
			d: `M${s.x},${s.y} C${s.x},${s.y + 90} ${t.x - 90},${t.y} ${t.x},${t.y}`,
			lx: (s.x + t.x) / 2,
			ly: (s.y + t.y) / 2
		};
	}

	if (t.x >= s.x + 30) {
		const dx = Math.max(40, (t.x - s.x) / 2);
		return {
			d: `M${s.x},${s.y} C${s.x + dx},${s.y} ${t.x - dx},${t.y} ${t.x},${t.y}`,
			lx: (s.x + t.x) / 2,
			ly: (s.y + t.y) / 2
		};
	}

	// Target is behind the source: wrap around with rounded corners.
	const out = 30;
	const r = 14;
	const midY = Math.abs(t.y - s.y) < NODE_H ? Math.max(s.y, t.y) + NODE_H * 0.85 : s.y + (t.y - s.y) / 2;
	const s1 = midY > s.y ? 1 : -1;
	const s2 = t.y > midY ? 1 : -1;
	const d = [
		`M${s.x},${s.y}`,
		`H${s.x + out - r}`,
		`Q${s.x + out},${s.y} ${s.x + out},${s.y + r * s1}`,
		`V${midY - r * s1}`,
		`Q${s.x + out},${midY} ${s.x + out - r},${midY}`,
		`H${t.x - out + r}`,
		`Q${t.x - out},${midY} ${t.x - out},${midY + r * s2}`,
		`V${t.y - r * s2}`,
		`Q${t.x - out},${t.y} ${t.x - out + r},${t.y}`,
		`H${t.x}`
	].join(' ');
	return { d, lx: (s.x + t.x) / 2, ly: midY };
}

export function bounds(nodes: WFNode[]) {
	if (!nodes.length) return { minX: 0, minY: 0, maxX: 800, maxY: 400 };
	let minX = Infinity,
		minY = Infinity,
		maxX = -Infinity,
		maxY = -Infinity;
	for (const n of nodes) {
		minX = Math.min(minX, n.x);
		minY = Math.min(minY, n.y);
		maxX = Math.max(maxX, n.x + NODE_W);
		maxY = Math.max(maxY, n.y + NODE_H);
	}
	return { minX, minY, maxX, maxY };
}
