import Form from '@rjsf/shadcn'
import type { ErrorSchema, RJSFSchema, UiSchema } from '@rjsf/utils'
import validator from '@rjsf/validator-ajv8'
import { AlertCircle, CheckCircle2, ClipboardList, Loader2, Pencil, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Badge, Button, Card } from './ui'

type Values = Record<string, unknown>

type PublicForm = {
  mode: 'form'
  form_id: string
  title: string
  description: string
  schema: RJSFSchema
  ui_schema: UiSchema
  submit_label: string
  form_data: Values
  prefilled_fields: string[]
  status: 'draft' | 'submitted' | 'executed' | 'expired'
  result: {
    message?: string
    reference?: string
    error?: string
    workflow_run_id?: string
    task_id?: string
    elapsed_time?: number
    delivery?: Record<string, unknown>
    outputs?: Record<string, unknown>
  } | null
}

type PublicView = {
  mode: 'view'
  view_id: string
  title: string
  description: string
  schema: RJSFSchema
  ui_schema: UiSchema
  form_data: Values
  status: 'view'
}

type PublicPayload = PublicForm | PublicView

type Stage = 'edit' | 'review' | 'submitting' | 'done'

const pathParts = location.pathname.split('/').filter(Boolean)
const entityType = pathParts[0] === 'v' ? 'view' : 'form'
const entityId = decodeURIComponent(pathParts.at(-1) ?? '')

// Tell Open WebUI (our parent frame) how tall we are, and hand results back to the chat.
const toParent = (message: object) => window.parent !== window && window.parent.postMessage(message, '*')

function useReportHeight() {
  useLayoutEffect(() => {
    const report = () => toParent({ type: 'iframe:height', height: document.documentElement.scrollHeight })
    const observer = new ResizeObserver(report)
    observer.observe(document.body)
    report()
    return () => observer.disconnect()
  }, [])
}

function displayValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function titleize(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

type WorkflowStep = {
  title?: string
  status?: string
  details?: string
}

type GeneratedLead = {
  name?: string
  title?: string
  company?: string
  email?: string
  linkedin?: string
  score?: number
  reason?: string
}

export default function App() {
  const [form, setForm] = useState<PublicPayload | null>(null)
  const [loadError, setLoadError] = useState('')
  const [values, setValues] = useState<Values>({})
  const [stage, setStage] = useState<Stage>('edit')
  const [extraErrors, setExtraErrors] = useState<ErrorSchema | undefined>()
  const [banner, setBanner] = useState('')
  const [doneMessage, setDoneMessage] = useState('')
  useReportHeight()

  useEffect(() => {
    const apiPath =
      entityType === 'view'
        ? `/api/public/views/${encodeURIComponent(entityId)}`
        : `/api/public/forms/${encodeURIComponent(entityId)}`
    fetch(apiPath)
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? 'This link is not valid.' : `Could not load item (${r.status}).`)
        return r.json() as Promise<PublicPayload>
      })
      .then((f) => {
        setForm(f)
        setValues(f.form_data ?? {})
        if (f.mode === 'view') {
          setStage('done')
          setDoneMessage('Structured output loaded successfully.')
          return
        }
        if (f.status === 'executed' || f.status === 'submitted') {
          setStage('done')
          setDoneMessage(f.result?.message ?? 'This form has already been submitted.')
        }
        if (f.result?.error) setBanner(`Last attempt failed: ${f.result.error}`)
      })
      .catch((e: Error) => setLoadError(e.message))
  }, [])

  const properties = useMemo(() => (form?.schema.properties ?? {}) as Record<string, { title?: string }>, [form])
  const order = useMemo(() => {
    const uiOrder = (form?.ui_schema['ui:order'] as string[] | undefined) ?? []
    return [...uiOrder.filter((k) => k in properties), ...Object.keys(properties).filter((k) => !uiOrder.includes(k))]
  }, [form, properties])

  const uiSchema = useMemo<UiSchema>(
    () =>
      form?.mode === 'view'
        ? { ...form?.ui_schema, 'ui:submitButtonOptions': { norender: true } }
        : { ...form?.ui_schema, 'ui:submitButtonOptions': { submitText: (form as PublicForm | null)?.submit_label ?? 'Review' } },
    [form],
  )

  const submit = useCallback(async () => {
    if (!form || form.mode === 'view') return
    setStage('submitting')
    setBanner('')
    const r = await fetch(`/api/public/forms/${encodeURIComponent(form.form_id)}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ values }),
    }).catch(() => null)
    const body = r ? await r.json().catch(() => ({})) : {}

    if (r?.ok) {
      setDoneMessage(body.message)
      setForm((current) =>
        current && current.mode === 'form'
          ? {
              ...current,
              status: 'executed',
              result: body.result ?? current.result,
            }
          : current,
      )
      setStage('done')
      // Continue the conversation: Open WebUI asks the user to confirm prompts from embeds.
      toParent({ type: 'input:prompt:submit', text: `✅ ${form.title} submitted. ${body.message}` })
      return
    }
    if (r?.status === 422 && Array.isArray(body.errors)) {
      const errs: ErrorSchema = {}
      for (const e of body.errors as { field: string; message: string }[]) {
        const key = e.field || '__root'
        ;(errs as Record<string, unknown>)[key] = { __errors: [e.message] }
      }
      setExtraErrors(errs)
      setBanner('Please fix the highlighted fields.')
      setStage('edit')
      return
    }
    setBanner(body.message ?? body.detail ?? 'Submission failed. Please try again.')
    setStage(r?.status === 409 || r?.status === 410 ? 'done' : 'review')
    if (r?.status === 409 || r?.status === 410) setDoneMessage(body.detail ?? 'This form can no longer be submitted.')
  }, [form, values])

  if (loadError) {
    return (
      <Shell>
        <Card className="p-5 flex items-center gap-2 text-destructive">
          <AlertCircle className="size-4" /> {loadError}
        </Card>
      </Shell>
    )
  }

  if (!form) {
    return (
      <Shell>
        <Card className="p-5 flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading form…
        </Card>
      </Shell>
    )
  }

  const prefilled = form.mode === 'view' ? [] : form.prefilled_fields.filter((field) => field in properties)
  const outputs = form.mode === 'view' ? {} : form.result?.outputs ?? {}
  const delivery = form.mode === 'view' ? null : isRecord(form.result?.delivery) ? form.result?.delivery : null
  const workflowSteps = Array.isArray((outputs as Record<string, unknown>).workflow_steps)
    ? (((outputs as Record<string, unknown>).workflow_steps as unknown[]).filter(isRecord) as WorkflowStep[])
    : []
  const generatedLeads = Array.isArray((outputs as Record<string, unknown>).generated_leads)
    ? (((outputs as Record<string, unknown>).generated_leads as unknown[]).filter(isRecord) as GeneratedLead[])
    : []
  const recommendedSequence = Array.isArray((outputs as Record<string, unknown>).recommended_sequence)
    ? ((outputs as Record<string, unknown>).recommended_sequence as unknown[])
    : []
  const otherOutputs =
    form.mode === 'view'
      ? []
      : Object.entries(outputs).filter(([key]) => !['workflow_steps', 'generated_leads', 'recommended_sequence'].includes(key))

  return (
    <Shell>
      <Card className="overflow-hidden">
        <header className="flex items-start gap-3 border-b px-5 py-4">
          <div className="rounded-lg bg-muted p-2">
            <ClipboardList className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="font-semibold leading-tight">{form.title}</h1>
            {form.description && <p className="text-sm text-muted-foreground">{form.description}</p>}
          </div>
          <StageBadge stage={stage} expired={form.status === 'expired'} />
        </header>

        <div className="px-5 py-4">
          {banner && (
            <div className="mb-4 flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="size-4 shrink-0" /> {banner}
            </div>
          )}

          {form.status === 'expired' ? (
            <p className="text-sm text-muted-foreground">This form has expired. Ask Biz GPT to open a new one.</p>
          ) : form.mode === 'view' ? (
            <div className="space-y-4">
              <div className="rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
                This dynamic JSON output is rendered as a read-only schema view.
              </div>
              <Form
                schema={form.schema}
                uiSchema={uiSchema}
                formData={values}
                validator={validator}
                showErrorList={false}
                readonly
                disabled
              />
            </div>
          ) : stage === 'done' ? (
            <div className="space-y-4">
              <div className="flex items-start gap-3 rounded-lg border border-emerald-600/20 bg-emerald-600/5 p-4">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" />
                <div className="space-y-1">
                  <p className="text-sm font-medium">
                    {form.status === 'executed' ? 'This request has already been completed.' : 'This form has already been submitted.'}
                  </p>
                  <p className="text-sm text-muted-foreground">{doneMessage}</p>
                  <div className="flex flex-wrap gap-2">
                    {form.result?.reference && <Badge>{form.result.reference}</Badge>}
                    {form.result?.workflow_run_id && <Badge>{form.result.workflow_run_id}</Badge>}
                    {typeof form.result?.elapsed_time === 'number' && <Badge>{form.result.elapsed_time.toFixed(1)}s</Badge>}
                  </div>
                </div>
              </div>

              <div>
                <p className="mb-2 text-sm font-medium">Submitted details</p>
                <dl className="divide-y rounded-lg border text-sm">
                  {order.map((key) => (
                    <div key={key} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
                      <dt className="text-muted-foreground">{properties[key]?.title ?? key}</dt>
                      <dd className="break-words font-medium">{displayValue(values[key])}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              {workflowSteps.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Workflow steps</p>
                  <div className="space-y-2 rounded-lg border p-3 text-sm">
                    {workflowSteps.map((step, index) => (
                      <div key={`${step.title ?? 'step'}-${index}`} className="rounded-md border bg-muted/30 px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium">{step.title ?? `Step ${index + 1}`}</p>
                          <Badge className="text-muted-foreground">{step.status ?? 'completed'}</Badge>
                        </div>
                        {step.details && <p className="mt-1 text-muted-foreground">{step.details}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {generatedLeads.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Generated leads</p>
                  <div className="space-y-3">
                    {generatedLeads.map((lead, index) => (
                      <div key={`${lead.email ?? lead.name ?? 'lead'}-${index}`} className="rounded-lg border p-3 text-sm">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium">{lead.name ?? 'Unnamed lead'}</p>
                            <p className="text-muted-foreground">
                              {[lead.title, lead.company].filter(Boolean).join(' · ') || 'Lead profile'}
                            </p>
                          </div>
                          {lead.score !== undefined && <Badge>{lead.score}/100</Badge>}
                        </div>
                        <div className="mt-3 grid gap-2 md:grid-cols-2">
                          <div>
                            <p className="text-xs text-muted-foreground">Email</p>
                            <p className="break-words font-medium">{displayValue(lead.email)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">LinkedIn</p>
                            <p className="break-words font-medium">{displayValue(lead.linkedin)}</p>
                          </div>
                        </div>
                        {lead.reason && (
                          <div className="mt-3 rounded-md bg-muted/40 px-3 py-2 text-muted-foreground">
                            {lead.reason}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {recommendedSequence.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Recommended sequence</p>
                  <ol className="space-y-2 rounded-lg border p-3 text-sm">
                    {recommendedSequence.map((item, index) => (
                      <li key={`${String(item)}-${index}`} className="rounded-md bg-muted/30 px-3 py-2">
                        <span className="font-medium">{index + 1}.</span> {displayValue(item)}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {delivery && (
                <div>
                  <p className="mb-2 text-sm font-medium">Automation handoff</p>
                  <div className="rounded-lg border p-3 text-sm space-y-2">
                    <div className="grid gap-2 md:grid-cols-2">
                      <div>
                        <p className="text-xs text-muted-foreground">Status</p>
                        <p className="font-medium">{displayValue(delivery.status)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Execution ID</p>
                        <p className="font-medium">{displayValue(delivery.execution_id)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Saved leads</p>
                        <p className="font-medium">{displayValue(delivery.saved_leads)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Message</p>
                        <p className="font-medium">{displayValue(delivery.message)}</p>
                      </div>
                    </div>
                    {typeof delivery.execution_url === 'string' && (
                      <p className="text-sm">
                        <a className="font-medium text-primary underline" href={delivery.execution_url} target="_blank" rel="noreferrer">
                          Open automation execution
                        </a>
                      </p>
                    )}
                  </div>
                </div>
              )}

              {otherOutputs.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Workflow output</p>
                  <dl className="divide-y rounded-lg border text-sm">
                    {otherOutputs.map(([key, value]) => (
                      <div key={key} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
                        <dt className="text-muted-foreground">{titleize(key)}</dt>
                        <dd className="break-words font-medium whitespace-pre-wrap">
                          {isRecord(value) ? JSON.stringify(value, null, 2) : displayValue(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              <p className="text-xs text-muted-foreground">Ask Biz GPT to open a new form if you need to make another request.</p>
            </div>
          ) : stage === 'edit' ? (
            <>
              {prefilled.length > 0 && (
                <p className="mb-4 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <Sparkles className="size-3.5" /> Prefilled from your message:
                  {prefilled.map((field) => (
                    <Badge key={field}>{properties[field]?.title ?? field}</Badge>
                  ))}
                </p>
              )}
              <Form
                schema={form.schema}
                uiSchema={uiSchema}
                formData={values}
                validator={validator}
                extraErrors={extraErrors}
                showErrorList={false}
                noHtml5Validate
                onChange={(e) => setValues(e.formData as Values)}
                onSubmit={(e) => {
                  setValues(e.formData as Values)
                  setExtraErrors(undefined)
                  setBanner('')
                  setStage('review')
                }}
              />
            </>
          ) : (
            <>
              <p className="mb-3 text-sm text-muted-foreground">Please confirm these details.</p>
              <dl className="divide-y rounded-lg border text-sm">
                {order.map((key) => (
                  <div key={key} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 px-3 py-2">
                    <dt className="text-muted-foreground">{properties[key]?.title ?? key}</dt>
                    <dd className="break-words font-medium">{displayValue(values[key])}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" onClick={() => setStage('edit')} disabled={stage === 'submitting'}>
                  <Pencil className="size-4" /> Edit
                </Button>
                <Button onClick={submit} disabled={stage === 'submitting'}>
                  {stage === 'submitting' ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                  Confirm & submit
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto w-full max-w-2xl p-1">{children}</main>
}

function StageBadge({ stage, expired }: { stage: Stage; expired: boolean }) {
  if (expired) return <Badge className="text-muted-foreground">Expired</Badge>
  const labels: Record<Stage, string> = { edit: 'Step 1 · Details', review: 'Step 2 · Confirm', submitting: 'Submitting…', done: 'Done' }
  return <Badge className={stage === 'done' ? 'border-emerald-600/40 text-emerald-600' : 'text-muted-foreground'}>{labels[stage]}</Badge>
}
