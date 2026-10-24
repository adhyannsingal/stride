import { strideApi } from './api'

export class SpeechController {
  private enabled = false
  private spoken = new Set<string>()
  rate = 1
  observations = true

  available() {
    return 'speechSynthesis' in window
  }

  enable() {
    this.enabled = this.available()
    return this.enabled
  }

  status() {
    return !this.available() ? 'Browser speech unavailable' : this.enabled ? 'Browser speech enabled' : 'Browser speech off'
  }

  speak(id: string, text: string, kind: 'route' | 'observation' | 'urgent' = 'route') {
    if (!this.enabled || this.spoken.has(id) || (kind === 'observation' && !this.observations)) return
    this.spoken.add(id)
    if (kind === 'urgent') speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = this.rate
    speechSynthesis.speak(utterance)
  }

  cancel() {
    if (this.available()) speechSynthesis.cancel()
  }
}

export class BrowserCameraController {
  private stream: MediaStream | null = null
  private timer: number | null = null
  private sequence = 0
  private bootId = crypto.randomUUID()

  async start(video: HTMLVideoElement, sessionId: string, onError: (message: string) => void) {
    this.stop()
    this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    video.srcObject = this.stream
    await video.play()
    const send = async () => {
      if (!this.stream || video.readyState < 2) return
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      canvas.getContext('2d')?.drawImage(video, 0, 0)
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.78))
      if (!blob || !this.stream) return
      const form = new FormData()
      form.append('file', blob, 'frame.jpg')
      form.append('session_id', sessionId)
      form.append('device_id', 'browser-camera')
      form.append('boot_id', this.bootId)
      form.append('frame_id', crypto.randomUUID())
      form.append('sequence', String(++this.sequence))
      form.append('captured_ms', String(Date.now()))
      form.append('source', 'real')
      form.append('origin', 'browser_camera')
      form.append('source_revision', '0')
      try {
        await strideApi.uploadFrame(form)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Frame upload failed')
      }
    }
    this.timer = window.setInterval(send, 500)
    await send()
  }

  stop() {
    if (this.timer !== null) window.clearInterval(this.timer)
    this.timer = null
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
  }
}
