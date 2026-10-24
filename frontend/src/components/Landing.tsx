// Landing page — appearance preserved exactly from the Figma Make export.
// Only structural extraction into its own module; no visual/markup changes.

import { Button } from '@figma/astraui'

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

export function Landing({ openApp }: { openApp: () => void }) {
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

export { Mark }
