export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'unauthorized' | 'error'
export type NavigationState = 'idle' | 'guiding' | 'paused' | 'blocked' | 'completed'
export type ObstacleState = 'clear' | 'caution' | 'danger' | 'unknown'

export interface Checkpoint {
  checkpoint_id: string
  ordinal: number
  instruction: string
  direction: 'left' | 'right' | 'straight' | 'stop'
  landmark: string | null
}

export interface SavedRoute {
  route_id: string
  name: string
  description: string
  checked: boolean
  demo_fixture: boolean
  verification_note: string | null
  checkpoints: Checkpoint[]
}

export interface GuidanceEvent {
  event_id: string
  navigation_id: string
  instruction: string
  created_at: number
  expires_at: number
  state_revision: number
  valid: boolean
}

export interface CheckpointRef {
  checkpoint_id: string
  ordinal: number
  landmark: string | null
}

export interface NavigationProgress {
  navigation_id: string
  route_id: string
  state: NavigationState
  state_revision: number
  current_checkpoint: CheckpointRef | null
  confirmed_checkpoint_count: number
  total_checkpoints: number
  confirmed_checkpoints: CheckpointRef[]
  instruction: string | null
  guidance_event: GuidanceEvent | null
  status_message: string
  sensor_monitoring: 'not_associated' | 'unknown' | 'fresh_measurement'
  paired_device_id: string | null
  obstacle_state: ObstacleState | null
}

export interface HapticCommand {
  command_id: string
  kind: string
  status: 'issued' | 'delivered' | 'received' | 'executed' | 'rejected' | 'expired' | 'canceled'
  created_at: number
  execution_reported: boolean
  perception_verified: false
}

export interface DeviceStatus {
  measurement_timeout_ms?: number
  heartbeat_timeout_ms?: number
  device_id: string
  session_id: string | null
  paired: boolean
  availability: 'unknown' | 'connected' | 'stale'
  telemetry_age_ms: number | null
  telemetry_fresh: boolean
  measurement_fresh: boolean
  sensor_valid: boolean
  measurement_reason: string | null
  current_distance_cm: number | null
  last_reported_distance_cm: number | null
  last_valid_distance_cm: number | null
  last_valid_distance_age_ms: number | null
  obstacle_state: ObstacleState
  source: 'real' | 'simulated' | 'fixture' | null
  battery_percent: number | null
  firmware_version: string | null
  recovery_clear_count: number
  recovery_required: number
  navigation_state: string | null
  navigation_revision: number | null
  pending_commands: number
  latest_command: HapticCommand | null
  last_acknowledged_command_id: string | null
  local_alerts_verified: false
}

export interface VisionObject {
  track_id?: string | null
  label: string
  score: number
  bbox: [number, number, number, number]
  position: 'left' | 'center' | 'right'
}

export interface VisionLatest {
  delivered_ms?: number
  freshness_basis?: 'server_receipt' | 'aligned_capture'
  camera_clock_aligned?: boolean
  result_hz?: number
  state: 'idle' | 'active' | 'paused' | 'stopped'
  status: 'live' | 'stale' | 'paused' | 'unavailable'
  generation: number
  state_seq: number
  source_revision: number
  detector_configured: boolean
  source: 'real' | 'simulated' | 'fixture' | null
  origin: string | null
  device_id: string | null
  frame_id: string | null
  age_ms: number | null
  objects: VisionObject[]
  speech_event: {
    event_id: string
    text: string
    generation: number
    source_revision: number
  } | null
  last_inference_error: string | null
}

export interface Sighting {
  sighting_id: string
  label: string
  checkpoint_id: string | null
  checkpoint_association: 'last_user_confirmed' | null
  source: 'real' | 'simulated' | 'fixture'
  provider: 'yolo' | 'gemini' | 'fixture'
  age_ms: number
  last_seen_at: number
}

export interface MemoryResponse {
  routes: SavedRoute[]
  navigation: NavigationProgress | null
  previous_navigation: NavigationProgress[]
  sightings: Sighting[]
  returned_at: number
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

const API_BASE = (import.meta.env?.VITE_STRIDE_API_URL || '').replace(/\/$/, '')

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(8000)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    cache: 'no-store',
    signal,
    headers: {
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init.headers,
    },
  })
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string } } = {}
    try {
      body = await response.json()
    } catch {
      // Keep the transport-safe fallback below.
    }
    throw new ApiError(response.status, body.error?.code || 'request_failed', body.error?.message || `Request failed (${response.status})`)
  }
  return response.json()
}

