import { useEffect, useState } from 'react'
import {
  Button,
  Checkbox,
  InputField,
  SelectField,
  SwitchField,
  ThemeProvider,
  useTheme,
  Home,
  Search,
  Settings as SettingsIcon,
  Play,
  X,
} from '@figma/astraui'
import StrideApp from './app/StrideApp'

type View = 'landing' | 'guidance' | 'memory' | 'settings'
type GuidanceState = 'idle' | 'active' | 'paused' | 'blocked'

function Mark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-mark" aria-label="STRIDE">
      <span className="brand-symbol" aria-hidden="true">
        S
      </span>
      {!compact && <span>STRIDE</span>}
    </div>
  )
}

function Spectacles({ className = '' }: { className?: string }) {
  return (
    <div className={`spectacles ${className}`}>
      <img src="/stride-glasses.png" alt="" aria-hidden="true" />
    </div>
  )
}

function ProductIllustration() {
  return (
    <div className="product-illustration motion-stage">
      <div className="stage-word" aria-hidden="true">
        {'STRIDE'.split('').map((letter, index) => <span key={`${letter}-${index}`}>{letter}</span>)}
      </div>
      <Spectacles />
    </div>
  )
}

function Landing({ enterApp }: { enterApp: () => void }) {
  const [zooming, setZooming] = useState(false)

  const startTransition = () => {
    if (zooming) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      enterApp()
      return
    }
    setZooming(true)
    window.setTimeout(enterApp, 850)
  }

  useEffect(() => {
    let touchStart = 0
    let triggered = false
    const trigger = () => {
      if (triggered) return
      triggered = true
      startTransition()
    }
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY > 28) trigger()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (['ArrowDown', 'PageDown'].includes(event.key)) trigger()
    }
    const onTouchStart = (event: TouchEvent) => {
      touchStart = event.touches[0]?.clientY ?? 0
    }
    const onTouchEnd = (event: TouchEvent) => {
      const touchEnd = event.changedTouches[0]?.clientY ?? touchStart
      if (touchStart - touchEnd > 48) trigger()
    }
    window.addEventListener('wheel', onWheel, { passive: true })
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchend', onTouchEnd, { passive: true })
    return () => {
      window.removeEventListener('wheel', onWheel)
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchend', onTouchEnd)
    }
  }, [zooming])

  return (
    <div className={`landing ${zooming ? 'is-zooming' : ''}`}>
      <Button className="skip-link" onClick={() => document.getElementById('main-content')?.focus()}>
        Skip to content
      </Button>
      <nav className="topbar" aria-label="Public navigation">
        <div className="nav-links">
          <Button variant="primary" onClick={startTransition}>
            Open STRIDE
          </Button>
        </div>
      </nav>

      <main id="main-content" tabIndex={-1}>
        <section className="hero" aria-labelledby="hero-title">
          <ProductIllustration />
          <div className="hero-copy">
            <div id="hero-title" role="heading" aria-level={1} className="display-title">
              Your next step. <em>Clearly communicated.</em>
            </div>
            <p className="hero-lede">
              Spoken guidance, nearby-obstacle alerts and awareness of what’s ahead—connected through a wearable prototype.
            </p>
          </div>
        </section>
      </main>
    </div>
  )
}

function CameraPreview({ stale }: { stale: boolean }) {
  return (
    <div className="camera-wrap">
      <div className="camera-head">
        <div>
          <span className={`status-dot ${stale ? 'warning-dot' : ''}`} />
          <strong>{stale ? 'Vision stale · 18s ago' : 'Fresh · just now'}</strong>
        </div>
        <span>Glasses camera</span>
      </div>
      <div className="camera-view" role="img" aria-label="Demo camera preview showing a bench and doorway with labeled bounding boxes">
        <div className="horizon" />
        <div className="box bench-box"><span>bench · ahead right</span></div>
        <div className="box door-box"><span>doorway · ahead</span></div>
        <div className="demo-stamp">DEMO PREVIEW</div>
      </div>
    </div>
  )
}

