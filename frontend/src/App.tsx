import { useState } from 'react'
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

function ProductIllustration() {
  return (
    <div className="product-illustration" role="img" aria-label="Diagram showing glasses sending a view ahead to a phone, which provides spoken guidance">
      <div className="diagram-label label-one">GLASSES CAMERA</div>
      <div className="glasses" aria-hidden="true">
        <span />
        <i />
        <span />
      </div>
      <div className="signal-line" aria-hidden="true">
        <b />
        <b />
        <b />
      </div>
      <div className="phone-preview">
        <div className="preview-top">Route active</div>
        <div className="preview-turn">Continue for 20 metres</div>
        <div className="preview-note">Bench ahead, slightly right</div>
      </div>
      <div className="audio-wave" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="diagram-label label-two">SPOKEN THROUGH AIRPODS</div>
    </div>
  )
}

function Landing({ openApp }: { openApp: () => void }) {
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  return (
    <div className="landing">
      <Button className="skip-link" onClick={() => document.getElementById('main-content')?.focus()}>
        Skip to content
      </Button>
      <nav className="topbar" aria-label="Public navigation">
        <Mark />
        <div className="nav-links">
          <Button variant="subtle" onClick={() => scrollTo('how')}>
            How it works
          </Button>
          <Button variant="subtle" onClick={() => scrollTo('accessibility')}>
            Accessibility
          </Button>
          <Button variant="primary" onClick={openApp}>
            Open STRIDE
          </Button>
        </div>
      </nav>

      <main id="main-content" tabIndex={-1}>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow">Wearable navigation assistance</div>
            <div id="hero-title" role="heading" aria-level={1} className="display-title">
              Your next step. <em>Clearly communicated.</em>
            </div>
            <p className="hero-lede">
              Spoken guidance, nearby-obstacle alerts and awareness of what’s ahead—connected through a wearable prototype.
            </p>
            <div className="button-row">
              <Button variant="primary" onClick={openApp}>
                Open STRIDE
              </Button>
              <Button variant="neutral" onClick={() => scrollTo('how')}>
                How it works
              </Button>
            </div>
          </div>
          <ProductIllustration />
        </section>

        <section id="how" className="dark-section" aria-labelledby="how-title">
          <div className="section-intro">
            <div className="eyebrow">A connected loop</div>
            <div id="how-title" role="heading" aria-level={2} className="section-title">
              Awareness without taking over.
            </div>
          </div>
          <div className="steps">
            {[
              ['01', 'Glasses see', 'A continuous camera feed shares the view ahead—with your consent.'],
              ['02', 'Detector checks', 'Hosted recognition describes useful objects. A separate sensor handles local obstacle alerts.'],
              ['03', 'You hear', 'The phone speaks concise observations and instructions for a route checked in advance.'],
            ].map(([n, title, copy]) => (
              <article className="step" key={n}>
                <span>{n}</span>
                <div role="heading" aria-level={3}>{title}</div>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="capabilities" aria-labelledby="capabilities-title">
          <div className="section-intro">
            <div className="eyebrow">Designed for useful moments</div>
            <div id="capabilities-title" role="heading" aria-level={2} className="section-title">
              Guidance, context and recall.
            </div>
          </div>
          <div className="capability-grid">
            {[
              ['Checked-route guidance', 'Clear checkpoint-based instructions for a route someone has reviewed.'],
              ['Objects ahead', 'Short, image-relative descriptions that support—not replace—your own judgment.'],
              ['Recent sightings', 'Search where an object was last seen, with age, source and route context.'],
            ].map(([title, copy], index) => (
              <article className="capability" key={title}>
                <span className="cap-number">0{index + 1}</span>
                <div role="heading" aria-level={3}>{title}</div>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="accessibility" className="access-section" aria-labelledby="access-title">
          <div>
            <div className="eyebrow">Your preferences, retained</div>
            <div id="access-title" role="heading" aria-level={2} className="section-title">
              Built around clear choices.
            </div>
            <p className="section-copy">
              Large controls, spoken feedback, adjustable text and deliberate light and dark appearances keep the interface adaptable.
            </p>
          </div>
          <div className="control-sample" aria-label="Example accessible controls">
            <span>Current instruction</span>
            <strong>Continue straight for 20 metres.</strong>
            <Button variant="primary">Repeat instruction</Button>
          </div>
        </section>

        <section className="limitations" aria-labelledby="limits-title">
          <div id="limits-title" role="heading" aria-level={2}>A prototype, with clear limits.</div>
          <p>
            STRIDE can miss, misidentify or delay observations. It does not replace a mobility aid, trained assistance or your own judgment.
            Camera images are uploaded only after explicit consent; this demo uses preview data and stores no camera feed.
          </p>
        </section>
      </main>
      <footer>
        <Mark />
        <p>Navigation assistance, shaped around agency.</p>
        <span>Prototype · 2025</span>
      </footer>
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
  return page === 'landing' ? <Landing openApp={() => setPage('guidance')} /> : <Dashboard exit={() => setPage('landing')} />
}

export default function App() {
  return <ThemeProvider><AppContent /></ThemeProvider>
}
