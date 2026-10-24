// STRIDE frontend — shared contract types.
//
// Mirrors contracts/API.md and contracts/examples.json. snake_case field names
// match the backend exactly; do not rename without a contract change.

export type CameraOrigin =
  | 'browser_camera'
  | 'w11_camera'
  | 'devkit'
  | 'simulator'
  | 'fixture'

export type SourceKind = 'real' | 'simulated' | 'fixture'

export type RouteState = 'idle' | 'guiding' | 'paused' | 'blocked' | 'completed'

export type VisionStatus = 'live' | 'stale' | 'paused' | 'unavailable'

export type SpeechPriority = 'urgent' | 'obstacle' | 'stop' | 'fault' | 'route' | 'observation'

export interface SpeechEvent {
  event_id: string
  kind: string
  priority: SpeechPriority
  text: string
  created_ms: number
  expires_ms?: number
  age_ms?: number
}

export interface RouteStep {
  checkpoint_id: string
  instruction: string
  pattern: string
}

export interface RouteDefinition {
  route_id: string
  name: string
  is_demo?: boolean
  steps: RouteStep[]
  return_steps?: RouteStep[]
}

export interface RouteStatus {
  route_id: string | null
  state: RouteState
  checkpoint_index: number | null
  checkpoint_id: string | null
  instruction: string | null
  pattern: string
  overlay?: string
}

export interface DetectedObject {
  track_id: string
  label: string
  score: number
  box: [number, number, number, number] // xyxy normalized 0..1
  position: string
}

export interface VisionLatest {
  session_id: string
  state_seq: number
  server_time_ms: number
  frame_id?: string
  captured_ms?: number
  completed_ms?: number
  age_ms?: number
  source_revision: number
  origin: CameraOrigin
  source: SourceKind
  status: VisionStatus
  provider: string
  result_hz: number
  objects: DetectedObject[]
  speech_event: SpeechEvent | null
}

export interface CameraStatus {
  origin: CameraOrigin
  source: SourceKind
  connected: boolean
  age_ms: number
  source_revision?: number
  device_id?: string
}

export interface FeedbackStatus {
  origin: string
  source: SourceKind
  connected: boolean
  valid: boolean
  distance_cm: number | null
  age_ms: number
  alert: 'none' | 'warning' | 'urgent' | 'sensor_fault'
  ack_state: string
}

export interface PerceptionStatus {
  provider: string
  available: boolean
  busy: boolean
  latest: unknown
}

export interface StatusResponse {
  session_id: string
  state_seq: number
  server_time_ms: number
  mode: string
  route: RouteStatus
  camera: CameraStatus
  feedback: FeedbackStatus
  perception: PerceptionStatus
  vision?: { status: VisionStatus; age_ms: number | null; result_hz: number }
  speech_event: SpeechEvent | null
  haptic_event: unknown
  memory: { durability: string; export_available: boolean }
}

export interface MemoryRecord {
  kind: string
  label: string
  source: SourceKind
  age_ms: number
  checkpoint_id: string | null
  captured_ms: number
}

export interface SessionResponse {
  session_id: string
  mode: string
  source: SourceKind
  origin: CameraOrigin
  source_revision: number
  state_seq: number
  server_time_ms: number
}

export type RouteActionName = 'start' | 'confirm' | 'repeat' | 'pause' | 'resume' | 'stop'
export type VisionActionName = 'start' | 'pause' | 'resume' | 'stop'
