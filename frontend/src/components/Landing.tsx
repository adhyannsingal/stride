// Landing page — appearance from the updated Figma Make export (App-2):
// animated STRIDE letter stage, spectacles image, and a scroll/swipe/key "zoom"
// transition into the app. Visual design preserved verbatim; only extracted
// into this module and wired to the existing `openApp` entry point so the
// Dashboard/controller architecture is unchanged.

import { useEffect, useState } from 'react'
import { Button } from '@figma/astraui'

function Spectacles({ className = '' }: { className?: string }) {
  return (
    <div className={`spectacles ${className}`}>
      <img src="/stride-glasses.png" alt="" aria-hidden="true" />
    </div>
  )
}

function ProductIllustration({ openApp }: { openApp: () => void }) {
  return (
    <div className="product-illustration motion-stage">
      <div className="stage-word" aria-hidden="true">
        {'STRIDE'.split('').map((letter, index) => (
          <span key={`${letter}-${index}`}>{letter}</span>
        ))}
      </div>
      <Spectacles />
      <div className="stage-action">
        <Button variant="primary" onClick={openApp}>
          Open STRIDE
        </Button>
      </div>
    </div>
  )
}

export function Landing({ openApp }: { openApp: () => void }) {
  const [zooming, setZooming] = useState(false)

  const startTransition = () => {
    if (zooming) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      openApp()
      return
    }
    setZooming(true)
    window.setTimeout(openApp, 850)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <ProductIllustration openApp={startTransition} />
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
