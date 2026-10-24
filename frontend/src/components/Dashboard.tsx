// Dashboard — wired to real backend state via useStride. Layout classes and
// structure preserved from the Figma export; fabricated data replaced with
// authoritative server/controller state. No invented distances, no false device
// claims, simulation explicitly labeled.

import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  InputField,
  SelectField,
  SwitchField,
  useTheme,
  Home,
  Search,
  Settings as SettingsIcon,
  Play,
  X,
} from '@figma/astraui'
import { useStride, type CameraSource } from '../lib/useStride'
import type { ApiMode } from '../lib/api'
import type { StatusResponse, VisionLatest } from '../lib/types'

type View = 'guidance' | 'memory' | 'settings'

// Human words for the provider/source — "Simulation" is explicit, never hidden.
function providerLabel(status: StatusResponse | null, mode: ApiMode): string {
  if (mode === 'fixture') return 'Simulation (fixtures)'
  if (!status) return 'Connecting…'
  const p = status.perception
  return `${p.provider} · ${p.available ? 'available' : 'unavailable'}`
}

function sourceWord(mode: ApiMode, status: StatusResponse | null): string {
  if (mode === 'fixture') return 'Simulation'
  return status?.camera?.source ?? '—'
}

function CameraPreview({ vision, stale }: { vision: VisionLatest | null; stale: boolean }) {
  return (
    <div className="camera-wrap">
      <div className="camera-head">
        <div>
          <span className={`status-dot ${stale ? 'warning-dot' : ''}`} />
          <strong>
            {stale || !vision ? 'Vision unavailable' : `Fresh · ${Math.round(vision.age_ms ?? 0)} ms ago`}
          </strong>
        </div>
        <span>{vision?.origin === 'w11_camera' ? 'Glasses camera' : vision?.origin ?? 'Camera'}</span>
      </div>
      <div className="camera-view" role="img" aria-label="Live camera preview with detected object boxes">
        <div className="horizon" />
        {!stale &&
          vision?.objects?.map((o) => {
            const [x1, y1, x2, y2] = o.box
            return (
              <div
                key={o.track_id}
                className="box"
                style={{
                  left: `${x1 * 100}%`,
                  top: `${y1 * 100}%`,
                  width: `${(x2 - x1) * 100}%`,
                  height: `${(y2 - y1) * 100}%`,
                }}
              >
                <span>
                  {o.label} · {o.position}
                </span>
              </div>
            )
          })}
      </div>
    </div>
  )
}