function Dashboard({ exit }: { exit: () => void }) {
  const [view, setView] = useState<View>('guidance')
  const [state, setState] = useState<GuidanceState>('idle')
  const [awareness, setAwareness] = useState(false)
  const [preview, setPreview] = useState(false)
  const [consent, setConsent] = useState(false)
  const [search, setSearch] = useState('')
  const [camera, setCamera] = useState('glasses')
  const { theme, setTheme } = useTheme()

  const start = () => {
    setState('active')
    setAwareness(true)
  }

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
        <Button variant="subtle" onClick={exit}>Exit</Button>
      </nav>

      <main className="dashboard-main">
        {view === 'guidance' && (
          <>
            <header className="dashboard-header">
              <div>
                <div className="eyebrow">Good afternoon</div>
                <div role="heading" aria-level={1} className="dash-title">Guidance</div>
              </div>
              <div className="device-summary"><span className="status-dot" /> AirPods connected</div>
            </header>

            {state === 'blocked' && (
              <div className="urgent-banner" role="alert">
                <X aria-hidden="true" />
                <div><strong>Stop. Obstacle very close ahead.</strong><span>Route instructions and ordinary observations are paused.</span></div>
              </div>
            )}

            <div className="dashboard-grid">
              <section className="guidance-panel" aria-labelledby="current-guidance">
                {state === 'idle' ? (
                  <div className="setup-flow">
                    <div className="panel-kicker">SETUP · 4 STEPS</div>
                    <div id="current-guidance" role="heading" aria-level={2} className="instruction">
                      Get ready for guidance.
                    </div>
                    <div className="setup-list">
                      <div className="setup-row"><span>1</span><div><strong>Audio</strong><p>AirPods connected and ready.</p></div><Button variant="neutral">Test audio</Button></div>
                      <div className="setup-row"><span>2</span><div className="grow"><SelectField label="Camera source" value={camera} onChange={setCamera} options={[{ value: 'glasses', label: 'Glasses camera' }, { value: 'browser', label: 'Browser camera' }]} /></div></div>
                      <div className="setup-row"><span>3</span><div className="grow"><Checkbox checked={consent} onChange={setConsent} label="I consent to uploading camera images during this session" description="Required for hosted detection. You can withdraw consent at any time." /></div></div>
                      <div className="setup-row"><span>4</span><div className="grow"><SelectField label="Manually checked route" value="library" onChange={() => {}} options={[{ value: 'library', label: 'Station entrance → Library desk' }, { value: 'cafe', label: 'North gate → Café counter' }]} /></div></div>
                    </div>
                    <Button variant="primary" iconStart={<Play />} disabled={!consent} onClick={start}>Start guidance</Button>
                  </div>
                ) : (
                  <div className="active-guidance">
                    <div className="route-row"><div><span>Current route</span><strong>Station entrance → Library desk</strong></div><span className={`state-label ${state}`}>{state}</span></div>
                    <div id="current-guidance" role="heading" aria-level={2} className="instruction">
                      {state === 'blocked' ? 'Stop and check your surroundings.' : state === 'paused' ? 'Guidance is paused.' : 'Continue straight for 20 metres.'}
                    </div>
                    <div className="checkpoint-grid">
                      <div><span>Last confirmed</span><strong>Station ticket gates</strong></div>
                      <div><span>Next checkpoint</span><strong>Library entrance doors</strong></div>
                    </div>
                    <div className="button-row action-row">
                      <Button variant="primary">Confirm arrival</Button>
                      <Button variant="neutral">Repeat instruction</Button>
                      <Button variant="neutral" onClick={() => setState(state === 'paused' ? 'active' : 'paused')}>{state === 'paused' ? 'Resume' : 'Pause'}</Button>
                    </div>
                    <Button className="simulate" variant="subtle" onClick={() => setState(state === 'blocked' ? 'active' : 'blocked')}>Demo obstacle state</Button>
                  </div>
                )}
              </section>

              <aside className="awareness-panel" aria-labelledby="awareness-title">
                <div className="panel-heading">
                  <div><div className="panel-kicker">LIVE AWARENESS</div><div id="awareness-title" role="heading" aria-level={2}>What’s ahead</div></div>
                  <span className="demo-label">Demo adapter</span>
                </div>
                {!awareness ? (
                  <div className="empty-awareness"><p>Continuous detection is off.</p><span>Start once to receive ongoing, concise observations.</span><Button variant="primary" onClick={() => setAwareness(true)}>Start awareness</Button></div>
                ) : (
                  <>
                    <div className="observation"><span className="status-dot" /><p><strong>Bench ahead, slightly right.</strong> Doorway about 8 metres ahead.</p></div>
                    <Button variant="neutral" onClick={() => setPreview(!preview)}>{preview ? 'Hide camera preview' : 'Show camera preview'}</Button>
                    {preview && <CameraPreview stale={state === 'paused'} />}
                  </>
                )}
                <details>
                  <summary>Device details</summary>
                  <dl><div><dt>Camera</dt><dd>{camera === 'glasses' ? 'Glasses camera' : 'Browser camera'}</dd></div><div><dt>Sensor</dt><dd>Connected · local alerts</dd></div><div><dt>Detector</dt><dd>Demo adapter · available</dd></div></dl>
                </details>
              </aside>
            </div>
          </>
        )}

        {view === 'memory' && (
          <section className="subpage">
            <div className="eyebrow">Historical sightings</div>
            <div role="heading" aria-level={1} className="dash-title">Memory</div>
            <p className="page-lede">Search recent object labels. These records are not current detections.</p>
            <div className="content-surface">
              <InputField label="Search an object label" placeholder="Try “bench” or “doorway”" value={search} onChange={setSearch} prefix={<Search />} />
              {search.toLowerCase().includes('unknown') ? (
                <div className="empty-result"><strong>No saved sightings</strong><p>Try another object label. Current detections appear in Guidance.</p></div>
              ) : (
                <div className="sighting"><div><span>HISTORICAL SIGHTING</span><strong>{search || 'Bench'}</strong></div><div><span>Last seen</span><strong>4 minutes ago</strong></div><div><span>Source</span><strong>Glasses camera</strong></div><div><span>Checkpoint context</span><strong>After station ticket gates</strong></div></div>
              )}
            </div>
          </section>
        )}

        {view === 'settings' && (
          <section className="subpage">
            <div className="eyebrow">Personal preferences</div>
            <div role="heading" aria-level={1} className="dash-title">Settings</div>
            <p className="page-lede">Choose how STRIDE looks, speaks and connects.</p>
            <div className="settings-grid">
              <div className="content-surface">
                <div role="heading" aria-level={2}>Appearance</div>
                <SelectField label="Text size" value="large" onChange={() => {}} options={[{ value: 'standard', label: 'Standard' }, { value: 'large', label: 'Large' }, { value: 'largest', label: 'Largest' }]} />
                <div className="theme-actions"><Button variant={theme === 'light' ? 'primary' : 'neutral'} onClick={() => setTheme('light')}>Light</Button><Button variant={theme === 'dark' ? 'primary' : 'neutral'} onClick={() => setTheme('dark')}>Dark</Button></div>
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>Speech</div>
                <SwitchField label="Spoken observations" description="Speak useful object descriptions as they arrive." hasDescription defaultSelected />
                <SelectField label="Speech rate" value="normal" onChange={() => {}} options={[{ value: 'slow', label: 'Slow' }, { value: 'normal', label: 'Normal' }, { value: 'fast', label: 'Fast' }]} />
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>Camera and privacy</div>
                <SelectField label="Camera source" value={camera} onChange={setCamera} options={[{ value: 'glasses', label: 'Glasses camera' }, { value: 'browser', label: 'Browser camera' }]} />
                <Checkbox checked={consent} onChange={setConsent} label="Upload camera images for detection" description="Images are sent only while the session is active." />
              </div>
              <div className="content-surface">
                <div role="heading" aria-level={2}>Device status</div>
                <dl><div><dt>Audio</dt><dd>Connected</dd></div><div><dt>Obstacle sensor</dt><dd>Connected</dd></div><div><dt>Recognition</dt><dd>Demo adapter available</dd></div></dl>
              </div>
            </div>
          </section>
        )}
      </main>

      {view === 'guidance' && state !== 'idle' && (
        <Button className="persistent-stop" iconStart={<X />} onClick={() => { setState('idle'); setAwareness(false) }}>Stop guidance</Button>
      )}
    </div>
  )
}

function AppContent() {
  const [page, setPage] = useState<View>('landing')

  return (
    <>
      {page === 'landing' ? (
        <Landing enterApp={() => setPage('guidance')} />
      ) : (
        <StrideApp exit={() => setPage('landing')} />
      )}
    </>
  )
}

export default function App() {
  return <ThemeProvider><AppContent /></ThemeProvider>
}
