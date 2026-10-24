// STRIDE frontend — central app controller hook.
//
// Composes StrideApi + CameraController + SpeechController + LiveController and
// exposes authoritative state to the React components. Replaces all fabricated
// prototype data: route/vision/feedback/memory come from the backend (or the
// explicitly selected Simulation fixtures), never from hardcoded UI state.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { StrideApi, type ApiMode } from './api'
import { CameraController } from './camera'
import { SpeechController, type SpeechState } from './speech'
import { LiveController } from './live'
import type { MemoryRecord, RouteActionName, StatusResponse, VisionLatest } from './types'

export type CameraSource = 'browser' | 'glasses' // glasses = W11
export type Connection = 'disconnected' | 'connected'

export interface AppState {
  mode: ApiMode
  connection: Connection
  sessionId: string | null
  status: StatusResponse | null
  vision: VisionLatest | null
  visionStale: boolean
  memory: MemoryRecord[]
  speechState: SpeechState
  speechSupported: boolean
  cameraSource: CameraSource
  consent: boolean
  cameraActive: boolean
  lastError: string | null
}

export function useStride(videoRef: React.RefObject<HTMLVideoElement | null>) {
  const [state, setState] = useState<AppState>({
    mode: 'fixture',
    connection: 'disconnected',
    sessionId: null,
    status: null,
    vision: null,
    visionStale: false,
    memory: [],
    speechState: 'off',
    speechSupported: false,
    cameraSource: 'glasses',
    consent: false,
    cameraActive: false,
    lastError: null,
  })

  const apiRef = useRef<StrideApi | null>(null)
  const speechRef = useRef<SpeechController | null>(null)
  const liveRef = useRef<LiveController | null>(null)
  const cameraRef = useRef<CameraController | null>(null)
  // Mutable mirror for the camera context getter (avoids stale closures).
  const ctxRef = useRef({ sessionId: '', deviceId: 'browser-camera-1', sourceRevision: 1, consent: false, source: 'glasses' as CameraSource })

  const patch = useCallback((p: Partial<AppState>) => setState((s) => ({ ...s, ...p })), [])

  // Lazy init of controllers (needs the video element).
  const ensure = useCallback(() => {
    if (apiRef.current) return
    const api = new StrideApi({ mode: 'fixture' })
    const speech = new SpeechController(api.clock, (s: SpeechState) => patch({ speechState: s }))
    apiRef.current = api
    speechRef.current = speech
    patch({ speechSupported: speech.supported })
    if (videoRef.current) {
      cameraRef.current = new CameraController(
        api,
        videoRef.current,
        () => ({
          sessionId: ctxRef.current.sessionId,
          deviceId: ctxRef.current.deviceId,
          sourceRevision: ctxRef.current.sourceRevision,
          consent: ctxRef.current.consent,
        }),
        (e) => patch({ lastError: e.message }),
      )
    }
    liveRef.current = new LiveController(api, speech, {
      onStatus: (s) => {
        ctxRef.current.sourceRevision = s.camera?.source_revision ?? ctxRef.current.sourceRevision
        patch({ status: s })
      },
      onVision: (v, stale) => patch({ vision: v, visionStale: stale }),
      onConnection: (c) => patch({ connection: c ? 'connected' : 'disconnected' }),
    })
  }, [patch, videoRef])

  const setMode = useCallback(
    (mode: ApiMode, baseUrl = '') => {
      ensure()
      apiRef.current!.setMode(mode)
      apiRef.current!.baseUrl = baseUrl.replace(/\/$/, '')
      patch({ mode })
    },
    [ensure, patch],
  )

  const connect = useCallback(
    async (opts: { accessCode?: string; sessionId?: string; mode: ApiMode; baseUrl?: string }) => {
      ensure()
      const api = apiRef.current!
      api.setMode(opts.mode)
      api.baseUrl = (opts.baseUrl ?? '').replace(/\/$/, '')
      patch({ mode: opts.mode, lastError: null })
      try {
        await api.health()
        if (opts.accessCode !== undefined) await api.auth(opts.accessCode)
        await api.syncClock()
        let sessionId = opts.sessionId?.trim() || ''
        let sourceRevision = ctxRef.current.sourceRevision
        if (!sessionId) {
          const session = await api.createSession('training', 'browser_camera')
          sessionId = session.session_id
          sourceRevision = session.source_revision ?? 1
        }
        ctxRef.current.sessionId = sessionId
        ctxRef.current.sourceRevision = sourceRevision
        const mem = await api.memory(sessionId, 'sightings')
        patch({ sessionId, connection: 'connected', memory: mem.records ?? [] })
        liveRef.current!.start(sessionId, sourceRevision)
      } catch (e) {
        patch({ connection: 'disconnected', lastError: (e as Error).message })
        throw e
      }
    },
    [ensure, patch],
  )

  const enableSpeech = useCallback(() => {
    ensure()
    speechRef.current!.enable()
  }, [ensure])

  const setSpeechRate = useCallback((rate: number) => {
    speechRef.current?.setRate(rate)
  }, [])

  const setConsent = useCallback(
    (consent: boolean) => {
      ctxRef.current.consent = consent
      patch({ consent })
      if (!consent) {
        // Revocation stops uploads and invalidates pending visual output.
        cameraRef.current?.revokeConsent()
        speechRef.current?.clear()
        patch({ vision: null, visionStale: true, cameraActive: false })
      }
    },
    [patch],
  )

  const setCameraSource = useCallback(
    async (source: CameraSource) => {
      ctxRef.current.source = source
      patch({ cameraSource: source })
      // Glasses (W11) must not activate the phone camera: release any stream.
      if (source === 'glasses') {
        cameraRef.current?.stop()
        patch({ cameraActive: false })
      }
    },
    [patch],
  )

  const useThisDeviceCamera = useCallback(
    async (deviceId?: string) => {
      ensure()
      if (ctxRef.current.source !== 'browser') {
        patch({ lastError: 'Select Browser camera before enabling this device.' })
        return
      }
      if (!ctxRef.current.consent) {
        patch({ lastError: 'Consent is required before enabling the camera.' })
        return
      }
      try {
        const info = await cameraRef.current!.enableProducer(deviceId)
        ctxRef.current.deviceId = info.deviceId || 'browser-camera-1'
        if (!apiRef.current!.isFixture && ctxRef.current.sessionId) {
          const sel = await apiRef.current!.selectCamera(ctxRef.current.sessionId, 'browser_camera', info.deviceId || undefined)
          ctxRef.current.sourceRevision = sel.source_revision ?? ctxRef.current.sourceRevision
        }
        patch({ cameraActive: true, lastError: null })
      } catch (e) {
        patch({ lastError: (e as Error).message })
      }
    },
    [ensure, patch],
  )

  const startGuidance = useCallback(async () => {
    const api = apiRef.current!
    const live = liveRef.current!
    const sid = ctxRef.current.sessionId
    try {
      await api.visionControl(sid, 'start')
      live.setVisionActive(true)
      patch({ vision: null, visionStale: false })
      // Only the browser-camera producer uploads; glasses mode consumes W11.
      if (ctxRef.current.source === 'browser' && ctxRef.current.consent && cameraRef.current?.stream) {
        cameraRef.current.start()
        patch({ cameraActive: true })
      }
      const r = await api.routeAction(sid, 'start')
      if (r.speech_event) speechRef.current!.offer(r.speech_event)
      patch({ status: r })
    } catch (e) {
      patch({ lastError: (e as Error).message })
    }
  }, [patch])

  const routeAction = useCallback(
    async (action: RouteActionName) => {
      const api = apiRef.current!
      const live = liveRef.current!
      const sid = ctxRef.current.sessionId
      try {
        const r = await api.routeAction(sid, action)
        if (r.speech_event) speechRef.current!.offer(r.speech_event)
        patch({ status: r })
        if (action === 'stop') {
          live.setVisionActive(false)
          await api.visionControl(sid, 'stop')
          cameraRef.current?.pause()
          speechRef.current?.clear()
          patch({ cameraActive: false })
        } else if (action === 'pause') {
          live.setVisionActive(false)
          await api.visionControl(sid, 'pause')
          cameraRef.current?.pause()
        } else if (action === 'resume') {
          live.setVisionActive(true)
          await api.visionControl(sid, 'resume')
          if (ctxRef.current.source === 'browser' && ctxRef.current.consent && cameraRef.current?.stream) {
            cameraRef.current.start()
          }
        }
      } catch (e) {
        patch({ lastError: (e as Error).message })
      }
    },
    [patch],
  )

  const find = useCallback(
    async (target: string): Promise<string> => {
      const api = apiRef.current!
      const sid = ctxRef.current.sessionId
      const res = await api.perception(sid, 'find-' + Date.now(), 'find', target)
      if (res.status === 'ok' && res.speakable && res.speech_event) speechRef.current!.offer(res.speech_event)
      return res.status
    },
    [],
  )

  const refreshMemory = useCallback(async () => {
    const api = apiRef.current
    const sid = ctxRef.current.sessionId
    if (!api || !sid) return
    const mem = await api.memory(sid, 'sightings')
    patch({ memory: mem.records ?? [] })
  }, [patch])

  // Page hide: stop this client's speech; pause capture if we are the producer.
  useEffect(() => {
    const onHide = () => {
      if (document.hidden) {
        speechRef.current?.clear()
        if (ctxRef.current.source === 'browser') cameraRef.current?.pause()
      }
    }
    document.addEventListener('visibilitychange', onHide)
    return () => document.removeEventListener('visibilitychange', onHide)
  }, [])

  return useMemo(
    () => ({
      state,
      setMode,
      connect,
      enableSpeech,
      setSpeechRate,
      setConsent,
      setCameraSource,
      useThisDeviceCamera,
      startGuidance,
      routeAction,
      find,
      refreshMemory,
    }),
    [state, setMode, connect, enableSpeech, setSpeechRate, setConsent, setCameraSource, useThisDeviceCamera, startGuidance, routeAction, find, refreshMemory],
  )
}