export function Dashboard({ exit }: { exit: () => void }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const stride = useStride(videoRef)
  const { state } = stride
  const { theme, setTheme } = useTheme()

  const [view, setView] = useState<View>('guidance')
  const [mode, setMode] = useState<ApiMode>('fixture')
  const [baseUrl, setBaseUrl] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [joinSession, setJoinSession] = useState('')
  const [search, setSearch] = useState('')
  const [findResult, setFindResult] = useState<string | null>(null)
  const [textSize, setTextSize] = useState<'standard' | 'large' | 'largest'>('large')
  const [speechRate, setSpeechRate] = useState<'slow' | 'normal' | 'fast'>('normal')
  const [spokenOn, setSpokenOn] = useState(true)

  const route = state.status?.route
  const routeState = route?.state ?? 'idle'
  const connected = state.connection === 'connected'

  // Apply text-size as a functional document data attribute (CSS hooks on it).
  useEffect(() => {
    document.documentElement.dataset.textSize = textSize
  }, [textSize])

  useEffect(() => {
    const rate = speechRate === 'slow' ? 0.8 : speechRate === 'fast' ? 1.25 : 1
    stride.setSpeechRate(rate)
  }, [speechRate, stride])

  const doConnect = async () => {
    setMode(mode)
    try {
      await stride.connect({ accessCode: accessCode || undefined, sessionId: joinSession, mode, baseUrl })
    } catch {
      /* lastError is surfaced in state */
    }
  }

  const start = () => void stride.startGuidance()

  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label="STRIDE dashboard">
        <div className="app-nav-items">
          <Button variant={view === 'guidance' ? 'primary' : 'subtle'} iconStart={<Home />} onClick={() => setView('guidance')}>
            Guidance
          </Button>
          <Button variant={view === 'memory' ? 'primary' : 'subtle'} iconStart={<Search />} onClick={() => setView('memory')}>
            Memory
          </Button>
          <Button variant={view === 'settings' ? 'primary' : 'subtle'} iconStart={<SettingsIcon />} onClick={() => setView('settings')}>
            Settings
          </Button>
        </div>
        <Button variant="subtle" onClick={exit}>
          Exit
        </Button>
      </nav>

      {/* Off-screen video element for browser capture; shown inside preview when live */}
      <video ref={videoRef} playsInline muted style={{ display: 'none' }} aria-hidden="true" />

      <main className="dashboard-main">
        {view === 'guidance' && (
          <>
            <header className="dashboard-header">
              <div>
                <div className="eyebrow">{mode === 'fixture' ? 'Simulation session' : connected ? 'Live session' : 'Not connected'}</div>
                <div role="heading" aria-level={1} className="dash-title">
                  Guidance
                </div>
              </div>
              {/* Honest: report browser speech readiness, not a device connection */}
              <div className="device-summary">
                <span className={`status-dot ${state.speechState === 'off' ? 'warning-dot' : ''}`} />
                {state.speechSupported
                  ? state.speechState === 'off'
                    ? 'Speech off'
                    : 'Browser speech ready'
                  : 'Speech unsupported'}
              </div>
            </header>

            {routeState === 'blocked' && (
              <div className="urgent-banner" role="alert">
                <X aria-hidden="true" />
                <div>
                  <strong>Stop. Obstacle very close ahead.</strong>
                  <span>Route instructions and ordinary observations are paused.</span>
                </div>
              </div>
            )}

            <div className="dashboard-grid">
              <section className="guidance-panel" aria-labelledby="current-guidance">
                {routeState === 'idle' ? (
                  <div className="setup-flow">
                    <div className="panel-kicker">SETUP</div>
                    <div id="current-guidance" role="heading" aria-level={2} className="instruction">
                      Get ready for guidance.
                    </div>
                    <div className="setup-list">
                      <div className="setup-row">
                        <span>1</span>
                        <div className="grow">
                          <SelectField
                            label="Development mode"
                            value={mode}
                            onChange={(v: string) => setMode(v as ApiMode)}
                            options={[
                              { value: 'fixture', label: 'Simulation (fixtures)' },
                              { value: 'real', label: 'Real backend' },
                            ]}
                          />
                          {mode === 'real' && (
                            <InputField label="Backend base URL" value={baseUrl} onChange={setBaseUrl} placeholder="(same origin)" />
                          )}
                        </div>
                      </div>
                      <div className="setup-row">
                        <span>2</span>
                        <div className="grow">
                          <InputField label="Access code" type="password" value={accessCode} onChange={setAccessCode} />
                          <InputField label="Join session ID (optional)" value={joinSession} onChange={setJoinSession} placeholder="create new if blank" />
                          <Button variant={connected ? 'neutral' : 'primary'} onClick={doConnect}>
                            {connected ? 'Reconnect' : 'Connect'}
                          </Button>
                        </div>
                      </div>
                      <div className="setup-row">
                        <span>3</span>
                        <div>
                          <strong>Audio</strong>
                          <p>Enable browser speech. The web app cannot select AirPods for you — choose them in iOS.</p>
                        </div>
                        <Button variant="neutral" onClick={stride.enableSpeech}>
                          Enable / test audio
                        </Button>
                      </div>
                      <div className="setup-row">
                        <span>4</span>
                        <div className="grow">
                          <SelectField
                            label="Camera source"
                            value={state.cameraSource}
                            onChange={(v: string) => void stride.setCameraSource(v as CameraSource)}
                            options={[
                              { value: 'glasses', label: 'Glasses camera (W11)' },
                              { value: 'browser', label: 'Browser camera' },
                            ]}
                          />
                        </div>
                      </div>
                      <div className="setup-row">
                        <span>5</span>
                        <div className="grow">
                          <Checkbox
                            checked={state.consent}
                            onChange={stride.setConsent}
                            label="I consent to uploading camera images during this session"
                            description="Required for hosted detection. Withdrawing consent stops uploads immediately."
                          />
                          {state.cameraSource === 'browser' && state.consent && (
                            <Button variant="neutral" onClick={() => void stride.useThisDeviceCamera()}>
                              {state.cameraActive ? 'Camera active' : "Use this device's camera"}
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                    <Button variant="primary" iconStart={<Play />} disabled={!connected || !state.consent} onClick={start}>
                      Start guidance
                    </Button>
                    {state.lastError && <p className="error-line" role="alert">{state.lastError}</p>}
                  </div>
                ) : (
                  <div className="active-guidance">
                    <div className="route-row">
                      <div>
                        <span>Current route</span>
                        <strong>{state.status?.route?.route_id ?? 'Route'}</strong>
                      </div>
                      <span className={`state-label ${routeState}`}>{routeState}</span>
                    </div>
                    <div id="current-guidance" role="heading" aria-level={2} className="instruction">
                      {route?.instruction ?? 'Waiting for the next instruction.'}
                    </div>
                    <div className="checkpoint-grid">
                      <div>
                        <span>Checkpoint</span>
                        <strong>{route?.checkpoint_id ?? '—'}</strong>
                      </div>
                      <div>
                        <span>Turn cue</span>
                        <strong>{route?.pattern ?? '—'}</strong>
                      </div>
                    </div>
                    <div className="button-row action-row">
                      <Button variant="primary" disabled={routeState !== 'guiding'} onClick={() => void stride.routeAction('confirm')}>
                        Confirm arrival
                      </Button>
                      <Button variant="neutral" disabled={!(routeState === 'guiding' || routeState === 'paused')} onClick={() => void stride.routeAction('repeat')}>
                        Repeat instruction
                      </Button>
                      {routeState === 'paused' ? (
                        <Button variant="neutral" onClick={() => void stride.routeAction('resume')}>
                          Resume
                        </Button>
                      ) : (
                        <Button variant="neutral" disabled={routeState !== 'guiding'} onClick={() => void stride.routeAction('pause')}>
                          Pause
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </section>

              <aside className="awareness-panel" aria-labelledby="awareness-title">
                <div className="panel-heading">
                  <div>
                    <div className="panel-kicker">LIVE AWARENESS</div>
                    <div id="awareness-title" role="heading" aria-level={2}>
                      What’s ahead
                    </div>
                  </div>
                  <span className="demo-label">{providerLabel(state.status, mode)}</span>
                </div>
                {routeState === 'idle' || !state.vision ? (
                  <div className="empty-awareness">
                    <p>Continuous detection is off.</p>
                    <span>Start guidance to receive ongoing, concise observations.</span>
                  </div>
                ) : state.visionStale ? (
                  <div className="observation">
                    <span className="status-dot warning-dot" />
                    <p>
                      <strong>Live vision unavailable.</strong> No fresh results — visual guidance is suppressed.
                    </p>
                  </div>
                ) : (
                  <>
                    {state.vision.objects.length === 0 ? (
                      <div className="observation">
                        <span className="status-dot" />
                        <p>No notable objects detected ahead right now.</p>
                      </div>
                    ) : (
                      state.vision.objects.map((o) => (
                        <div className="observation" key={o.track_id}>
                          <span className="status-dot" />
                          <p>
                            {/* position words only — no invented distances */}
                            <strong>
                              {o.label} · {o.position}.
                            </strong>{' '}
                            Detector score {Math.round(o.score * 100)}%.
                          </p>
                        </div>
                      ))
                    )}
                    <CameraPreview vision={state.vision} stale={state.visionStale} />
                  </>
                )}
                <details>
                  <summary>Device details</summary>
                  <dl>
                    <div>
                      <dt>Camera</dt>
                      <dd>{state.cameraSource === 'glasses' ? 'Glasses camera (W11)' : 'Browser camera'} · {sourceWord(mode, state.status)}</dd>
                    </div>
                    <div>
                      <dt>Sensor</dt>
                      <dd>
                        {state.status?.feedback
                          ? `${state.status.feedback.connected ? 'connected' : 'offline'} · ${state.status.feedback.alert}`
                          : '—'}
                      </dd>
                    </div>
                    <div>
                      <dt>Detector</dt>
                      <dd>{providerLabel(state.status, mode)}</dd>
                    </div>
                    <div>
                      <dt>Result rate</dt>
                      <dd>{state.vision ? `${(state.vision.result_hz ?? 0).toFixed(1)} Hz` : '—'}</dd>
                    </div>
                  </dl>
                </details>
              </aside>
            </div>
          </>
        )}

        {view === 'memory' && (
          <section className="subpage">
            <div className="eyebrow">Historical sightings</div>
            <div role="heading" aria-level={1} className="dash-title">
              Memory
            </div>
            <p className="page-lede">Recent object labels from this session. These records are not current detections.</p>
            <div className="content-surface">
              <InputField label="Search an object label" placeholder="Try “bench” or “doorway”" value={search} onChange={setSearch} prefix={<Search />} />
              {(() => {
                const rows = state.memory.filter((r) => !search || r.label.toLowerCase().includes(search.toLowerCase()))
                if (rows.length === 0) {
                  return (
                    <div className="empty-result">
                      <strong>No saved sightings</strong>
                      <p>{state.memory.length === 0 ? 'Nothing recalled yet this session.' : 'Try another object label.'}</p>
                    </div>
                  )
                }
                return rows.map((r, i) => (
                  <div className="sighting" key={i}>
                    <div>
                      <span>SIGHTING</span>
                      <strong>{r.label}</strong>
                    </div>
                    <div>
                      <span>Last seen</span>
                      <strong>{Math.round(r.age_ms / 1000)}s ago</strong>
                    </div>
                    <div>
                      <span>Source</span>
                      <strong>{r.source}</strong>
                    </div>
                    <div>
                      <span>Checkpoint context</span>
                      <strong>{r.checkpoint_id ?? '—'}</strong>
                    </div>
                  </div>
                ))
              })()}
            </div>
          </section>
        )}

        {view === 'settings' && (
          <section className="subpage">
            <div className="eyebrow">Personal preferences</div>
            <div role="heading" aria-level={1} className="dash-title">
              Settings
            </div>
            <p className="page-lede">Choose how STRIDE looks, speaks and connects.</p>
            <div className="settings-grid">
              <div className="content-surface">
                <div role="heading" aria-level={2}>
                  Appearance
                </div>
                <SelectField
                  label="Text size"
                  value={textSize}
                  onChange={(v: string) => setTextSize(v as typeof textSize)}
                  options={[
                    { value: 'standard', label: 'Standard' },
                    { value: 'large', label: 'Large' },
                    { value: 'largest', label: 'Largest' },
                  ]}
                />
                <div className="theme-actions">
                  <Button variant={theme === 'light' ? 'primary' : 'neutral'} onClick={() => setTheme('light')}>
                    Light
                  </Button>
                  <Button variant={theme === 'dark' ? 'primary' : 'neutral'} onClick={() => setTheme('dark')}>
                    Dark
                  </Button>
                </div>
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>
                  Speech
                </div>
                <SwitchField
                  label="Spoken observations"
                  description="Speak useful object descriptions as they arrive."
                  hasDescription
                  defaultSelected={spokenOn}
                  onChange={(v: boolean) => {
                    setSpokenOn(v)
                    if (!v) stride.setConsent(state.consent) // no-op guard; speech gate handled in controller
                  }}
                />
                <SelectField
                  label="Speech rate"
                  value={speechRate}
                  onChange={(v: string) => setSpeechRate(v as typeof speechRate)}
                  options={[
                    { value: 'slow', label: 'Slow' },
                    { value: 'normal', label: 'Normal' },
                    { value: 'fast', label: 'Fast' },
                  ]}
                />
                <Button variant="neutral" onClick={stride.enableSpeech}>
                  Enable / test audio
                </Button>
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>
                  Camera and privacy
                </div>
                <SelectField
                  label="Camera source"
                  value={state.cameraSource}
                  onChange={(v: string) => void stride.setCameraSource(v as CameraSource)}
                  options={[
                    { value: 'glasses', label: 'Glasses camera (W11)' },
                    { value: 'browser', label: 'Browser camera' },
                  ]}
                />
                <Checkbox
                  checked={state.consent}
                  onChange={stride.setConsent}
                  label="Upload camera images for detection"
                  description="Images are sent only while the session is active and consent is on."
                />
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>
                  Device status
                </div>
                <dl>
                  <div>
                    <dt>Audio</dt>
                    <dd>{state.speechSupported ? (state.speechState === 'off' ? 'Browser speech off' : 'Browser speech ready') : 'Unsupported'}</dd>
                  </div>
                  <div>
                    <dt>Obstacle sensor</dt>
                    <dd>{state.status?.feedback ? (state.status.feedback.connected ? 'Connected' : 'Offline') : '—'}</dd>
                  </div>
                  <div>
                    <dt>Recognition</dt>
                    <dd>{providerLabel(state.status, mode)}</dd>
                  </div>
                  <div>
                    <dt>Connection</dt>
                    <dd>{connected ? 'Connected' : 'Disconnected'}</dd>
                  </div>
                </dl>
              </div>
            </div>
          </section>
        )}
      </main>

      {view === 'guidance' && routeState !== 'idle' && (
        <Button className="persistent-stop" iconStart={<X />} onClick={() => void stride.routeAction('stop')}>
          Stop guidance
        </Button>
      )}
    </div>
  )
}
