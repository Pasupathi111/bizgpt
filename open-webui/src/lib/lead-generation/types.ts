// Shared types for the Lead Generation workflow builder.

export type Handle = 'out' | 'true' | 'false';

export interface WFNode {
	id: string;
	kind: string;
	title: string;
	subtitle: string;
	desc: string;
	x: number;
	y: number;
	config: Record<string, any>;
}

export interface WFEdge {
	id: string;
	from: string;
	to: string;
	handle: Handle;
	label?: string;
}

export type WorkflowStatus = 'active' | 'draft' | 'paused';

export interface Workflow {
	id: string;
	name: string;
	description: string;
	category: string;
	status: WorkflowStatus;
	trigger: string;
	runs: number;
	successRate: number;
	leads: number;
	lastRun: string;
	owner: string;
	updated: string;
	version: string;
	tags: string[];
	nodes: WFNode[];
	edges: WFEdge[];
}

export type NodeStatus = 'idle' | 'running' | 'success' | 'skipped' | 'error';
export type EdgeStatus = 'idle' | 'active' | 'done' | 'skipped';
export type RunStatus = 'idle' | 'running' | 'success' | 'failed';

export interface RunStep {
	nodeId: string;
	ms: number;
	output: Record<string, any>;
	log: string;
	/** edge ids that were traversed to reach this node */
	via: string[];
}

export interface RunPlan {
	steps: RunStep[];
	skippedNodes: string[];
	skippedEdges: string[];
	output: Record<string, any>;
}

export interface LogLine {
	time: string;
	level: 'info' | 'success' | 'warn' | 'error';
	node?: string;
	message: string;
}

export interface RunRecord {
	id: string;
	workflowId: string;
	workflowName: string;
	status: 'success' | 'failed' | 'running';
	trigger: string;
	durationMs: number;
	startedAt: string;
	lead: string;
	score: number | null;
	nodes: number;
}
