import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  InputField,
  SelectField,
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
} from './api'
import { BrowserCameraController, SpeechController } from './controllers'
import './app.css'

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
        <InputField label="Session ID" value={sessionId} onChange={setSessionId} autoComplete="username" />
        <InputField label="Session token" type="password" value={token} onChange={setToken} autoComplete="current-password" />
        <Button variant="primary" disabled={!sessionId || !token || state === 'connecting'} onClick={() => onConnect(sessionId, token)}>
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
  const actionIds = useRef(new Map<string, string>())
  const [deviceId, setDeviceId] = useState('')
  const [device, setDevice] = useState<DeviceStatus | null>(null)
  const [deviceError, setDeviceError] = useState('')
  const [pairing, setPairing] = useState(false)
  const [vision, setVision] = useState<VisionLatest | null>(null)
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

  const connect = async (id: string, token: string) => {
    setConnection('connecting')
    setError('')
    try {
      await strideApi.connect(id, token)
      setSessionId(id)
      setConnection('connected')
      setRoutesState('loading')
      const [result, recalled] = await Promise.all([strideApi.routes(id), strideApi.memory(id)])
      setPreviewMode(false)
      setConnectToken('')
      setRoutes(result.routes)
      setNavigation(recalled.navigation)
      setSelectedRoute(result.routes.find((route) => route.checked)?.route_id || '')
      setRoutesState('ready')
    } catch (cause) {
      setConnection(cause instanceof ApiError && [401, 403].includes(cause.status) ? 'unauthorized' : 'error')
      setError(cause instanceof Error ? cause.message : 'Connection failed')
      setRoutesState('error')
    }
  }

  const useDemoData = () => {
    camera.current.stop()
    speech.current.cancel()
    setPreviewMode(true)
    setConnection('connected')
    setSessionId('demo-preview')
    setRoutes([previewRoute])
    setRoutesState('ready')
    setSelectedRoute(previewRoute.route_id)
    setNavigation(null)
    setDevice(null)
    setDeviceId('')
    setVision(null)
    setMemory(previewMemory)
    setMemoryState('ready')
    setError('')
  }

  const refreshAuthoritativeNavigation = async () => {
    const result = await strideApi.memory(sessionId)
    setNavigation(result.navigation)
    return result.navigation
  }

  const routeAction = async (action: 'start' | 'confirm' | 'repeat' | 'pause' | 'resume' | 'stop') => {
    if (!sessionId || routePending) return
    if (previewMode) {
      if (action === 'start') {
        setNavigation({
          navigation_id: 'preview-navigation',
          route_id: previewRoute.route_id,
          state: 'guiding',
          state_revision: 1,
          current_checkpoint: { checkpoint_id: 'ticket-gates', ordinal: 0, landmark: 'Station ticket gates' },
          confirmed_checkpoint_count: 0,
          total_checkpoints: 2,
          confirmed_checkpoints: [],
          instruction: previewRoute.checkpoints[0].instruction,
          guidance_event: null,
          status_message: 'Preview guidance',
          sensor_monitoring: 'not_associated',
          paired_device_id: null,
          obstacle_state: null,
        })
        return
      }
      if (!navigation) return
      if (action === 'confirm') {
        const count = navigation.confirmed_checkpoint_count + 1
        const confirmed = navigation.current_checkpoint ? [...navigation.confirmed_checkpoints, navigation.current_checkpoint] : navigation.confirmed_checkpoints
        setNavigation({
          ...navigation,
          state: count >= navigation.total_checkpoints ? 'completed' : 'guiding',
          state_revision: navigation.state_revision + 1,
          confirmed_checkpoint_count: count,
          confirmed_checkpoints: confirmed,
          current_checkpoint: count >= navigation.total_checkpoints ? null : { checkpoint_id: 'library-doors', ordinal: 1, landmark: 'Library entrance doors' },
          instruction: count >= navigation.total_checkpoints ? null : previewRoute.checkpoints[1].instruction,
          status_message: count >= navigation.total_checkpoints ? 'Route completed.' : 'Continue to the next checkpoint.',
        })
        return
      }
      setNavigation({
        ...navigation,
        state: action === 'pause' ? 'paused' : action === 'resume' ? 'guiding' : action === 'stop' ? 'idle' : navigation.state,
        state_revision: action === 'repeat' ? navigation.state_revision : navigation.state_revision + 1,
      })
      if (action === 'stop') {
        speech.current.cancel()
        camera.current.stop()
      }
      return
    }
    const key = `${action}:${navigation?.navigation_id || selectedRoute}:${navigation?.state_revision ?? 'start'}`
    const actionId = actionIds.current.get(key) || newActionId()
    actionIds.current.set(key, actionId)
    setRoutePending(true)
    setError('')
    if (action === 'stop') {
      speech.current.cancel()
      camera.current.stop()
    }
    try {
      const result = await strideApi.routeAction(sessionId, actionId, action, selectedRoute, navigation || undefined)
      actionIds.current.delete(key)
      setNavigation(result)
      const event = result.guidance_event
      if (event && event.valid && event.navigation_id === result.navigation_id && event.state_revision === result.state_revision && event.expires_at > Date.now()) {
        speech.current.speak(event.event_id, event.instruction)
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        await refreshAuthoritativeNavigation()
        setError('Guidance changed on the server. The latest state is shown.')
      } else {
        setError(action === 'stop' ? 'Local activity stopped, but server Stop could not be confirmed.' : cause instanceof Error ? cause.message : 'Guidance request failed')
      }
    } finally {
      setRoutePending(false)
    }
  }

  const refreshDevice = async () => {
    if (!deviceId || !sessionId) return
    try {
      const result = await strideApi.deviceStatus(deviceId, sessionId)
      setDevice(result)
      if (result.navigation_revision !== null && result.navigation_revision !== navigation?.state_revision) {
        await refreshAuthoritativeNavigation()
      }
      setDeviceError('')
    } catch (cause) {
      setDevice(null)
      setDeviceError(cause instanceof ApiError && [401, 403].includes(cause.status) ? 'Pairing denied or controller unconfigured.' : cause instanceof Error ? cause.message : 'Device status unavailable.')
    }
  }

  useEffect(() => {
    if (previewMode || connection !== 'connected' || !deviceId) return
    refreshDevice()
    const timer = window.setInterval(refreshDevice, 1000)
    return () => window.clearInterval(timer)
  }, [connection, deviceId, sessionId, navigation?.state_revision])

  useEffect(() => {
    if (previewMode || connection !== 'connected' || !vision || !['active', 'paused'].includes(vision.state)) return
    const timer = window.setInterval(async () => {
      try {
        const latest = await strideApi.visionLatest(sessionId)
        setVision(latest)
        setVisionFetchedAt(Date.now())
        setVisionError('')
      } catch (cause) {
        setVisionError(cause instanceof Error ? cause.message : 'Recognition unavailable.')
      }
    }, 500)
    return () => window.clearInterval(timer)
  }, [connection, sessionId, vision?.state])

  useEffect(() => () => {
    camera.current.stop()
    speech.current.cancel()
  }, [])

  const controlVision = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    setVisionError('')
    try {
      if (previewMode) {
        setVision({
          state: action === 'start' || action === 'resume' ? 'active' : action === 'pause' ? 'paused' : 'stopped',
          status: action === 'start' || action === 'resume' ? 'live' : action === 'pause' ? 'paused' : 'unavailable',
          generation: 1,
          state_seq: 1,
          source_revision: 0,
          detector_configured: true,
          source: 'fixture',
          origin: 'demo_preview',
          device_id: 'preview-camera',
          frame_id: 'preview-frame',
          age_ms: action === 'start' || action === 'resume' ? 80 : null,
          objects: action === 'start' || action === 'resume' ? [{ label: 'bench', score: .91, bbox: [.58, .48, .84, .78], position: 'right' }] : [],
          speech_event: null,
          last_inference_error: null,
        })
        setVisionFetchedAt(Date.now())
        return
      }
      if (action === 'start' && cameraRole === 'browser' && !cameraConsent) {
        throw new Error('Consent is required before browser camera uploads.')
      }
      const result = await strideApi.visionAction(sessionId, newActionId(), action, vision?.generation)
      const latest = await strideApi.visionLatest(sessionId)
      setVision(latest)
      setVisionFetchedAt(Date.now())
      if (action === 'start' && cameraRole === 'browser') {
        if (!videoRef.current) throw new Error('Camera preview is unavailable.')
        await camera.current.start(videoRef.current, sessionId, setVisionError)
      }
      if (action === 'pause' || action === 'stop') camera.current.stop()
      if (action === 'stop') setVision({ ...latest, state: 'stopped', status: result.status })
    } catch (cause) {
      setVisionError(cause instanceof Error ? cause.message : 'Vision control unavailable.')
    }
  }

  const effectiveVisionAge = vision?.age_ms === null || vision?.age_ms === undefined ? null : vision.age_ms + Math.max(0, Date.now() - visionFetchedAt)
  const liveVision = vision?.status === 'live' && effectiveVisionAge !== null && effectiveVisionAge <= 1000
  const blocked = navigation?.state === 'blocked' || Boolean(device?.paired && (device.availability !== 'connected' || !device.telemetry_fresh || ['caution', 'danger', 'unknown'].includes(device.obstacle_state)))

  useEffect(() => {
    if (!vision?.speech_event || !liveVision || blocked) return
    speech.current.speak(vision.speech_event.event_id, vision.speech_event.text, 'observation')
  }, [vision?.speech_event?.event_id, liveVision, blocked])

  useEffect(() => {
    const obstacle = navigation?.obstacle_state || device?.obstacle_state
    if (obstacle === 'danger') {
      speech.current.speak(`obstacle:${navigation?.navigation_id || device?.device_id}:${navigation?.state_revision || device?.navigation_revision}`, obstacleCopy.danger, 'urgent')
    } else if (blocked) {
      speech.current.cancel()
    }
  }, [navigation?.obstacle_state, navigation?.state_revision, device?.obstacle_state, device?.navigation_revision, blocked])

  const loadMemory = async () => {
    if (previewMode) {
      setMemory(previewMemory)
      setMemoryState('ready')
      return
    }
    setMemoryState('loading')
    try {
      setMemory(await strideApi.memory(sessionId))
      setMemoryState('ready')
    } catch {
      setMemoryState('error')
    }
  }

  useEffect(() => {
    if (tab === 'memory' && connection === 'connected') loadMemory()
  }, [tab])

  const currentRoute = routes.find((route) => route.route_id === navigation?.route_id)
  const currentCheckpoint = navigation?.current_checkpoint
  const lastConfirmed = navigation?.confirmed_checkpoints.at(-1)
  const sightings = useMemo(() => (memory?.sightings || []).filter((item) => item.label.toLowerCase().includes(query.toLowerCase())), [memory, query])

  if (!previewMode && connection !== 'connected') {
    return <div className="stride-app"><ConnectionPanel state={connection} error={error} onConnect={connect} /></div>
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
        {error && <StatusMessage tone="warning">{error}</StatusMessage>}

        {tab === 'guidance' && (
          <div className="sa-page">
            <header className="sa-header">
              <div><div className="sa-kicker">ASSISTED NAVIGATION</div><div role="heading" aria-level={1} className="sa-title">Guidance</div></div>
            </header>

            {navigation?.obstacle_state && <ObstacleBanner state={navigation.obstacle_state} />}
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
                    <Button variant="primary" disabled={!selectedRoute || routePending} onClick={() => routeAction('start')}>Start Guidance</Button>
                  </>
                ) : (
                  <>
                    <div className="sa-route-name">{currentRoute?.name || 'Selected route'} · {navigation.state}</div>
                    <div role="heading" aria-level={2} className="sa-instruction">{navigation.instruction || navigation.status_message}</div>
                    <div className="sa-progress">
                      <div><span>Current checkpoint</span><strong>{currentCheckpoint?.landmark || currentCheckpoint?.checkpoint_id || 'None'}</strong></div>
                      <div><span>Last explicitly confirmed</span><strong>{lastConfirmed?.landmark || lastConfirmed?.checkpoint_id || 'None yet'}</strong></div>
                      <div><span>Confirmed</span><strong>{navigation.confirmed_checkpoint_count} / {navigation.total_checkpoints}</strong></div>
                    </div>
                    <div className="sa-actions">
                      <Button variant="primary" disabled={navigation.state !== 'guiding' || routePending} onClick={() => routeAction('confirm')}>Confirm Arrival</Button>
                      <Button variant="neutral" disabled={navigation.state !== 'guiding' || routePending} onClick={() => routeAction('repeat')}>Repeat</Button>
                      {navigation.state === 'paused' ? (
                        <Button variant="neutral" disabled={routePending} onClick={() => routeAction('resume')}>Resume</Button>
                      ) : (
                        <Button variant="neutral" disabled={navigation.state !== 'guiding' || routePending} onClick={() => routeAction('pause')}>Pause</Button>
                      )}
                    </div>
                    {navigation.state === 'completed' && <Button variant="neutral" disabled={routePending} onClick={() => routeAction('stop')}>Choose another route</Button>}
                  </>
                )}
              </section>

              <aside className="sa-secondary-panel">
                <div className="sa-kicker">LIVE AWARENESS</div>
                <div role="heading" aria-level={2}>What’s ahead</div>
                <div className="sa-vision-status">{vision?.status || 'off'}{effectiveVisionAge !== null ? ` · ${effectiveVisionAge} ms` : ''}</div>
                {visionError && <StatusMessage tone="warning">{visionError}</StatusMessage>}
                {cameraRole === 'browser' && (
                  <div className="sa-video-wrap">
                    <video ref={videoRef} className="sa-video" muted playsInline aria-label="Browser camera preview" />
                    {liveVision && <div className="sa-overlay">{vision!.objects.map((object, index) => <span key={`${object.label}-${index}`} style={{ left: `${object.bbox[0] * 100}%`, top: `${object.bbox[1] * 100}%`, width: `${(object.bbox[2] - object.bbox[0]) * 100}%`, height: `${(object.bbox[3] - object.bbox[1]) * 100}%` }}>{object.label}</span>)}</div>}
                  </div>
                )}
                {cameraRole === 'glasses' && <p>Glasses-camera preview frames are unavailable unless the backend provides video separately.</p>}
                {liveVision ? (
                  vision!.objects.length ? (
                    <div className="sa-detections">
                      <strong>{vision!.objects.map((object) => `${object.label} ${object.position}`).join('; ')}.</strong>
                    </div>
                  ) : <p>No supported objects detected in the latest frame.</p>
                ) : <p>Current recognition is unavailable. Expired results and boxes are hidden.</p>}
                <div className="sa-actions">
                  {!vision || ['idle', 'stopped'].includes(vision.state) ? <Button variant="primary" disabled={blocked} onClick={() => controlVision('start')}>Start</Button> : null}
                  {vision?.state === 'active' && <Button variant="neutral" onClick={() => controlVision('pause')}>Pause</Button>}
                  {vision?.state === 'paused' && <Button variant="neutral" onClick={() => controlVision('resume')}>Resume</Button>}
                  {vision && !['idle', 'stopped'].includes(vision.state) && <Button variant="neutral" onClick={() => controlVision('stop')}>Stop awareness</Button>}
                </div>
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
                <InputField label="Controller ID" value={deviceId} onChange={setDeviceId} />
                <Button variant="primary" disabled={!deviceId || pairing} onClick={async () => {
                  setPairing(true)
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
                      await strideApi.pairDevice(deviceId, sessionId)
                      await refreshDevice()
                    }
                  } catch (cause) { setDeviceError(cause instanceof Error ? cause.message : 'Pairing unavailable.') } finally { setPairing(false) }
                }}>{pairing ? 'Pairing…' : 'Pair controller'}</Button>
                {deviceError && <StatusMessage tone="warning">{deviceError}</StatusMessage>}
                {!device && !deviceError && <p>Not associated.</p>}
                {device && (
                  <>
                    <ObstacleBanner state={device.obstacle_state} />
                    <dl className="sa-data-list">
                      <div><dt>Association</dt><dd>{device.paired ? device.availability === 'unknown' ? 'Paired, awaiting contact' : 'Paired' : 'Not associated'}</dd></div>
                      <div><dt>Availability</dt><dd>{device.availability}</dd></div>
                      <div><dt>Telemetry fresh</dt><dd>{device.telemetry_fresh ? 'Yes' : 'No'}</dd></div>
                      <div><dt>Measurement</dt><dd>{device.measurement_fresh && device.sensor_valid && device.current_distance_cm !== null ? `${device.current_distance_cm} cm current` : 'Unknown'}</dd></div>
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
                <SelectField label="This device acts as" value={cameraRole} onChange={(value) => setCameraRole(value as CameraRole)} options={[
                  { value: 'viewer', label: 'Viewer and audio only' },
                  { value: 'browser', label: 'Browser-camera producer' },
                  { value: 'glasses', label: 'Glasses-camera viewer' },
                ]} />
                {cameraRole === 'browser' && <Checkbox checked={cameraConsent} onChange={(value) => { setCameraConsent(value); if (!value) { camera.current.stop(); setVision(null) } }} label="I consent to browser camera uploads" description="Revoking consent stops this browser’s uploads and hides old output. It does not claim to stop an external glasses camera." />}
                {cameraRole === 'viewer' && <p>Viewer mode does not activate this phone’s camera or take over another camera source.</p>}
              </section>
            </div>
          </div>
        )}

        {tab === 'memory' && (
          <div className="sa-page">
            <header className="sa-header"><div><div className="sa-kicker">HISTORICAL SIGHTINGS</div><div role="heading" aria-level={1} className="sa-title">Memory</div></div><Button variant="neutral" onClick={loadMemory}>Refresh</Button></header>
            <section className="sa-panel">
              <InputField label="Search object label" value={query} onChange={setQuery} prefix={<Search />} />
              {memoryState === 'loading' && <p>Loading sightings…</p>}
              {memoryState === 'error' && <StatusMessage tone="danger">Memory could not be loaded.</StatusMessage>}
              {memoryState === 'ready' && sightings.length === 0 && <p>No saved sightings match this search.</p>}
              <div className="sa-sightings">
                {sightings.map((sighting) => (
                  <div key={sighting.sighting_id}>
                    <div><span>Historical sighting</span><strong>{sighting.label}</strong></div>
                    <div><span>Age</span><strong>{Math.round(sighting.age_ms / 1000)} seconds</strong></div>
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
                <InputField label="Session ID" value={connectSessionId} onChange={setConnectSessionId} autoComplete="username" />
                <InputField label="Session token" type="password" value={connectToken} onChange={setConnectToken} autoComplete="current-password" />
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
                <SelectField label="Text size" value={document.documentElement.dataset.strideTextSize || 'standard'} onChange={(value) => { document.documentElement.dataset.strideTextSize = value }} options={[{ value: 'standard', label: 'Standard' }, { value: 'large', label: 'Large' }, { value: 'largest', label: 'Largest' }]} />
                <div className="sa-actions"><Button variant={theme === 'light' ? 'primary' : 'neutral'} onClick={() => setTheme('light')}>Light</Button><Button variant={theme === 'dark' ? 'primary' : 'neutral'} onClick={() => setTheme('dark')}>Dark</Button></div>
              </section>
              <section className="sa-panel">
                <div role="heading" aria-level={2}>Browser speech</div>
                <p>{speechStatus}</p>
                <div className="sa-actions">
                  <Button variant="primary" onClick={() => { speech.current.enable(); setSpeechStatus(speech.current.status()) }}>Enable audio</Button>
                  <Button variant="neutral" disabled={speechStatus !== 'Browser speech enabled'} onClick={() => speech.current.speak(newActionId(), 'STRIDE browser speech test.')}>Test audio</Button>
                </div>
                <SelectField label="Speech rate" value={speechRate} onChange={(value) => { setSpeechRate(value); speech.current.rate = Number(value) }} options={[{ value: '0.8', label: 'Slow' }, { value: '1', label: 'Normal' }, { value: '1.2', label: 'Fast' }]} />
                <SwitchField label="Speak live observations" description="Route and urgent feedback remain enabled." hasDescription defaultSelected={observationSpeech} onChange={(value) => { setObservationSpeech(value); speech.current.observations = value }} />
              </section>
            </div>
          </div>
        )}
      </main>

      {navigation && !['idle', 'completed'].includes(navigation.state) && (
        <Button className="sa-stop" iconStart={<X />} disabled={routePending} onClick={() => routeAction('stop')}>Stop guidance</Button>
      )}
    </div>
  )
}