export const strideApi = {
  health: (signal?: AbortSignal) => request<{status: 'ok'}>('/health', {signal}),
  time: (signal?: AbortSignal) => request<{server_ms: number}>('/time', {signal}),
  connect: (session_id: string, session_token: string, signal?: AbortSignal) =>
    request<{ session_id: string; expires_ms: number }>('/auth/session', {
      method: 'POST', signal,
      body: JSON.stringify({ session_id, session_token }),
    }),

  routes: (sessionId: string, signal?: AbortSignal) =>
    request<{ routes: SavedRoute[] }>(`/routes?session_id=${encodeURIComponent(sessionId)}`, {signal}),

  routeAction: (
    sessionId: string,
    actionId: string,
    action: 'start' | 'confirm' | 'repeat' | 'pause' | 'resume' | 'stop',
    routeId?: string,
    navigation?: NavigationProgress,
    signal?: AbortSignal,
  ) =>
    request<NavigationProgress & { action_id: string; duplicate: boolean; applied_revision: number }>('/route', {
      method: 'POST', signal,
      body: JSON.stringify({
        session_id: sessionId,
        action_id: actionId,
        action,
        ...(action === 'start'
          ? {
              route_id: routeId,
              ...(navigation
                ? { navigation_id: navigation.navigation_id, expected_revision: navigation.state_revision }
                : {}),
            }
          : { navigation_id: navigation?.navigation_id, expected_revision: navigation?.state_revision }),
      }),
    }),

  memory: (sessionId: string, signal?: AbortSignal) =>
    request<MemoryResponse>(`/memory?session_id=${encodeURIComponent(sessionId)}&limit=100`, {signal}),

  pairDevice: (deviceId: string, sessionId: string, signal?: AbortSignal) =>
    request<{ device_id: string; session_id: string; paired: boolean; duplicate: boolean }>('/device/pair', {
      method: 'POST', signal,
      body: JSON.stringify({ device_id: deviceId, session_id: sessionId }),
    }),

  deviceStatus: (deviceId: string, sessionId: string, signal?: AbortSignal) =>
    request<DeviceStatus>(`/device/status?device_id=${encodeURIComponent(deviceId)}&session_id=${encodeURIComponent(sessionId)}`, {signal}),

  visionAction: (
    sessionId: string,
    actionId: string,
    action: 'start' | 'pause' | 'resume' | 'stop',
    expectedGeneration?: number,
    signal?: AbortSignal,
  ) =>
    request<{ generation: number; state_seq: number; status: VisionLatest['status'] }>('/vision', {
      method: 'POST', signal,
      body: JSON.stringify({
        session_id: sessionId,
        action_id: actionId,
        action,
        ...(expectedGeneration === undefined ? {} : { expected_generation: expectedGeneration }),
      }),
    }),

  visionLatest: (sessionId: string, signal?: AbortSignal) =>
    request<VisionLatest>(`/vision/latest?session_id=${encodeURIComponent(sessionId)}`, {signal}),

  uploadFrame: (data: FormData, signal?: AbortSignal) => request<{ received_ms: number; replaced_pending: boolean }>('/frame', { method: 'POST', body: data, signal }),
}

export const newActionId = () => crypto.randomUUID()

export function explainError(cause: unknown): string {
  if (!(cause instanceof ApiError)) return cause instanceof Error ? cause.message : 'Connection failed. Check the backend and retry.'
  const hints: Record<number, string> = {
    401: 'Reconnect with your session credentials.', 403: 'Check the session and allowed controller with the operator.',
    409: 'Refresh the current state before trying again.', 413: 'Reduce the JPEG size.',
    415: 'A multipart JPEG is required.', 422: 'Check the request fields.',
    429: 'Capacity reached. Wait before retrying.', 503: 'Ask the operator to check service configuration.',
  }
  return `${cause.message} ${hints[cause.status] || 'Please retry.'}`
}
