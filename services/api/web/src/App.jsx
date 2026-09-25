import {
  Activity,
  CircleAlert,
  Clock3,
  Database,
  LayoutDashboard,
  Mail,
  PlayCircle,
  RefreshCcw,
  Search,
  Settings,
  Sparkles,
  Workflow,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

const primaryNav = [
  { id: 'workspace', label: 'Agentic Workspace', icon: Sparkles, disabled: true },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'chat', label: 'Chat', icon: Mail, disabled: true },
  { id: 'workflows', label: 'Workflows', icon: Workflow },
  { id: 'forms', label: 'Dynamic Forms', icon: Database, disabled: true },
  { id: 'settings', label: 'Settings', icon: Settings, disabled: true },
]

const studioTabs = [
  { id: 'builder', label: 'Builder' },
  { id: 'runs', label: 'Runs' },
  { id: 'logs', label: 'Logs' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'settings', label: 'Settings' },
]

const terminalStates = new Set(['succeeded', 'failed', 'stopped', 'cancelled', 'completed'])

async function getJson(path) {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

function toStartCase(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function configLabel(workflow) {
  if (workflow.configured) {
    if (workflow.config_source === 'dify_apps') return 'Via DIFY_APPS'
    if (workflow.config_source === 'mixed') return 'Mixed config'
    return 'Configured'
  }
  return 'Needs env'
}

function statusTone(status) {
  if (status === 'succeeded' || status === 'live' || status === 'configured') return 'ok'
  if (status === 'running' || status === 'queued' || status === 'pending') return 'info'
  return 'warn'
}

function formatDateTime(value) {
  if (!value) return 'Not available'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function runDuration(run) {
  if (!run?.started_at) return 'Pending'
  if (!run.finished_at) return 'Running'
  const start = new Date(run.started_at).getTime()
  const end = new Date(run.finished_at).getTime()
  if (Number.isNaN(start) || Number.isNaN(end)) return 'Completed'
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  return `${seconds}s`
}

function initialValuesFromSchema(schema) {
  const properties = schema?.properties ?? {}
  return Object.fromEntries(
    Object.entries(properties).map(([key, field]) => {
      if (field.default !== undefined) return [key, field.default]
      if (field.type === 'boolean') return [key, false]
      return [key, '']
    }),
  )
}

function sanitizeInputs(values, schema) {
  const properties = schema?.properties ?? {}
  return Object.fromEntries(
    Object.entries(values)
      .map(([key, value]) => {
        const field = properties[key] ?? {}
        if (field.type === 'integer') {
          if (value === '' || value === null || value === undefined) return [key, undefined]
          return [key, Number.parseInt(value, 10)]
        }
        if (field.type === 'number') {
          if (value === '' || value === null || value === undefined) return [key, undefined]
          return [key, Number.parseFloat(value)]
        }
        if (field.type === 'boolean') return [key, Boolean(value)]
        if (typeof value === 'string' && value.trim() === '') return [key, undefined]
        return [key, value]
      })
      .filter(([, value]) => value !== undefined && !Number.isNaN(value)),
  )
}

function edgePath(source, target) {
  const startX = source.position.x + (source.size?.width ?? 220)
  const startY = source.position.y + (source.size?.height ?? 132) / 2
  const endX = target.position.x
  const endY = target.position.y + (target.size?.height ?? 132) / 2
  const curve = Math.max(80, Math.abs(endX - startX) * 0.35)
  return `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`
}

function StatusPill({ label, status }) {
  return <span className={`pill pill-${statusTone(status)}`}>{label}</span>
}

function SidebarItem({ item, active, onClick }) {
  const Icon = item.icon
  return (
    <button className={`sidebar-link ${active ? 'sidebar-link-active' : ''}`} onClick={onClick} disabled={item.disabled}>
      <Icon size={16} />
      <span>{item.label}</span>
    </button>
  )
}

function StatCard({ title, value, hint, icon: Icon, tone = 'default' }) {
  return (
    <div className={`card stat-card tone-${tone}`}>
      <div className="stat-header">
        <span>{title}</span>
        <Icon size={18} />
      </div>
      <div className="stat-value">{value}</div>
      <div className="muted">{hint}</div>
    </div>
  )
}

function WorkflowCanvas({ graph, selectedNodeId, onSelectNode }) {
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]))
  const width = Math.max(
    960,
    ...nodes.map((node) => (node.position?.x ?? 0) + (node.size?.width ?? 220) + 80),
  )
  const height = Math.max(
    460,
    ...nodes.map((node) => (node.position?.y ?? 0) + (node.size?.height ?? 132) + 80),
  )

  return (
    <div className="canvas-shell">
      <div className="canvas-toolbar">
        <span className="muted">Read-only workflow graph</span>
        <div className="zoom-pill">100%</div>
      </div>
      <div className="canvas-scroll">
        <div className="canvas-board" style={{ width, height }}>
          <svg className="canvas-edges" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {edges.map((edge, index) => {
              const source = nodeMap[edge.source]
              const target = nodeMap[edge.target]
              if (!source || !target) return null
              return <path key={`${edge.source}-${edge.target}-${index}`} d={edgePath(source, target)} className="canvas-edge" />
            })}
          </svg>
          {nodes.map((node) => (
            <button
              key={node.id}
              className={`node-card node-type-${node.type || 'default'} ${selectedNodeId === node.id ? 'node-card-active' : ''}`}
              style={{
                left: node.position?.x ?? 0,
                top: node.position?.y ?? 0,
                width: node.size?.width ?? 220,
                minHeight: node.size?.height ?? 132,
              }}
              onClick={() => onSelectNode(node.id)}
            >
              <div className="node-badge">{toStartCase(node.type || 'Node')}</div>
              <div className="node-title">{node.title}</div>
              <div className="muted node-subtitle">{node.subtitle}</div>
              {Array.isArray(node.outputs) && node.outputs.length ? (
                <div className="node-ports">
                  {node.outputs.slice(0, 2).map((output) => (
                    <span key={output} className="port-chip">
                      {output}
                    </span>
                  ))}
                </div>
              ) : null}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function StudioField({ name, schema, value, onChange }) {
  const label = schema.title || toStartCase(name)

  if (schema.enum?.length) {
    return (
      <label className="field">
        <span>{label}</span>
        <select value={value ?? ''} onChange={(event) => onChange(name, event.target.value)}>
          <option value="">Select</option>
          {schema.enum.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    )
  }

  if (schema.type === 'boolean') {
    return (
      <label className="toggle-field">
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(name, event.target.checked)} />
        <span>{label}</span>
      </label>
    )
  }

  if (schema.format === 'date') {
    return (
      <label className="field">
        <span>{label}</span>
        <input type="date" value={value ?? ''} onChange={(event) => onChange(name, event.target.value)} />
      </label>
    )
  }

  if (schema.type === 'integer' || schema.type === 'number') {
    return (
      <label className="field">
        <span>{label}</span>
        <input type="number" value={value ?? ''} onChange={(event) => onChange(name, event.target.value)} />
      </label>
    )
  }

  const isTextArea = schema.description || schema.maxLength > 120
  return (
    <label className="field">
      <span>{label}</span>
      {isTextArea ? (
        <textarea rows={3} value={value ?? ''} onChange={(event) => onChange(name, event.target.value)} />
      ) : (
        <input type="text" value={value ?? ''} onChange={(event) => onChange(name, event.target.value)} />
      )}
    </label>
  )
}

function NodePanel({ node }) {
  if (!node) {
    return (
      <div className="card panel-card">
        <div className="section-header">
          <h3>Node Configuration</h3>
        </div>
        <div className="muted">Select a node to inspect its configuration.</div>
      </div>
    )
  }

  const configEntries = Object.entries(node.config ?? {})
  return (
    <div className="card panel-card">
      <div className="section-header">
        <h3>Node Configuration</h3>
        <StatusPill label={toStartCase(node.type || 'node')} status="configured" />
      </div>
      <div className="stack">
        <div>
          <div className="list-title">{node.title}</div>
          <div className="muted">{node.description || node.subtitle}</div>
        </div>
        <div className="detail-block">
          <div className="subheading">Inputs</div>
          <div className="chip-row">
            {(node.inputs?.length ? node.inputs : ['No inputs']).map((item) => (
              <span key={item} className="tag">
                {item}
              </span>
            ))}
          </div>
        </div>
        <div className="detail-block">
          <div className="subheading">Outputs</div>
          <div className="chip-row">
            {(node.outputs?.length ? node.outputs : ['No outputs']).map((item) => (
              <span key={item} className="tag">
                {item}
              </span>
            ))}
          </div>
        </div>
        <div className="detail-block">
          <div className="subheading">Configuration</div>
          {configEntries.length ? (
            <div className="stack compact">
              {configEntries.map(([key, value]) => (
                <div key={key} className="row-between data-row">
                  <span>{toStartCase(key)}</span>
                  <span className="muted">{String(value)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="muted">No extra settings for this node yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}

function RunTimeline({ run }) {
  if (!run) {
    return <div className="muted">Run events will appear here after the first execution.</div>
  }

  const steps = [
    { label: 'Queued', value: run.started_at },
    { label: 'Running', value: run.status === 'running' || run.status === 'queued' ? 'In progress' : run.started_at },
    { label: 'Completed', value: terminalStates.has(run.status) ? formatDateTime(run.finished_at) : 'Waiting' },
  ]

  return (
    <div className="timeline">
      {steps.map((step) => (
        <div key={step.label} className="timeline-item">
          <div className="timeline-dot" />
          <div>
            <div className="list-title">{step.label}</div>
            <div className="muted">{step.value || 'Waiting'}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [section, setSection] = useState('workflows')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [overview, setOverview] = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('')
  const [studio, setStudio] = useState(null)
  const [studioError, setStudioError] = useState('')
  const [workflowRuns, setWorkflowRuns] = useState([])
  const [activeStudioTab, setActiveStudioTab] = useState('builder')
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [formValues, setFormValues] = useState({})
  const [formErrors, setFormErrors] = useState([])
  const [running, setRunning] = useState(false)
  const [currentRunId, setCurrentRunId] = useState('')
  const [currentRun, setCurrentRun] = useState(null)

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null,
    [workflows, selectedWorkflowId],
  )

  const selectedNode = useMemo(
    () => studio?.graph?.nodes?.find((node) => node.id === selectedNodeId) ?? null,
    [studio, selectedNodeId],
  )

  const refreshOverview = async () => {
    const [overviewData, workflowData] = await Promise.all([getJson('/api/overview'), getJson('/api/workflows')])
    setOverview(overviewData)
    setWorkflows(workflowData)
    setSelectedWorkflowId((current) => current || workflowData.find((workflow) => workflow.id === 'lead_qualifier')?.id || workflowData[0]?.id || '')
  }

  const refreshRuns = async (workflowId) => {
    if (!workflowId) return
    const runs = await getJson(`/api/workflows/${workflowId}/runs`)
    setWorkflowRuns(runs)
  }

  useEffect(() => {
    setLoading(true)
    setError('')
    void refreshOverview()
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load dashboard data.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedWorkflowId) {
      setStudio(null)
      return
    }
    setStudioError('')
    void Promise.all([getJson(`/api/workflows/${selectedWorkflowId}/studio`), refreshRuns(selectedWorkflowId)])
      .then(([studioData]) => {
        setStudio(studioData)
        setSelectedNodeId(studioData.graph?.nodes?.[0]?.id || '')
        setFormValues(initialValuesFromSchema(studioData.test_form?.schema))
        setFormErrors([])
        setCurrentRunId('')
        setCurrentRun(null)
      })
      .catch((err) => {
        setStudio(null)
        setStudioError(err instanceof Error ? err.message : 'Could not load workflow studio data.')
      })
  }, [selectedWorkflowId])

  useEffect(() => {
    if (!currentRunId || terminalStates.has(currentRun?.status)) return undefined
    const interval = window.setInterval(() => {
      void getJson(`/api/workflow-runs/${currentRunId}`)
        .then((run) => {
          setCurrentRun(run)
          if (terminalStates.has(run.status)) {
            setRunning(false)
            void refreshRuns(run.workflow_id)
            void refreshOverview()
          }
        })
        .catch(() => undefined)
    }, 1800)
    return () => window.clearInterval(interval)
  }, [currentRunId, currentRun?.status])

  const handleRefresh = async () => {
    setLoading(true)
    setError('')
    try {
      await refreshOverview()
      if (selectedWorkflowId) {
        const [studioData] = await Promise.all([getJson(`/api/workflows/${selectedWorkflowId}/studio`), refreshRuns(selectedWorkflowId)])
        setStudio(studioData)
        setSelectedNodeId((current) => current || studioData.graph?.nodes?.[0]?.id || '')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not refresh dashboard.')
    } finally {
      setLoading(false)
    }
  }

  const handleFieldChange = (name, value) => {
    setFormValues((current) => ({ ...current, [name]: value }))
  }

  const handleRunWorkflow = async () => {
    if (!selectedWorkflowId || !studio?.test_form?.schema) return
    setRunning(true)
    setFormErrors([])
    try {
      const payload = await postJson(`/api/workflows/${selectedWorkflowId}/run`, {
        inputs: sanitizeInputs(formValues, studio.test_form.schema),
        confirm: true,
        wait: false,
      })
      if (payload.status === 'invalid') {
        setFormErrors(payload.errors ?? [])
        setRunning(false)
        return
      }
      setCurrentRunId(payload.run_id)
      setCurrentRun({
        id: payload.run_id,
        workflow_id: selectedWorkflowId,
        status: payload.status,
        outputs: payload.outputs ?? {},
        error: payload.error ?? '',
        started_at: new Date().toISOString(),
      })
      setActiveStudioTab('runs')
      await refreshRuns(selectedWorkflowId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start workflow run.')
      setRunning(false)
    }
  }

  const recentRuns = overview?.recent_runs ?? []
  const recentForms = overview?.recent_forms ?? []
  const integrations = overview?.integrations ?? {}
  const workflowMeta = studio?.workflow ?? {}
  const schemaProperties = studio?.test_form?.schema?.properties ?? {}

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-card">
          <div className="brand-mark">DB</div>
          <div>
            <div className="brand-title">Biz GPT</div>
            <div className="muted">Workflow Studio</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {primaryNav.map((item) => (
            <SidebarItem key={item.id} item={item} active={section === item.id} onClick={() => !item.disabled && setSection(item.id)} />
          ))}
        </nav>

        <div className="sidebar-section">
          <div className="sidebar-section-title">My Workflows</div>
          <div className="sidebar-workflows">
            {workflows.map((workflow) => (
              <button
                key={workflow.id}
                className={`sidebar-workflow ${selectedWorkflowId === workflow.id ? 'sidebar-workflow-active' : ''}`}
                onClick={() => {
                  setSection('workflows')
                  setSelectedWorkflowId(workflow.id)
                }}
              >
                <div>
                  <div className="list-title">{workflow.name}</div>
                  <div className="muted small">{workflow.latest_run ? `${workflow.latest_run.status} · ${runDuration(workflow.latest_run)}` : configLabel(workflow)}</div>
                </div>
                <StatusPill label={workflow.status} status={workflow.status} />
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="topbar-search">
            <Search size={16} />
            <span>Search workflows, tools, docs…</span>
          </div>
          <div className="topbar-actions">
            <div className="environment-pill">
              <Activity size={14} />
              {workflowMeta.environment || 'Production'}
            </div>
            <button className="refresh-button" onClick={() => void handleRefresh()} disabled={loading}>
              <RefreshCcw size={16} />
              Refresh
            </button>
          </div>
        </header>

        {error ? (
          <div className="card error-card">
            <CircleAlert size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        {section === 'dashboard' ? (
          <>
            <header className="page-header">
              <div>
                <div className="eyebrow">Biz GPT</div>
                <h1>General Dashboard</h1>
                <p className="subtitle">Live health, workflow coverage, and recent execution history across the Biz GPT services.</p>
              </div>
            </header>

            <section className="stats-grid">
              <StatCard title="Configured Workflows" value={`${overview?.configured_workflow_count ?? 0}/${overview?.workflow_count ?? 0}`} hint="Registry-backed Dify workflows" icon={Workflow} tone="accent" />
              <StatCard title="Recent Workflow Runs" value={recentRuns.length} hint="Stored in the Biz GPT API run store" icon={PlayCircle} />
              <StatCard title="Recent Forms" value={recentForms.length} hint="Pulled from the forms service" icon={Database} />
              <StatCard title="Integrations" value={integrations.status === 'ok' ? 'Healthy' : 'Check'} hint="Live integrations service status" icon={Mail} tone={integrations.status === 'ok' ? 'success' : 'warn'} />
            </section>

            <section className="content-grid">
              <div className="card">
                <div className="section-header">
                  <h3>System Status</h3>
                </div>
                <div className="stack">
                  <div className="row-between">
                    <span>Integrations service</span>
                    <StatusPill label={integrations.status === 'ok' ? 'Connected' : 'Unavailable'} status={integrations.status === 'ok' ? 'succeeded' : 'failed'} />
                  </div>
                  <div className="row-between">
                    <span>Configured workflows</span>
                    <span className="muted">{overview?.configured_workflow_count ?? 0}</span>
                  </div>
                  <div className="row-between">
                    <span>Recent forms</span>
                    <span className="muted">{recentForms.length}</span>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="section-header">
                  <h3>Recent Workflow Runs</h3>
                </div>
                <div className="stack">
                  {recentRuns.length === 0 ? <div className="muted">No workflow runs yet.</div> : null}
                  {recentRuns.map((run) => (
                    <div key={run.id} className="list-item">
                      <div>
                        <div className="list-title">{toStartCase(run.workflow_id)}</div>
                        <div className="muted">{formatDateTime(run.started_at)}</div>
                      </div>
                      <StatusPill label={run.status} status={run.status} />
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </>
        ) : null}

        {section === 'workflows' ? (
          <>
            <header className="studio-header">
              <div>
                <div className="eyebrow">Workflows</div>
                <h1>{workflowMeta.name || selectedWorkflow?.name || 'Workflow Studio'}</h1>
                <p className="subtitle">{workflowMeta.description || selectedWorkflow?.description || 'Inspect the workflow graph and execute it live.'}</p>
                <div className="tag-row">
                  <StatusPill label={workflowMeta.status || 'live'} status={workflowMeta.status || 'live'} />
                  <span className="tag">{workflowMeta.version || 'v1.0'}</span>
                  {workflowMeta.tags?.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
              <div className="header-actions">
                <div className="muted">{configLabel(workflowMeta)}</div>
                <StatusPill label={workflowMeta.configured ? 'Configured' : 'Needs setup'} status={workflowMeta.configured ? 'configured' : 'failed'} />
              </div>
            </header>

            <div className="tab-row">
              {studioTabs.map((tab) => (
                <button key={tab.id} className={`tab ${activeStudioTab === tab.id ? 'tab-active' : ''}`} onClick={() => setActiveStudioTab(tab.id)}>
                  {tab.label}
                </button>
              ))}
            </div>

            {studioError ? (
              <div className="card error-card">
                <CircleAlert size={18} />
                <span>{studioError}</span>
              </div>
            ) : null}

            {activeStudioTab === 'builder' ? (
              <section className="studio-grid">
                <div className="card studio-main-card">
                  <div className="section-header">
                    <h3>Builder</h3>
                    <span className="muted">Read-only graph backed by Biz GPT studio metadata</span>
                  </div>
                  {studio ? (
                    <WorkflowCanvas graph={studio.graph} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />
                  ) : (
                    <div className="loading-card">Loading workflow studio…</div>
                  )}
                </div>

                <NodePanel node={selectedNode} />
              </section>
            ) : null}

            {activeStudioTab === 'runs' ? (
              <section className="content-grid workflow-grid">
                <div className="card">
                  <div className="section-header">
                    <h3>Latest Run</h3>
                    {currentRun ? <StatusPill label={currentRun.status} status={currentRun.status} /> : null}
                  </div>
                  <div className="stack">
                    <div className="row-between">
                      <span>Local run id</span>
                      <span className="muted">{currentRun?.id || currentRunId || 'Not started'}</span>
                    </div>
                    <div className="row-between">
                      <span>Started</span>
                      <span className="muted">{formatDateTime(currentRun?.started_at)}</span>
                    </div>
                    <div className="row-between">
                      <span>Duration</span>
                      <span className="muted">{runDuration(currentRun)}</span>
                    </div>
                    {currentRun?.error ? (
                      <div className="card error-card inline-card">
                        <CircleAlert size={16} />
                        <span>{currentRun.error}</span>
                      </div>
                    ) : null}
                    <RunTimeline run={currentRun} />
                  </div>
                </div>

                <div className="card">
                  <div className="section-header">
                    <h3>Workflow Runs</h3>
                    <span className="muted">{workflowRuns.length} total</span>
                  </div>
                  <div className="stack">
                    {workflowRuns.length === 0 ? <div className="muted">No runs recorded yet.</div> : null}
                    {workflowRuns.map((run) => (
                      <button key={run.id} className="workflow-row" onClick={() => { setCurrentRunId(run.id); setCurrentRun(run) }}>
                        <div>
                          <div className="list-title">{run.id}</div>
                          <div className="muted">{formatDateTime(run.started_at)}</div>
                        </div>
                        <StatusPill label={run.status} status={run.status} />
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            ) : null}

            {activeStudioTab === 'logs' ? (
              <section className="content-grid workflow-grid">
                <div className="card">
                  <div className="section-header">
                    <h3>Run Log</h3>
                    <Clock3 size={16} />
                  </div>
                  <RunTimeline run={currentRun} />
                </div>
                <div className="card">
                  <div className="section-header">
                    <h3>Output</h3>
                  </div>
                  <pre className="code-block">{JSON.stringify(currentRun?.outputs ?? {}, null, 2)}</pre>
                </div>
              </section>
            ) : null}

            {activeStudioTab === 'analytics' || activeStudioTab === 'settings' ? (
              <section className="content-grid">
                <div className="card">
                  <div className="section-header">
                    <h3>{activeStudioTab === 'analytics' ? 'Analytics' : 'Settings'}</h3>
                  </div>
                  <div className="muted">
                    This tab is ready for the next slice. The live studio, runs, and logs are now wired to the existing Biz GPT workflow API.
                  </div>
                </div>
              </section>
            ) : null}

            <section className="card run-panel">
              <div className="section-header">
                <div>
                  <h3>Test Run</h3>
                  <div className="muted">Execute the selected workflow with live status updates from the Biz GPT API.</div>
                </div>
                <button className="primary-button" onClick={() => void handleRunWorkflow()} disabled={running || !workflowMeta.configured}>
                  <PlayCircle size={16} />
                  {running ? 'Running…' : 'Run workflow'}
                </button>
              </div>

              {!workflowMeta.configured && workflowMeta.config_missing?.length ? (
                <div className="card error-card inline-card">
                  <CircleAlert size={16} />
                  <span>{workflowMeta.config_missing.join(' | ')}</span>
                </div>
              ) : null}

              <div className="run-panel-grid">
                <div className="run-form-grid">
                  {Object.entries(schemaProperties).map(([name, schema]) => (
                    <StudioField key={name} name={name} schema={schema} value={formValues[name]} onChange={handleFieldChange} />
                  ))}
                </div>
                <div className="run-sidebar">
                  <div className="detail-block">
                    <div className="subheading">Current Run Status</div>
                    <StatusPill label={currentRun?.status || 'Idle'} status={currentRun?.status || 'pending'} />
                  </div>
                  <div className="detail-block">
                    <div className="subheading">Provider</div>
                    <div className="muted">{workflowMeta.matched_app?.name || workflowMeta.matched_app?.id || 'Registry-backed workflow'}</div>
                  </div>
                  <div className="detail-block">
                    <div className="subheading">Validation</div>
                    {formErrors.length ? (
                      <div className="stack compact">
                        {formErrors.map((item, index) => (
                          <div key={`${item.field}-${index}`} className="muted">
                            {item.field || 'workflow'}: {item.message}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="muted">Schema validation passes on the latest draft.</div>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </>
        ) : null}

        {loading && !overview ? <div className="card loading-card">Loading dashboard…</div> : null}
      </main>
    </div>
  )
}
