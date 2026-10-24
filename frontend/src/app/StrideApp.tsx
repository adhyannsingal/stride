import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  InputField,
  SwitchField,
  Home,
  Search,
  Settings as SettingsIcon,
  Video,
  X,
  useTheme,
} from '@figma/astraui'
import {
  ApiError,
  ConnectionState,
  DeviceStatus,
  MemoryResponse,
  NavigationProgress,
  ObstacleState,
  SavedRoute,
  VisionLatest,
  newActionId,
  strideApi,
  explainError,
} from './api'
import { BrowserCameraController, SpeechController, PollController } from './controllers'
import { freshVision, newerVision, obstacleState, routeSpeech, visionSpeech, visionActionAllowed, PendingAction } from './policy'
import { AccessibleSelect as SelectField } from './AccessibleSelect'
import './app.css'

type RouteAction = 'start' | 'confirm' | 'repeat' | 'pause' | 'resume' | 'stop'
type VisionAction = 'start' | 'pause' | 'resume' | 'stop'
type Tab = 'guidance' | 'devices' | 'memory' | 'settings'
type CameraRole = 'viewer' | 'browser' | 'glasses'

const obstacleCopy: Record<ObstacleState, string> = {
  clear: 'Outside the current warning range.',
  caution: 'Nearby obstacle warning.',
  danger: 'Stop. Obstacle warning.',
  unknown: 'Obstacle sensing unavailable.',
}

const previewRoute: SavedRoute = {
  route_id: 'preview-library-route',
  name: 'Station entrance → Library desk',
  description: 'A manually checked demonstration route.',
  checked: true,
  demo_fixture: true,
  verification_note: 'Preview fixture',
  checkpoints: [
    { checkpoint_id: 'ticket-gates', ordinal: 0, instruction: 'Continue straight toward the library entrance.', direction: 'straight', landmark: 'Station ticket gates' },
    { checkpoint_id: 'library-doors', ordinal: 1, instruction: 'The library entrance is ahead.', direction: 'straight', landmark: 'Library entrance doors' },
  ],
}

const previewMemory: MemoryResponse = {
  routes: [previewRoute],
  navigation: null,
  previous_navigation: [],
  sightings: [
    {
      sighting_id: 'preview-bench',
      label: 'Bench',
      checkpoint_id: 'ticket-gates',
      checkpoint_association: 'last_user_confirmed',
      source: 'fixture',
      provider: 'fixture',
      age_ms: 240000,
      last_seen_at: Date.now() - 240000,
    },
  ],
  returned_at: Date.now(),
}

