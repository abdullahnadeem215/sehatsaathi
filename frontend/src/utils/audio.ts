/**
 * Audio Utilities:
 * - 100% Free Web Audio API Emergency Siren
 * - Text-to-Speech (Web Speech API) with adjustable speed
 * - Speech Audio Recording via MediaRecorder to Base64
 */

let activeSirenStop: (() => void) | null = null

/**
 * Plays an oscillating emergency ambulance siren using the client Web Audio API.
 * Alternates between 750Hz and 1150Hz. Triggers phone vibration.
 * Zero cost, no external MP3 dependencies.
 */
export function playEmergencySiren(): () => void {
  // If an existing siren is running, stop it first
  if (activeSirenStop) {
    try {
      activeSirenStop()
    } catch (e) {}
    activeSirenStop = null
  }

  try {
    const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioCtxClass) return () => {}

    const audioCtx = new AudioCtxClass()

    // Resume immediately if suspended by browser autoplay policy
    const tryResume = () => {
      if (audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {})
      }
    }
    tryResume()

    // Add immediate gesture listeners to unlock audio if browser autoplay restricted it
    const unlockEvents = ['click', 'touchstart', 'touchend', 'keydown', 'pointerdown']
    const handleGestureUnlock = () => {
      tryResume()
      unlockEvents.forEach((evt) => window.removeEventListener(evt, handleGestureUnlock))
    }
    unlockEvents.forEach((evt) => window.addEventListener(evt, handleGestureUnlock, { once: true, passive: true }))

    const osc = audioCtx.createOscillator()
    const gain = audioCtx.createGain()

    osc.type = 'sawtooth'
    gain.gain.setValueAtTime(0.85, audioCtx.currentTime)

    let high = false
    osc.frequency.setValueAtTime(750, audioCtx.currentTime)

    const interval = window.setInterval(() => {
      if (audioCtx.state === 'closed') {
        clearInterval(interval)
        return
      }
      tryResume()
      const nextFreq = high ? 750 : 1150
      try {
        osc.frequency.cancelScheduledValues(audioCtx.currentTime)
        osc.frequency.linearRampToValueAtTime(nextFreq, audioCtx.currentTime + 0.12)
      } catch (e) {
        osc.frequency.setValueAtTime(nextFreq, audioCtx.currentTime)
      }
      high = !high
    }, 450)

    osc.connect(gain)
    gain.connect(audioCtx.destination)
    osc.start()

    // Vibrate phone if supported
    if ('vibrate' in navigator) {
      navigator.vibrate([800, 200, 800, 200, 800])
    }

    const stop = () => {
      clearInterval(interval)
      unlockEvents.forEach((evt) => window.removeEventListener(evt, handleGestureUnlock))
      try {
        gain.gain.setValueAtTime(gain.gain.value, audioCtx.currentTime)
        gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.05)
        setTimeout(() => {
          try {
            osc.stop()
            audioCtx.close()
          } catch (e) {}
        }, 60)
      } catch (e) {
        try {
          osc.stop()
          audioCtx.close()
        } catch (e2) {}
      }
      if ('vibrate' in navigator) {
        navigator.vibrate(0)
      }
      if (activeSirenStop === stop) {
        activeSirenStop = null
      }
    }

    activeSirenStop = stop
    return stop
  } catch (err) {
    console.error('AudioContext emergency siren failed:', err)
    return () => {}
  }
}

export function stopEmergencySiren() {
  if (activeSirenStop) {
    try {
      activeSirenStop()
    } catch (e) {}
    activeSirenStop = null
  }
}

export function isEmergencySirenPlaying(): boolean {
  return activeSirenStop !== null
}

/**
 * Speaks text using the browser's native SpeechSynthesis API.
 * Ensures reassuring voice output even if remote audio files fail to load.
 */
export function speakText(text: string, rate: number = 1.0): Promise<void> {
  return new Promise((resolve) => {
    if (!('speechSynthesis' in window)) {
      resolve()
      return
    }

    window.speechSynthesis.cancel() // Stop any previous speech
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = Math.max(0.6, Math.min(1.5, rate))
    utterance.pitch = 1.0

    // Try to select an English voice
    const voices = window.speechSynthesis.getVoices()
    const englishVoice = voices.find((v) => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha') || v.default))
    if (englishVoice) {
      utterance.voice = englishVoice
    }

    utterance.onend = () => resolve()
    utterance.onerror = () => resolve()

    window.speechSynthesis.speak(utterance)
  })
}

export function stopSpeaking() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
}

/**
 * Microphone Recorder using MediaRecorder
 */
class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private stream: MediaStream | null = null

  async start(): Promise<boolean> {
    try {
      this.chunks = []
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      this.mediaRecorder = new MediaRecorder(this.stream)

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          this.chunks.push(e.data)
        }
      }

      this.mediaRecorder.start()
      return true
    } catch (err) {
      console.warn('Microphone permission not granted or unsupported:', err)
      return false
    }
  }

  stop(): Promise<string | null> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
        resolve(null)
        return
      }

      this.mediaRecorder.onstop = async () => {
        try {
          const blob = new Blob(this.chunks, { type: 'audio/webm;codecs=opus' })
          const reader = new FileReader()
          reader.onloadend = () => {
            const base64String = (reader.result as string).split(',')[1]
            resolve(base64String || null)
          }
          reader.readAsDataURL(blob)
        } catch (e) {
          console.error('Error converting blob to base64:', e)
          resolve(null)
        } finally {
          if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop())
            this.stream = null
          }
        }
      }

      this.mediaRecorder.stop()
    })
  }

  isRecording(): boolean {
    return this.mediaRecorder !== null && this.mediaRecorder.state === 'recording'
  }
}

export const audioRecorder = new AudioRecorder()