function StatusMessage({ tone = 'info', children }: { tone?: 'info' | 'warning' | 'danger'; children: React.ReactNode }) {
  return <div className={`sa-message sa-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>{children}</div>
}

function ConnectionPanel({
  state,
  error,
  onConnect,
}: {
  state: ConnectionState
  error: string
  onConnect: (sessionId: string, token: string) => void
}) {
  const [sessionId, setSessionId] = useState('')
  const [token, setToken] = useState('')
  return (
    <section className="sa-connect" aria-labelledby="connect-title">
      <div className="sa-kicker">SECURE CONNECTION</div>
      <div id="connect-title" role="heading" aria-level={1} className="sa-title">Connect to STRIDE</div>
      <p>Use the operator-provided UI session credentials. The token is exchanged for an HttpOnly session cookie and is not stored.</p>
      {state === 'unauthorized' && <StatusMessage tone="danger">Unauthorized. Check the session ID and token.</StatusMessage>}
      {state === 'error' && <StatusMessage tone="warning">{error || 'Backend connection unavailable.'}</StatusMessage>}
      <div className="sa-form">
        <InputField placeholder="" aria-label="Session ID" label="Session ID" value={sessionId} onChange={setSessionId} autoComplete="username" />
        <InputField placeholder="" aria-label="Session token" label="Session token" type="password" value={token} onChange={setToken} autoComplete="current-password" />
        <Button variant="primary" disabled={!sessionId || !token || state === 'connecting'} onClick={() => { onConnect(sessionId, token); setToken('') }}>
          {state === 'connecting' ? 'Connecting…' : state === 'disconnected' ? 'Connect' : 'Reconnect'}
        </Button>
      </div>
    </section>
  )
}

function ObstacleBanner({ state }: { state: ObstacleState }) {
  const tone = state === 'danger' ? 'danger' : state === 'clear' ? 'info' : 'warning'
  return (
    <StatusMessage tone={tone}>
      <strong>{obstacleCopy[state]}</strong>
    </StatusMessage>
  )
}

export default function StrideApp({ exit }: { exit: () => void }) {
  const [previewMode, setPreviewMode] = useState(true)
  const [tab, setTab] = useState<Tab>('guidance')
  const [connection, setConnection] = useState<ConnectionState>(previewMode ? 'connected' : 'disconnected')
  const [sessionId, setSessionId] = useState(previewMode ? 'demo-preview' : '')
  const [error, setError] = useState('')
  const [routes, setRoutes] = useState<SavedRoute[]>(previewMode ? [previewRoute] : [])
  const [routesState, setRoutesState] = useState<'idle' | 'loading' | 'ready' | 'error'>(previewMode ? 'ready' : 'idle')
  const [selectedRoute, setSelectedRoute] = useState(previewMode ? previewRoute.route_id : '')
  const [navigation, setNavigation] = useState<NavigationProgress | null>(null)
  const [routePending, setRoutePending] = useState(false)
  const [deviceId, setDeviceId] = useState('')
  const [device, setDevice] = useState<DeviceStatus | null>(null)
  const [deviceError, setDeviceError] = useState('')
  const [pairing, setPairing] = useState(false)
  const [vision, setVision] = useState<VisionLatest | null>({state:'idle',status:'unavailable',generation:0,state_seq:0,source_revision:0,detector_configured:false,source:'fixture',origin:'demo_preview',device_id:null,frame_id:null,age_ms:null,objects:[],speech_event:null,last_inference_error:null})
  const [visionFetchedAt, setVisionFetchedAt] = useState(0)
  const [visionError, setVisionError] = useState('')
  const [cameraRole, setCameraRole] = useState<CameraRole>('viewer')
  const [cameraConsent, setCameraConsent] = useState(false)
  const [memory, setMemory] = useState<MemoryResponse | null>(previewMode ? previewMemory : null)
  const [memoryState, setMemoryState] = useState<'idle' | 'loading' | 'ready' | 'error'>(previewMode ? 'ready' : 'idle')
  const [query, setQuery] = useState('')
  const speech = useRef(new SpeechController())
  const camera = useRef(new BrowserCameraController())
  const videoRef = useRef<HTMLVideoElement>(null)
  const [speechStatus, setSpeechStatus] = useState('Browser speech off')
  const [speechRate, setSpeechRate] = useState('1')
  const [observationSpeech, setObservationSpeech] = useState(true)
  const [connectSessionId, setConnectSessionId] = useState('')
  const [connectToken, setConnectToken] = useState('')
  const { theme, setTheme } = useTheme()

  const visionPoll = useRef(new PollController())
  const memoryPoll = useRef(new PollController())
  const runtime = useRef({epoch: 0, abort: new AbortController(), routeBusy: false, visionBusy: false, stopRequested: false})
  const routeAttempt = useRef(new PendingAction<{action: RouteAction; route: string; navigation: NavigationProgress | undefined}>())
  const visionAttempt = useRef(new PendingAction<{action: VisionAction; generation: number | undefined}>())
  const navRef = useRef(navigation)
  const visionRef = useRef(vision)
  const [visible, setVisible] = useState(!document.hidden)
  const [now, setNow] = useState(performance.now())
  const [deviceFetchedAt, setDeviceFetchedAt] = useState(0)
  const [backendFreshAt, setBackendFreshAt] = useState(0)
  const [visionPending, setVisionPending] = useState(false)
  const visionIntent = useRef(0)
  const queuedVisionControl = useRef<VisionAction | null>(null)
  const [visionSuppressed, setVisionSuppressed] = useState(false)
  const [localHold, setLocalHold] = useState(false)
  const [cameraRunning, setCameraRunning] = useState(false)
  const [singleProducer, setSingleProducer] = useState(false)
  const [textSize, setTextSize] = useState('standard')
  const [memoryFetchedAt, setMemoryFetchedAt] = useState(performance.now())
  const serverClock = useRef<{upper: number; at: number} | null>(null)
  const live = useRef({sessionId, cameraRole, cameraConsent, singleProducer, visible, blocked: false, visionSuppressed, localHold, previewMode})
  live.current = {sessionId, cameraRole, cameraConsent, singleProducer, visible, blocked: false, visionSuppressed, localHold, previewMode}
  const deviceFresh = previewMode || (!!device && now - deviceFetchedAt + (device.telemetry_age_ms ?? Infinity) < (device.measurement_timeout_ms ?? 1000))
  const backendFresh = previewMode || (backendFreshAt > 0 && now - backendFreshAt < 2000)
  const obstacle = obstacleState(navigation, device, deviceFresh, !!deviceId || !!navigation?.paired_device_id)
  const blocked = navigation?.state === 'blocked' || (!!obstacle && obstacle !== 'clear') || !backendFresh
  live.current.blocked = blocked
  const liveVision = visible && !visionSuppressed && !visionError && !blocked && freshVision(vision, visionFetchedAt, now)
  const effectiveVisionAge = vision?.age_ms == null ? null : Math.round(vision.age_ms + Math.max(0, now - visionFetchedAt))

  const applyNavigation = (next: NavigationProgress | null) => {
    if (next && navRef.current && next.state_revision < navRef.current.state_revision) return
    if (next?.guidance_event && navRef.current?.guidance_event && next.state_revision === navRef.current.state_revision && next.guidance_event.created_at < navRef.current.guidance_event.created_at) return
    navRef.current = next; setNavigation(next)
  }
  const applyVision = (next: VisionLatest, started = performance.now()) => {
    if (!newerVision(visionRef.current, next)) return
    visionRef.current = next; setVision(next); setVisionFetchedAt(started)
  }
  const stopLocal = () => { live.current.localHold = true; live.current.visionSuppressed = true; camera.current.stop(); speech.current.cancel(); setCameraRunning(false) }
  const resetSession = () => {
    memoryPoll.current.stop(); visionPoll.current.stop(); live.current.sessionId = '';
    runtime.current.epoch++; runtime.current.abort.abort(); runtime.current.abort = new AbortController()
    runtime.current.routeBusy = false; runtime.current.visionBusy = false; runtime.current.stopRequested = false
    stopLocal(); speech.current.reset(); routeAttempt.current.clear(); visionAttempt.current.clear(); queuedVisionControl.current = null
    navRef.current = null; visionRef.current = null; serverClock.current = null
    setNavigation(null); setVision(null); setMemory(null); setDevice(null); setDeviceId(''); setRoutes([]); setSelectedRoute('')
    setCameraConsent(false); setSingleProducer(false); setCameraRole('viewer'); setQuery(''); setVisionError(''); setDeviceError('')
    setPairing(false); setVisionPending(false); setRoutePending(false); setVisionSuppressed(false); setLocalHold(false); setBackendFreshAt(0)
  }
  const handleError = (cause: unknown) => {
    if (cause instanceof ApiError && [401,403].includes(cause.status)) {
      stopLocal(); setConnection('unauthorized'); setVisionSuppressed(true); setLocalHold(true)
    }
    setError(explainError(cause))
  }
  const connect = async (id: string, token: string) => {
    resetSession(); setPreviewMode(false); setSessionId(''); setConnectToken(''); setConnection('connecting'); setError(''); setRoutesState('loading')
    const {epoch, abort} = runtime.current
    try {
      await strideApi.connect(id, token, abort.signal)
      const started = performance.now()
      const [result, recalled, latest, time] = await Promise.all([
        strideApi.routes(id, abort.signal), strideApi.memory(id, abort.signal), strideApi.visionLatest(id, abort.signal), strideApi.time(abort.signal),
      ])
      if (epoch !== runtime.current.epoch) return
      serverClock.current = {upper: time.server_ms + performance.now() - started, at: performance.now()}
      setSessionId(id); setConnection('connected'); setRoutes(result.routes); applyNavigation(recalled.navigation)
      setMemory(recalled); setMemoryFetchedAt(performance.now()); setMemoryState('ready'); applyVision(latest, started)
      setDeviceId(recalled.navigation?.paired_device_id || '')
      setSelectedRoute(result.routes.find(r => r.checked)?.route_id || ''); setRoutesState('ready'); setBackendFreshAt(performance.now())
    } catch (cause) {
      if (epoch !== runtime.current.epoch) return
      setConnection(cause instanceof ApiError && [401,403].includes(cause.status) ? 'unauthorized' : 'error')
      setError(explainError(cause)); setRoutesState('error')
    }
  }
  const useDemoData = () => {
    resetSession(); setPreviewMode(true); setConnection('connected'); setSessionId('demo-preview')
    setRoutes([previewRoute]); setRoutesState('ready'); setSelectedRoute(previewRoute.route_id)
    setMemory(previewMemory); setMemoryFetchedAt(performance.now()); setMemoryState('ready'); setError('')
  }
  const refreshAuthoritativeNavigation = async () => {
    const epoch = runtime.current.epoch
    const result = await strideApi.memory(sessionId, runtime.current.abort.signal)
    if (epoch === runtime.current.epoch) applyNavigation(result.navigation)
    return result.navigation
  }
  const routeAction = async (action: RouteAction) => {
    if (action === 'stop' || action === 'pause') { speech.current.cancel(); setLocalHold(true) }
    if (action === 'stop') stopLocal()
    if (runtime.current.routeBusy) {
      if (action === 'stop') { runtime.current.stopRequested = true; setError('Local activity stopped. Waiting to confirm server Stop.') }
      return
    }
    if (!sessionId || connection !== 'connected') return
    if (previewMode) {
      if (action === 'start') {
        const cp = previewRoute.checkpoints[0]
        applyNavigation({navigation_id:'preview-navigation', route_id:previewRoute.route_id, state:'guiding', state_revision:1,
          current_checkpoint:cp, confirmed_checkpoint_count:0,total_checkpoints:2,confirmed_checkpoints:[],instruction:cp.instruction,
          guidance_event:null,status_message:'Simulated route progress',sensor_monitoring:'not_associated',paired_device_id:null,obstacle_state:null})
        setLocalHold(false); return
      }
      const n = navRef.current
      if (!n) return
      const count = n.confirmed_checkpoint_count + (action === 'confirm' && n.state === 'guiding' ? 1 : 0)
      const cp = previewRoute.checkpoints[count] || null
      applyNavigation({...n, state:action === 'stop' ? 'idle' : count === 2 ? 'completed' : action === 'pause' ? 'paused' : action === 'resume' ? 'guiding' : n.state,
        state_revision:n.state_revision + (action === 'repeat' ? 0 : 1), confirmed_checkpoint_count:count,
        confirmed_checkpoints:previewRoute.checkpoints.slice(0,count),current_checkpoint:cp,instruction:cp?.instruction || null})
      if (action === 'resume') setLocalHold(false)
      return
    }
    if (action === 'start' && !routes.find(r => r.route_id === selectedRoute)?.checked) return
    const pending = routeAttempt.current.value
    if (pending && pending.payload.action !== action) {
      if (action !== 'stop') { setError('Previous action outcome is uncertain. Retry that same action first.'); return }
      // Stop is a new user action, after authoritative recovery; never a retry of confirm.
      try { await refreshAuthoritativeNavigation() } catch (cause) { handleError(cause); return }
      routeAttempt.current.clear()
    }
    const attempt = routeAttempt.current.begin({action, route:selectedRoute, navigation:navRef.current || undefined})
    runtime.current.routeBusy = true; setRoutePending(true); setError('')
    const epoch = runtime.current.epoch
    try {
      const p = attempt.payload
      const result = await strideApi.routeAction(sessionId, attempt.id, p.action, p.route, p.navigation, runtime.current.abort.signal)
      if (epoch !== runtime.current.epoch) return
      routeAttempt.current.clear(); applyNavigation(result)
      if (!runtime.current.stopRequested && !['pause','stop'].includes(action)) setLocalHold(false)
    } catch (cause) {
      if (epoch !== runtime.current.epoch) return
      if (cause instanceof ApiError && cause.status < 500) routeAttempt.current.clear()
      if (cause instanceof ApiError && cause.status === 409) {
        try { await refreshAuthoritativeNavigation(); setError('Guidance changed on the server. Review the refreshed state before trying again.') }
        catch (refreshError) { handleError(refreshError) }
      } else { handleError(cause); if (action === 'stop') setError('Local activity stopped; server Stop is unconfirmed. Retry Stop with the same action ID.') }
    } finally {
      if (epoch === runtime.current.epoch) {
        runtime.current.routeBusy = false; setRoutePending(false)
        if (runtime.current.stopRequested) { runtime.current.stopRequested = false; void routeAction('stop') }
      }
    }
  }
  const refreshDevice = async () => {
    const epoch = runtime.current.epoch
    try {
      const started = performance.now()
      const result = await strideApi.deviceStatus(deviceId, sessionId, runtime.current.abort.signal)
      if (epoch !== runtime.current.epoch) return
      setDevice(result); setDeviceFetchedAt(started); setDeviceError(''); await refreshAuthoritativeNavigation()
    } catch (cause) { if (epoch === runtime.current.epoch) { setDevice(null); setDeviceError(explainError(cause)) } }
  }

  useEffect(() => {
    const update = () => {
      setVisible(!document.hidden)
      if (document.hidden) { stopLocal(); setVisionSuppressed(true); setLocalHold(true) }
    }
    document.addEventListener('visibilitychange', update)
    const tick = window.setInterval(() => setNow(performance.now()), 100)
    return () => { document.removeEventListener('visibilitychange', update); clearInterval(tick) }
  }, [])
  useEffect(() => () => { runtime.current.epoch++; runtime.current.abort.abort(); camera.current.stop(); speech.current.cancel() }, [])

  useEffect(() => {
    if (previewMode || connection !== 'connected' || !visible) return
    const poll = memoryPoll.current
    const epoch = runtime.current.epoch
    poll.start(async signal => {
      const mem = await strideApi.memory(sessionId, signal)
      const id = deviceId || mem.navigation?.paired_device_id
      let status: DeviceStatus | null = null
      let deviceFailure = ''
      if (id) {
        try { status = await strideApi.deviceStatus(id, sessionId, signal) }
        catch (cause) { if (cause instanceof ApiError && cause.status === 401) throw cause; deviceFailure = explainError(cause) }
      }
      return {mem,status,deviceFailure}
    }, ({mem,status,deviceFailure}, started) => {
      if (epoch !== runtime.current.epoch) return
      applyNavigation(mem.navigation); setMemory(mem); setMemoryFetchedAt(started); setMemoryState('ready')
      setDevice(status); setDeviceFetchedAt(started); setDeviceError(deviceFailure); setBackendFreshAt(performance.now())
    }, cause => { if (epoch === runtime.current.epoch) { setBackendFreshAt(0); setDevice(null); speech.current.cancel(); handleError(cause) } }, 500)
    return () => poll.stop()
  }, [previewMode, connection, sessionId, deviceId, visible])

  useEffect(() => {
    if (previewMode || connection !== 'connected' || !visible || vision?.state === 'stopped') return
    const poll = visionPoll.current
    const epoch = runtime.current.epoch
    poll.start(signal => strideApi.visionLatest(sessionId, signal), (next, started) => {
      if (epoch !== runtime.current.epoch) return
      const previous = visionRef.current
      applyVision(next, started)
      if (cameraRunning && previous && (next.source_revision !== previous.source_revision || next.generation !== previous.generation)) {
        camera.current.stop(); setCameraRunning(false); setVisionSuppressed(true); setVisionError('Vision generation or source changed. Capture stopped; explicitly review and restart.')
      }
      if (next.state !== 'active') { camera.current.stop(); setCameraRunning(false) }
      if (cameraRunning && next.device_id && next.device_id !== camera.current.deviceId) {
        camera.current.stop(); setCameraRunning(false); setVisionSuppressed(true)
        setVisionError('Another camera producer appeared. Capture stopped; use a separate development session.')
      }
    }, cause => {
      if (epoch !== runtime.current.epoch) return
      setVisionError(explainError(cause)); speech.current.reconcile()
      if (cause instanceof ApiError && [401,403].includes(cause.status)) handleError(cause)
    })
    return () => poll.stop()
  }, [previewMode, connection, sessionId, visible, vision?.state === 'stopped', cameraRunning])

  const controlVision = async (action: VisionAction) => {
    const intent = ++visionIntent.current
    if (action === 'stop' || action === 'pause') { stopLocal(); setVisionSuppressed(true) }
    if (runtime.current.visionBusy) {
      if (action === 'stop' || (action === 'pause' && queuedVisionControl.current !== 'stop')) queuedVisionControl.current = action
      setVisionError('Local capture/audio stopped. Server control is pending.')
      return
    }
    const current = visionRef.current
    if (previewMode) {
      if (current && !visionActionAllowed(current.state, action)) return
      applyVision({state: action === 'start' || action === 'resume' ? 'active' : action === 'pause' ? 'paused' : 'stopped',
        status: action === 'start' || action === 'resume' ? 'live' : action === 'pause' ? 'paused' : 'unavailable',
        generation:current?.generation || 0,state_seq:(current?.state_seq || 0)+1,source_revision:0,age_ms:80,
        source:'fixture',origin:'demo_preview',objects:[],speech_event:null,detector_configured:false,device_id:null,frame_id:null,last_inference_error:null})
      setVisionSuppressed(action === 'pause' || action === 'stop'); return
    }
    if (!visionAttempt.current.value && ['start','resume'].includes(action) && cameraRole === 'browser' && (!cameraConsent || !singleProducer)) {
      setVisionError('Consent and single-producer development confirmation are required.'); return
    }
    runtime.current.visionBusy = true; setVisionPending(true); setVisionError('')
    const epoch = runtime.current.epoch
    const signal = runtime.current.abort.signal
    try {
      // Resolve the original ID/payload BEFORE validating a new action against a
      // polled state. A successful request whose response was lost is a duplicate,
      // even if polling already shows its resulting state.
      const pending = visionAttempt.current.value
      if (pending) {
        await strideApi.visionAction(sessionId, pending.id, pending.payload.action, pending.payload.generation, signal)
        if (epoch !== runtime.current.epoch) return
        visionAttempt.current.clear()
      }
      const started = performance.now()
      let latest = await strideApi.visionLatest(sessionId, signal)
      if (epoch !== runtime.current.epoch) return
      applyVision(latest, started)
      if (pending?.payload.action !== action && visionActionAllowed(latest.state, action)) {
        const attempt = visionAttempt.current.begin({action,generation:latest.generation})
        await strideApi.visionAction(sessionId, attempt.id, action, attempt.payload.generation, signal)
        if (epoch !== runtime.current.epoch) return
        visionAttempt.current.clear()
        const fetched = performance.now()
        latest = await strideApi.visionLatest(sessionId, signal)
        if (epoch !== runtime.current.epoch) return
        applyVision(latest, fetched)
      } else if (!pending && !visionActionAllowed(latest.state, action)) {
        const reached = action === 'stop' ? 'stopped' : action === 'pause' ? 'paused' : 'active'
        if (latest.state !== reached) throw new Error('Action unavailable. Stopped sessions require a new authorized session.')
      }
      if (intent === visionIntent.current) setVisionSuppressed(latest.state !== 'active')
    } catch (cause) {
      if (epoch !== runtime.current.epoch) return
      if (cause instanceof ApiError && cause.status < 500) visionAttempt.current.clear()
      stopLocal(); setVisionSuppressed(true)
      setVisionError(action === 'stop' ? 'Local capture/audio stopped; server Stop is unconfirmed. Retry Stop.' : explainError(cause))
      if (cause instanceof ApiError && cause.status === 409) {
        try { const v = await strideApi.visionLatest(sessionId, signal); if (epoch === runtime.current.epoch) applyVision(v) } catch { /* retain conflict */ }
      }
    } finally {
      if (epoch === runtime.current.epoch) {
        runtime.current.visionBusy = false; setVisionPending(false)
        const queued = queuedVisionControl.current
        queuedVisionControl.current = null
        if (queued) void controlVision(queued)
      }
    }
  }
  const startBrowserCamera = async () => {
    const epoch = runtime.current.epoch
    const v = visionRef.current
    if (previewMode || !videoRef.current || v?.state !== 'active') return
    if (v.device_id && v.device_id !== camera.current.deviceId) { setVisionError('This session already has another producer. Use a newly provisioned single-producer session.'); return }
    setVisionError(''); setVisionSuppressed(false)
    try {
      await camera.current.start(videoRef.current, {sessionId,role:cameraRole,consent:cameraConsent,userGesture:true,
        sourceRevision:v.source_revision,singleProducer,allowed:() => epoch === runtime.current.epoch && live.current.cameraRole === 'browser' && live.current.cameraConsent && live.current.singleProducer && live.current.visible},
        message => { if (epoch === runtime.current.epoch) { setVisionError(message); setCameraRunning(false); setVisionSuppressed(true) } })
      if (epoch === runtime.current.epoch) setCameraRunning(true)
    } catch (cause) { if (epoch === runtime.current.epoch) { setCameraRunning(false); setVisionError(explainError(cause)) } }
  }

  useEffect(() => {
    speech.current.reconcile()
    if (previewMode || !visible) return
    if (blocked) {
      const state = !backendFresh ? 'backend' : obstacle || 'blocked'
      const text = state === 'backend' ? 'Backend connection unavailable. Guidance is on hold.' : state === 'danger' ? obstacleCopy.danger : state === 'caution' ? 'Nearby obstacle warning. Guidance is blocked.' : 'Obstacle sensing unavailable or guidance blocked. Check before continuing.'
      speech.current.enqueue({id:`${sessionId}:hold:${state}:${holdEpisode.current}`,text,kind:state === 'danger' ? 'urgent' : 'fault',expiresAt:performance.now()+3000,
        valid:() => live.current.sessionId === sessionId && live.current.blocked && live.current.visible})
      return
    }
    if (localHold) return
    const n = navigation
    const clock = serverClock.current
    if (n?.guidance_event && clock) {
      const upperNow = clock.upper + performance.now() - clock.at
      const e = routeSpeech(sessionId,n,performance.now()+n.guidance_event.expires_at-upperNow,() =>
        live.current.sessionId === sessionId && !live.current.blocked && !live.current.localHold && live.current.visible && navRef.current?.state === 'guiding' && navRef.current.navigation_id === n.navigation_id && navRef.current.state_revision === n.state_revision && navRef.current.guidance_event?.event_id === n.guidance_event?.event_id && !!navRef.current.guidance_event?.valid)
      if (e) speech.current.enqueue(e)
    }
    if (vision && liveVision) {
      const v = vision
      const e = visionSpeech(sessionId,v,visionFetchedAt,() => live.current.sessionId === sessionId && !live.current.blocked && !live.current.visionSuppressed && live.current.visible && visionRef.current?.generation === v.generation && visionRef.current?.source_revision === v.source_revision && visionRef.current?.state === 'active')
      if (e) speech.current.enqueue(e)
    }
  }, [navigation,vision,blocked,localHold,liveVision,obstacle,visible,previewMode,speechStatus,now])
  const holdEpisode = useRef(0)
  const priorHold = useRef(false)
  if (blocked && !priorHold.current) holdEpisode.current++
  priorHold.current = blocked

  const loadMemory = async () => {
    if (previewMode) { setMemory(previewMemory); setMemoryFetchedAt(performance.now()); setMemoryState('ready'); return }
    const epoch = runtime.current.epoch
    setMemoryState('loading')
    try { const m = await strideApi.memory(sessionId,runtime.current.abort.signal); if (epoch === runtime.current.epoch) { setMemory(m); setMemoryFetchedAt(performance.now()); setMemoryState('ready') } }
    catch (cause) { if (epoch === runtime.current.epoch) { setMemoryState('error'); handleError(cause) } }
  }

  const currentRoute = routes.find((route) => route.route_id === navigation?.route_id)
  const currentCheckpoint = navigation?.current_checkpoint
  const lastConfirmed = navigation?.confirmed_checkpoints.at(-1)
  const sightings = useMemo(() => (memory?.sightings || []).filter((item) => item.label.toLowerCase().includes(query.toLowerCase())), [memory, query])

  if (!previewMode && connection !== 'connected') {
    return <div className="stride-app"><ConnectionPanel state={connection} error={error} onConnect={connect} /><Button variant="neutral" onClick={useDemoData}>Use explicitly simulated demo</Button><Button variant="neutral" onClick={exit}>Exit</Button>{navigation && <Button className="sa-stop" onClick={() => { stopLocal(); setError('Local camera/audio stopped. Reconnect to confirm server Stop.') }}>Stop local activity</Button>}</div>
  }

  return (
    <div className="stride-app">
      <nav className="sa-nav" aria-label="STRIDE application">
        <div className="sa-tabs">
          <Button variant={tab === 'guidance' ? 'primary' : 'subtle'} iconStart={<Home />} onClick={() => setTab('guidance')}>Guidance</Button>
          <Button variant={tab === 'devices' ? 'primary' : 'subtle'} iconStart={<Video />} onClick={() => setTab('devices')}>Devices</Button>
          <Button variant={tab === 'memory' ? 'primary' : 'subtle'} iconStart={<Search />} onClick={() => setTab('memory')}>Memory</Button>
          <Button variant={tab === 'settings' ? 'primary' : 'subtle'} iconStart={<SettingsIcon />} onClick={() => setTab('settings')}>Settings</Button>
        </div>
        <div className="sa-nav-end">
          <span className="sa-mode">{previewMode ? 'Demo data' : `Backend · ${sessionId}`}</span>
          <Button variant="subtle" onClick={exit}>Exit</Button>
        </div>
      </nav>

      <main className="sa-main">
        {previewMode && <StatusMessage>Demo data · simulated progress and devices. No physical sensor or YOLO connection.</StatusMessage>}
        {obstacle && <div aria-live={speechStatus === 'Browser speech enabled' ? 'off' : 'polite'}><strong>{obstacleCopy[obstacle]}</strong></div>}
        {!previewMode && !backendFresh && <StatusMessage tone="warning">Backend disconnected or stale. Routine guidance is on hold.</StatusMessage>}
        {error && <StatusMessage tone="warning">{error}</StatusMessage>}

        {(
          <div className="sa-page" hidden={tab !== 'guidance'}>
            <header className="sa-header">
              <div><div className="sa-kicker">ASSISTED NAVIGATION</div><div role="heading" aria-level={1} className="sa-title">Guidance</div></div>
            </header>

            {navigation?.sensor_monitoring === 'not_associated' && <p>Obstacle sensor not associated. Local protection is not verified.</p>}
            {navigation?.state === 'completed' && <StatusMessage><strong>Route completed.</strong> All checked checkpoints were explicitly confirmed.</StatusMessage>}

            <div className="sa-guidance-grid">
              <section className="sa-primary-panel">
                {!navigation || navigation.state === 'idle' ? (
                  <>
                    <div className="sa-kicker">CHECKED ROUTE</div>
                    <div role="heading" aria-level={2} className="sa-instruction">Choose where guidance begins.</div>
                    {routesState === 'loading' && <p>Loading checked routes…</p>}
                    {routesState === 'error' && <StatusMessage tone="danger">Routes could not be loaded.</StatusMessage>}
                    {routesState === 'ready' && routes.length === 0 && <p>No routes are available for this session.</p>}
                    <div className="sa-route-list">
                      {routes.map((route) => (
                        <div className={`sa-route ${!route.checked ? 'sa-disabled' : ''}`} key={route.route_id}>
                          <div><strong>{route.name}</strong><p>{route.description || 'No description provided.'}</p><span>{route.checked ? 'Manually checked' : 'Not checked — guidance unavailable'}{route.demo_fixture ? ' · Demo fixture' : ''}</span></div>
                          <Button variant={selectedRoute === route.route_id ? 'primary' : 'neutral'} disabled={!route.checked} onClick={() => setSelectedRoute(route.route_id)}>{selectedRoute === route.route_id ? 'Selected' : 'Select'}</Button>
                        </div>
                      ))}
                    </div>
                    <Button variant="primary" disabled={!selectedRoute || routePending || blocked} onClick={() => routeAction('start')}>Start Guidance</Button>
                  </>
                ) : (
                  <>
                    <div className="sa-route-name">{currentRoute?.name || 'Selected route'} · {navigation.state}</div>
                    <div role="heading" aria-level={2} className="sa-instruction">{!previewMode && (blocked || localHold) ? 'Guidance on hold. Check the current status.' : navigation.instruction || navigation.status_message}</div>
                    <div className="sa-progress">
                      <div><span>Current checkpoint</span><strong>{currentCheckpoint?.landmark || currentCheckpoint?.checkpoint_id || 'None'}</strong></div>
                      <div><span>Last explicitly confirmed</span><strong>{lastConfirmed?.landmark || lastConfirmed?.checkpoint_id || 'None yet'}</strong></div>
                      <div><span>Confirmed</span><strong>{navigation.confirmed_checkpoint_count} / {navigation.total_checkpoints}</strong></div>
                    </div>
                    <div className="sa-actions">
                      <Button variant="primary" disabled={navigation.state !== 'guiding' || routePending || blocked} onClick={() => routeAction('confirm')}>Confirm Arrival</Button>
                      <Button variant="neutral" disabled={navigation.state !== 'guiding' || routePending || blocked} onClick={() => routeAction('repeat')}>Repeat</Button>
                      {navigation.state === 'paused' ? (
                        <Button variant="neutral" disabled={routePending || blocked} onClick={() => routeAction('resume')}>Resume</Button>
                      ) : (
                        <Button variant="neutral" disabled={navigation.state !== 'guiding' || routePending || blocked} onClick={() => routeAction('pause')}>Pause</Button>
                      )}
                    </div>
                    {navigation.state === 'completed' && <Button variant="neutral" disabled={routePending} onClick={() => routeAction('stop')}>Choose another route</Button>}
                  </>
                )}
              </section>

              <aside className="sa-secondary-panel">
                <div className="sa-kicker">LIVE AWARENESS</div>
                <div role="heading" aria-level={2}>What’s ahead</div>
                <div className="sa-vision-status">{liveVision ? 'live' : vision?.state === 'stopped' ? 'stopped' : vision?.state === 'paused' ? 'paused' : 'unavailable or stale'}{effectiveVisionAge !== null ? ` · ${effectiveVisionAge} ms` : ''}</div>
                {visionError && <StatusMessage tone="warning">{visionError}</StatusMessage>}
                {cameraRole === 'browser' && (
                  <div className="sa-video-wrap">
                    <video ref={videoRef} className="sa-video" muted playsInline aria-label="Browser camera preview" />
                    {liveVision && cameraRunning && vision?.device_id === camera.current.deviceId && <div className="sa-overlay">{vision!.objects.map((object, index) => <span key={object.track_id || `${object.label}-${index}`} style={{ left: `${object.bbox[0] * 100}%`, top: `${object.bbox[1] * 100}%`, width: `${(object.bbox[2] - object.bbox[0]) * 100}%`, height: `${(object.bbox[3] - object.bbox[1]) * 100}%` }}>{object.label}</span>)}</div>}
                  </div>
                )}
                {cameraRole === 'glasses' && <p>Glasses-camera preview frames are unavailable unless the backend provides video separately.</p>}
                {liveVision ? (
                  vision!.objects.length ? (
                    <div className="sa-detections">
                      <strong>{vision!.objects.map((object) => `${object.label}, ${object.position} side of camera view`).join('; ')}.</strong>
                    </div>
                  ) : <p>No supported objects detected in the latest frame.</p>
                ) : <p>Current recognition is unavailable. Expired results and boxes are hidden.</p>}
                <div className="sa-actions">
                  {(!vision && previewMode) || vision?.state === 'idle' ? <Button variant="primary" disabled={blocked || visionPending} onClick={() => controlVision('start')}>Start</Button> : null}
                  {vision?.state === 'active' && <Button variant="neutral" onClick={() => controlVision('pause')}>Pause</Button>}
                  {vision?.state === 'paused' && <Button variant="neutral" disabled={visionPending || blocked} onClick={() => controlVision('resume')}>Resume</Button>}
                  {vision && !['idle', 'stopped'].includes(vision.state) && <Button variant="neutral" onClick={() => controlVision('stop')}>Stop awareness</Button>}
                </div>
                {visionAttempt.current.value && <Button variant="neutral" disabled={visionPending} onClick={() => controlVision(visionAttempt.current.value!.payload.action)}>Retry awareness command</Button>}
                {vision?.state === 'stopped' && <p>Awareness stopped for this session. Connect to a newly provisioned session to start again.</p>}
                {cameraRole === 'browser' && !previewMode && <Button variant="neutral" disabled={vision?.state !== 'active' || !cameraConsent || !singleProducer || cameraRunning} onClick={startBrowserCamera}>Start this camera</Button>}
                {visionSuppressed && vision?.state === 'active' && cameraRole !== 'browser' && <Button variant="neutral" onClick={() => setVisionSuppressed(false)}>View current awareness</Button>}
                <p>Source: {vision?.source || 'unavailable'} · {vision?.origin || 'unavailable'}</p>
                {!previewMode && <p>Object speech awaits backend-authorized events and capture freshness. Detection metadata alone does not produce speech.</p>}
              </aside>
            </div>
          </div>
        )}

        {tab === 'devices' && (
          <div className="sa-page">
            <header className="sa-header"><div><div className="sa-kicker">TECHNICAL SETUP</div><div role="heading" aria-level={1} className="sa-title">Devices</div></div></header>
            <div className="sa-two-column">
              <section className="sa-panel">
                <div role="heading" aria-level={2}>Obstacle controller</div>
                <p>Enter the controller ID supplied by the operator. Browser device discovery and firmware credentials are not used.</p>
                <InputField placeholder="" aria-label="Controller ID" label="Controller ID" disabled={pairing} value={deviceId} onChange={(id) => { setDeviceId(id); setDevice(null); setDeviceError('') }} />
                <Button variant="primary" disabled={!deviceId || pairing} onClick={async () => {
                  setPairing(true)
                  const pairEpoch = runtime.current.epoch
                  try {
                    if (previewMode) {
                      setDevice({
                        device_id: deviceId,
                        session_id: sessionId,
                        paired: true,
                        availability: 'connected',
                        telemetry_age_ms: 120,
                        telemetry_fresh: true,
                        measurement_fresh: true,
                        sensor_valid: true,
                        measurement_reason: null,
                        current_distance_cm: 142,
                        last_reported_distance_cm: 142,
                        last_valid_distance_cm: 142,
                        last_valid_distance_age_ms: 120,
                        obstacle_state: 'clear',
                        source: 'fixture',
                        battery_percent: null,
                        firmware_version: null,
                        recovery_clear_count: 3,
                        recovery_required: 3,
                        navigation_state: navigation?.state || null,
                        navigation_revision: navigation?.state_revision || null,
                        pending_commands: 0,
                        latest_command: null,
                        last_acknowledged_command_id: null,
                        local_alerts_verified: false,
                      })
                    } else {
                      await strideApi.pairDevice(deviceId, sessionId, runtime.current.abort.signal)
                      if (pairEpoch === runtime.current.epoch) await refreshDevice()
                    }
                  } catch (cause) { if (pairEpoch === runtime.current.epoch) setDeviceError(explainError(cause)) } finally { if (pairEpoch === runtime.current.epoch) setPairing(false) }
                }}>{pairing ? 'Pairing…' : 'Pair controller'}</Button>
                {deviceError && <StatusMessage tone="warning">{deviceError}</StatusMessage>}
                {!device && !deviceError && <p>Not associated.</p>}
                {device && (
                  <>
                    <p><strong>{obstacleCopy[deviceFresh ? device.obstacle_state : 'unknown']}</strong></p>
                    <dl className="sa-data-list">
                      <div><dt>Association</dt><dd>{device.paired ? device.availability === 'unknown' ? 'Paired, awaiting contact' : previewMode ? 'Simulated pairing' : 'Paired' : 'Not associated'}</dd></div>
                      <div><dt>Availability</dt><dd>{previewMode ? 'Simulated connection' : deviceFresh ? device.availability : 'stale'}</dd></div>
                      <div><dt>Telemetry fresh</dt><dd>{deviceFresh && device.telemetry_fresh ? 'Yes' : 'No'}</dd></div>
                      <div><dt>Measurement</dt><dd>{deviceFresh && device.measurement_fresh && device.sensor_valid && device.current_distance_cm !== null ? `${device.current_distance_cm} cm current` : 'Unknown'}</dd></div>
                      <div><dt>Source</dt><dd>{device.source || 'Not reported'}</dd></div>
                      <div><dt>Recovery</dt><dd>{device.recovery_clear_count} / {device.recovery_required}</dd></div>
                      {device.battery_percent !== null && <div><dt>Battery</dt><dd>{device.battery_percent}%</dd></div>}
                      {device.firmware_version && <div><dt>Firmware</dt><dd>{device.firmware_version}</dd></div>}
                    </dl>
                    {device.last_valid_distance_cm !== null && <p className="sa-diagnostic">Historical diagnostic: sensor last reported {device.last_valid_distance_cm} cm, {device.last_valid_distance_age_ms ?? 'unknown'} ms ago.</p>}
                    {device.latest_command && <div className="sa-audit"><strong>Haptic audit: {device.latest_command.status}</strong><p>{device.latest_command.execution_reported ? 'Firmware reported execution.' : 'Execution not reported.'} This does not prove physical vibration or wearer perception.</p></div>}
                  </>
                )}
              </section>

              <section className="sa-panel">
                <div role="heading" aria-level={2}>Camera role</div>
                <SelectField label="This device acts as" value={cameraRole} onChange={(value) => { stopLocal(); setVisionSuppressed(true); setCameraConsent(false); setSingleProducer(false); live.current.cameraRole = value as CameraRole; live.current.cameraConsent = false; setCameraRole(value as CameraRole) }} options={[
                  { value: 'viewer', label: 'Viewer and audio only' },
                  { value: 'browser', label: 'Browser-camera producer' },
                  { value: 'glasses', label: 'Glasses-camera viewer' },
                ]} />
                {cameraRole === 'browser' && <Checkbox checked={cameraConsent} onChange={(value) => { live.current.cameraConsent = value; setCameraConsent(value); if (!value) { stopLocal(); setVisionSuppressed(true) } }} label="I consent to browser camera uploads" description="Revoking consent stops this browser’s uploads and hides old output. It does not claim to stop an external glasses camera." />}
                {cameraRole === 'browser' && <Checkbox checked={singleProducer} onChange={(value) => { live.current.singleProducer = value; setSingleProducer(value); if (!value) { stopLocal(); setVisionSuppressed(true) } }} label="Operator confirms this is the only producer in a dedicated development session" description="Server camera ownership is not implemented. Do not switch physical producers within this session." />}
                {cameraRole === 'viewer' && <p>Viewer mode does not activate this phone’s camera or take over another camera source.</p>}
              </section>
            </div>
          </div>
        )}

        {tab === 'memory' && (
          <div className="sa-page">
            <header className="sa-header"><div><div className="sa-kicker">HISTORICAL SIGHTINGS</div><div role="heading" aria-level={1} className="sa-title">Memory</div></div><Button variant="neutral" onClick={loadMemory}>Refresh</Button></header>
            <section className="sa-panel">
              <InputField placeholder="" aria-label="Search object label" label="Search object label" value={query} onChange={setQuery} prefix={<Search />} />
              {memoryState === 'loading' && <p>Loading sightings…</p>}
              {memoryState === 'error' && <StatusMessage tone="danger">Memory could not be loaded.</StatusMessage>}
              {memoryState === 'ready' && sightings.length === 0 && <p>No saved sightings match this search.</p>}
              <div className="sa-sightings">
                {sightings.map((sighting) => (
                  <div key={sighting.sighting_id}>
                    <div><span>Historical sighting</span><strong>{sighting.label}</strong></div>
                    <div><span>Age</span><strong>{Math.round((sighting.age_ms + Math.max(0, now - memoryFetchedAt)) / 1000)} seconds</strong></div>
                    <div><span>Source</span><strong>{sighting.source} · {sighting.provider}</strong></div>
                    <div><span>Checkpoint context</span><strong>{sighting.checkpoint_id ? `Last confirmed checkpoint ${sighting.checkpoint_id}` : 'Not available'}</strong></div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {tab === 'settings' && (
          <div className="sa-page">
            <header className="sa-header"><div><div className="sa-kicker">PREFERENCES</div><div role="heading" aria-level={1} className="sa-title">Settings</div></div></header>
            <div className="sa-two-column">
              <section className="sa-panel">
                <div role="heading" aria-level={2}>Data connection</div>
                <p>{previewMode ? 'Demo data is active. Connect when the application backend is available.' : `Connected to backend session ${sessionId}. Authentication uses an HttpOnly cookie.`}</p>
                {connection === 'unauthorized' && <StatusMessage tone="danger">Unauthorized. Check the session ID and token.</StatusMessage>}
                {connection === 'error' && <StatusMessage tone="warning">{error || 'Backend connection unavailable.'}</StatusMessage>}
                <InputField placeholder="" aria-label="Session ID" label="Session ID" value={connectSessionId} onChange={setConnectSessionId} autoComplete="username" />
                <InputField placeholder="" aria-label="Session token" label="Session token" type="password" value={connectToken} onChange={setConnectToken} autoComplete="current-password" />
                <div className="sa-actions">
                  <Button variant="primary" disabled={!connectSessionId || !connectToken || connection === 'connecting'} onClick={() => connect(connectSessionId, connectToken)}>
                    {connection === 'connecting' ? 'Connecting…' : previewMode ? 'Connect backend' : 'Reconnect'}
                  </Button>
                  {!previewMode && <Button variant="neutral" onClick={useDemoData}>Use demo data</Button>}
                </div>
                <p className="sa-diagnostic">Session tokens are not saved in localStorage. Camera and controller firmware credentials do not belong in this application.</p>
              </section>
              <section className="sa-panel">
                <div role="heading" aria-level={2}>Appearance</div>
                <SelectField label="Text size" value={textSize} onChange={(value) => { setTextSize(value); document.documentElement.dataset.strideTextSize = value }} options={[{ value: 'standard', label: 'Standard' }, { value: 'large', label: 'Large' }, { value: 'largest', label: 'Largest' }]} />
                <div className="sa-actions"><Button variant={theme === 'light' ? 'primary' : 'neutral'} onClick={() => setTheme('light')}>Light</Button><Button variant={theme === 'dark' ? 'primary' : 'neutral'} onClick={() => setTheme('dark')}>Dark</Button></div>
              </section>
              <section className="sa-panel">
                <div role="heading" aria-level={2}>Browser speech</div>
                <p>{speechStatus}. Audio uses the system-selected output; AirPods routing is not verified.</p>
                <div className="sa-actions">
                  <Button variant="primary" onClick={() => { speech.current.enable(); setSpeechStatus(speech.current.status()) }}>Enable audio</Button>
                  <Button variant="neutral" disabled={speechStatus !== 'Browser speech enabled'} onClick={() => speech.current.speak(newActionId(), 'STRIDE browser speech test.')}>Test audio</Button>
                </div>
                <SelectField label="Speech rate" value={speechRate} onChange={(value) => { setSpeechRate(value); speech.current.rate = Number(value) }} options={[{ value: '0.8', label: 'Slow' }, { value: '1', label: 'Normal' }, { value: '1.2', label: 'Fast' }]} />
                <SwitchField label="Speak live observations" description="Route and urgent feedback remain enabled." hasDescription defaultSelected={observationSpeech} onChange={(value) => { setObservationSpeech(value); speech.current.observations = value; speech.current.reconcile() }} />
              </section>
            </div>
          </div>
        )}
      </main>

      {navigation && !['idle', 'completed'].includes(navigation.state) && (
        <Button className="sa-stop" iconStart={<X />} onClick={() => routeAction('stop')}>Stop guidance</Button>
      )}
    </div>
  )
}
