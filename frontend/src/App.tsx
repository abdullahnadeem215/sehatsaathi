import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, Bell, Check, ChevronRight, CircleHelp, HeartPulse, Keyboard,
  Mic, PhoneCall, Play, RotateCcw, Send, Settings, ShieldCheck,
  Users, Volume2, VolumeX, X, Zap, AlertTriangle, Pill, Plus, Trash2,
  Calendar, CheckCircle2, Clock, Upload, Camera, FileText, Mail, User,
  Home, ClipboardList,
  Stethoscope, AlertCircle, RefreshCw, History, QrCode, ExternalLink, Copy
} from 'lucide-react'
import QRCode from 'qrcode'
import jsQR from 'jsqr'

import {
  API_BASE,
  TurnResponse,
  PrescriptionItem,
  DashboardResponse,
  CaregiverLinkItem,
  PairPendingItem,
  PatientProfile,
  ExtractedMedicineItem,
  PrescriptionOCRResponse,
  DoctorEmailItem,
  DueReminderResponse,
  PatientMemoryItem,
  getPatientToken,
  getCaregiverToken,
  setCaregiverToken,
  registerPatient,
  getPatientProfile,
  updatePatientProfile,
  submitTurn,
  confirmAction,
  getReminders,
  createPairingKey,
  redeemPairingKey,
  getPendingPairRequests,
  decidePairRequest,
  checkPairStatus,
  getLinkedCaregivers,
  revokeCaregiverLink,
  getCaregiverDashboard,
  markAlertHandled,
  getPrescriptions,
  createPrescription,
  deletePrescription,
  uploadPrescriptionImage,
  draftDoctorEmail,
  approveDoctorEmail,
  declineDoctorEmail,
  getDoctorEmails,
  notifyFamilyEmergency,
  getDueReminder,
  recordNaturalIntake,
  takeReminderWithOffset,
  getPatientMemories,
} from './api'

import {
  playEmergencySiren,
  stopEmergencySiren,
  isEmergencySirenPlaying,
  speakText,
  stopSpeaking,
  audioRecorder
} from './utils/audio'

type Screen = 'signup' | 'role' | 'home' | 'reminder' | 'answer' | 'emergency' | 'caregiver'
type TextSize = 'normal' | 'large' | 'extra'

const textSizes: Record<TextSize, string> = {
  normal: '24px', // UX-02: Base text size is at least 24px
  large: '28px',
  extra: '34px',
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => {
    const isRegistered = Boolean(localStorage.getItem('patient_registered') && getPatientToken())
    if (!isRegistered) return 'signup'
    const savedRole = localStorage.getItem('user-role')
    if (savedRole === 'caregiver') return 'caregiver'
    if (savedRole === 'patient') return 'home'
    return 'role'
  })

  const [textSize, setTextSize] = useState<TextSize>(() => (localStorage.getItem('text-size') as TextSize) || 'normal')
  const [highContrast, setHighContrast] = useState(false)
  const [patientName, setPatientName] = useState(() => localStorage.getItem('patient_display_name') || '')
  const [patientProfile, setPatientProfile] = useState<PatientProfile | null>(null)

  // Professional startup splash screen state
  const [loadingSplash, setLoadingSplash] = useState(true)

  // Modals
  const [showPairingModal, setShowPairingModal] = useState(false)
  const [showPrescriptionModal, setShowPrescriptionModal] = useState(false)
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [showDoctorModal, setShowDoctorModal] = useState(false)
  const [showMemoryModal, setShowMemoryModal] = useState(false)
  const [dueReminder, setDueReminder] = useState<DueReminderResponse | null>(null)
  const [dismissedDueReminderId, setDismissedDueReminderId] = useState<number | null>(null)

  const [pendingConfirm, setPendingConfirm] = useState<{
    actionId: string
    echoBack: string
    emailDraft?: DoctorEmailItem | null
    toolCalled?: string | null
  } | null>(null)

  // Turn / Audio State
  const [turnState, setTurnState] = useState<'idle' | 'listening' | 'thinking' | 'speaking'>('idle')
  const [currentAnswer, setCurrentAnswer] = useState<TurnResponse | null>(null)
  const [holdingMessage, setHoldingMessage] = useState('')
  const [linkedCaregiversCount, setLinkedCaregiversCount] = useState(0)
  const [nextMedicine, setNextMedicine] = useState<string>('')
  const [reminders, setReminders] = useState<any[]>([])

  // Caregiver Live Siren / Emergency state
  const [activeEmergencyAlert, setActiveEmergencyAlert] = useState<{ id: number; transcript: string; created_at: string } | null>(null)
  const sirenStopRef = useRef<(() => void) | null>(null)

  // Apply Text Size (UX-02)
  useEffect(() => {
    localStorage.setItem('text-size', textSize)
    document.documentElement.style.setProperty('--base-size', textSizes[textSize])
  }, [textSize])

  // Strict Guard: Patient app cannot be accessed until signup is completed
  useEffect(() => {
    const isRegistered = Boolean(localStorage.getItem('patient_registered') && getPatientToken())
    if (!isRegistered && screen !== 'signup' && screen !== 'caregiver') {
      setScreen('signup')
    }
  }, [screen])

  // Periodic Due Reminders Checker
  const checkDueReminder = async () => {
    try {
      const due = await getDueReminder()
      setDueReminder(due)
      if (due.has_due_reminder && due.reminder && 'Notification' in window && Notification.permission === 'granted') {
        new Notification('Sehat Saathi Reminder', {
          body: due.prompt_text || `Did you take your ${due.reminder.medicine_name}?`,
          icon: '/favicon.ico'
        })
      }
    } catch {
      // offline fallback
    }
  }

  const handleTakeMedicineFromBanner = async (reminderId: number, timeOffsetMinutes: number = 0, note?: string) => {
    try {
      const res = await takeReminderWithOffset(reminderId, timeOffsetMinutes, note)
      speakText(res.message || 'I have recorded that you took your medicine. Well done!')
      setDismissedDueReminderId(reminderId)
      await checkDueReminder()
      await refreshPatientData()
    } catch (e) {
      console.error('Failed to log intake:', e)
    }
  }

  // Initial Patient Setup & Splash Timer
  useEffect(() => {
    async function initPatient() {
      const isRegistered = Boolean(localStorage.getItem('patient_registered') && getPatientToken())
      if (!isRegistered) {
        setScreen('signup')
        return
      }

      try {
        const prof = await getPatientProfile()
        if (prof) {
          setPatientProfile(prof)
          if (prof.display_name) setPatientName(prof.display_name)
        } else {
          throw new Error('No profile')
        }
      } catch (e) {
        // Reset stale tokens and keep user on signup
        localStorage.removeItem('patient_registered')
        localStorage.removeItem('patient_device_token')
        localStorage.removeItem('patient_id')
        localStorage.removeItem('patient_display_name')
        localStorage.removeItem('patient_email')
        setScreen('signup')
        return
      }
      refreshPatientData()
      checkDueReminder()

      // Request browser notification permission gently if supported
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().catch(() => {})
      }
    }
    initPatient()

    const reminderTimer = setInterval(checkDueReminder, 25000)

    // Professional startup loading duration (~1.2s)
    const splashTimer = setTimeout(() => {
      setLoadingSplash(false)
    }, 1200)
    return () => {
      clearTimeout(splashTimer)
      clearInterval(reminderTimer)
    }
  }, [])

  const handleSignupSuccess = (profile: PatientProfile) => {
    setPatientProfile(profile)
    setPatientName(profile.display_name)
    localStorage.setItem('user-role', 'patient')
    setScreen('home')
    refreshPatientData()
    checkDueReminder()
  }

  const handleCaregiverJoin = () => {
    localStorage.setItem('user-role', 'caregiver')
    setScreen('caregiver')
  }

  const handleSwitchAccount = () => {
    localStorage.removeItem('patient_registered')
    localStorage.removeItem('patient_device_token')
    localStorage.removeItem('patient_id')
    localStorage.removeItem('patient_display_name')
    localStorage.removeItem('patient_email')
    setShowProfileModal(false)
    setScreen('signup')
  }

  // Refresh Patient Reminders, Linked count & Profile
  const refreshPatientData = async () => {
    try {
      const links = await getLinkedCaregivers()
      setLinkedCaregiversCount(links.filter((l) => l.is_active).length)
      const reminders = await getReminders()
      setReminders(Array.isArray(reminders) ? reminders : [])
      if (reminders && reminders.length > 0) {
        const rem = reminders[0]
        setNextMedicine(`${rem.medicine_name} ${rem.dose_text} · ${rem.timing_text}`)
      } else {
        setNextMedicine('')
      }
      const prof = await getPatientProfile()
      if (prof) {
        setPatientProfile(prof)
        if (prof.display_name) setPatientName(prof.display_name)
      }
    } catch (e) {
      // offline silent fallback
    }
  }

  // Handle Role Selection
  const chooseRole = (role: 'patient' | 'caregiver') => {
    localStorage.setItem('user-role', role)
    if (role === 'caregiver') {
      setScreen('caregiver')
    } else {
      setScreen('home')
      refreshPatientData()
    }
  }

  // Primary Action: Submit Question (Voice or Typed)
  const handleQuerySubmit = async (queryText?: string, audioBase64?: string | null) => {
    setTurnState('thinking')
    setHoldingMessage('')

    // UX-21: Holding phrase if > 4s
    const holdingTimer = window.setTimeout(() => {
      setHoldingMessage('Please wait a moment...')
    }, 4000)

    try {
      const response = await submitTurn({ text: queryText, audio_base64: audioBase64 })
      clearTimeout(holdingTimer)
      setHoldingMessage('')

      // Red-Flag Emergency Detected (UX-27)
      if (response.is_emergency || response.ui_state === 'emergency') {
        setCurrentAnswer(response)
        setTurnState('idle')
        setScreen('emergency')
        sirenStopRef.current = playEmergencySiren()
        speakText('Emergency detected. Please call 911 immediately. Your family caregiver buzzer has been alerted.')
        return
      }

      // Action requiring confirmation (UX-14) or Doctor Email Approval
      if (response.pending_action_id && response.echo_back) {
        setPendingConfirm({
          actionId: response.pending_action_id,
          echoBack: response.echo_back,
          emailDraft: response.email_draft,
          toolCalled: response.tool_called,
        })
        setTurnState('idle')
        speakText(response.echo_back)
        return
      }

      // Standard Grounded Answer or Intake confirmation
      setCurrentAnswer(response)
      setTurnState('speaking')
      setScreen('answer')
      speakText(response.answer)
      refreshPatientData()
      checkDueReminder()
    } catch (err: any) {
      clearTimeout(holdingTimer)
      setTurnState('idle')
      // UX-24: Never show technical jargon
      alert('I could not hear that clearly. Please say it again or type your question below.')
    }
  }

  // Handle Confirm-Before-Act Decision (UX-14, UX-15)
  const handleConfirmDecision = async (confirmed: boolean) => {
    if (!pendingConfirm) return
    try {
      const res = await confirmAction(pendingConfirm.actionId, confirmed)
      setPendingConfirm(null)
      if (confirmed) {
        speakText(res.message || 'Confirmed and saved.')
        refreshPatientData()
      } else {
        // UX-15: Polite 'No' handling returns to home
        speakText('All right, please say it again.')
      }
    } catch (e) {
      setPendingConfirm(null)
    }
  }

  // Emergency Siren Handlers for Caregiver & Patient
  const handleSilenceSiren = () => {
    if (sirenStopRef.current) {
      sirenStopRef.current()
      sirenStopRef.current = null
    }
    stopEmergencySiren()
    stopSpeaking()
  }

  const handleMarkEmergencyHandled = async (alertId: number) => {
    handleSilenceSiren()
    await markAlertHandled(alertId)
    setActiveEmergencyAlert(null)
  }

  return (
    <div className={`app ${highContrast ? 'high-contrast' : ''}`}>
      {/* 0. Professional Startup Splash Screen */}
      {loadingSplash && <SplashScreen />}

      {/* 0b. Professional Startup Signup Screen */}
      {screen === 'signup' && (
        <SignupScreen
          onSignupSuccess={handleSignupSuccess}
          onCaregiverJoin={handleCaregiverJoin}
        />
      )}

      {/* 1. Role Selection Screen */}
      {screen === 'role' && <RoleScreen onChoose={chooseRole} />}

      {/* 2. Patient Home Screen */}
      {screen === 'home' && (
        <HomeScreen
          patientName={patientName}
          patientProfile={patientProfile}
          nextMedicine={nextMedicine}
          turnState={turnState}
          holdingMessage={holdingMessage}
          linkedCaregiversCount={linkedCaregiversCount}
          dueReminder={dueReminder}
          dismissedDueReminderId={dismissedDueReminderId}
          onSubmitQuery={handleQuerySubmit}
          onTakeMedicine={handleTakeMedicineFromBanner}
          onDismissDueReminder={(remId) => setDismissedDueReminderId(remId)}
          onEmergencyClick={async () => {
            setScreen('emergency')
            sirenStopRef.current = playEmergencySiren()
            speakText('Emergency assistance requested. Please call 911 immediately. Alerting your family.')
            try {
              await notifyFamilyEmergency()
            } catch (e) {
              console.warn('Emergency notification fallback:', e)
            }
          }}
          onFamilyClick={() => setShowPairingModal(true)}
          onPrescriptionsClick={() => setShowPrescriptionModal(true)}
          onDoctorClick={() => setShowDoctorModal(true)}
          onProfileClick={() => setShowProfileModal(true)}
          onMemoryClick={() => setShowMemoryModal(true)}
          onRoleSwitch={() => setScreen('role')}
          onReminderClick={() => setScreen('reminder')}
        />
      )}

      {screen === 'reminder' && (
        <ReminderScreen
          nextMedicine={nextMedicine}
          dueReminder={dueReminder}
          reminders={reminders}
          dismissedDueReminderId={dismissedDueReminderId}
          linkedCaregiversCount={linkedCaregiversCount}
          onBack={() => setScreen('home')}
          onTakeMedicine={handleTakeMedicineFromBanner}
          onSnooze={(reminderId) => setDismissedDueReminderId(reminderId)}
          onEmergencyClick={() => setScreen('emergency')}
          onPrescriptionsClick={() => setShowPrescriptionModal(true)}
          onHomeClick={() => setScreen('home')}
          onVisitsClick={() => setShowDoctorModal(true)}
          onRecordsClick={() => setShowMemoryModal(true)}
        />
      )}

      {/* 3. Patient Answer Screen */}
      {screen === 'answer' && currentAnswer && (
        <AnswerScreen
          answer={currentAnswer}
          onBack={() => {
            stopSpeaking()
            setTurnState('idle')
            setScreen('home')
          }}
        />
      )}

      {/* 4. Patient Emergency Screen (UX-27) */}
      {screen === 'emergency' && (
        <EmergencyScreen
          linkedCount={linkedCaregiversCount}
          onSilenceSiren={handleSilenceSiren}
          onRestartSiren={() => {
            sirenStopRef.current = playEmergencySiren()
          }}
          onBack={() => {
            handleSilenceSiren()
            setScreen('home')
          }}
        />
      )}

      {/* 5. Caregiver Screen (Key Entry or Scoped Dashboard) */}
      {screen === 'caregiver' && (
        <CaregiverScreen
          onSwitchToPatient={() => {
            localStorage.setItem('user-role', 'patient')
            setScreen('home')
          }}
          patientProfile={patientProfile}
          activeEmergencyAlert={activeEmergencyAlert}
          setActiveEmergencyAlert={setActiveEmergencyAlert}
          onTriggerSiren={(alert) => {
            setActiveEmergencyAlert(alert)
            sirenStopRef.current = playEmergencySiren()
          }}
          onSilenceSiren={handleSilenceSiren}
          onMarkHandled={handleMarkEmergencyHandled}
          onDoctorClick={() => setShowDoctorModal(true)}
          onProfileClick={() => setShowProfileModal(true)}
        />
      )}

      {/* Confirm-Before-Act Modal (UX-14, UX-15, Doctor Email Approval) */}
      {pendingConfirm && (
        <ConfirmModal
          echoBack={pendingConfirm.echoBack}
          emailDraft={pendingConfirm.emailDraft}
          onConfirm={() => handleConfirmDecision(true)}
          onReject={() => handleConfirmDecision(false)}
        />
      )}

      {/* Patient Family Pairing Modal (UX-40, UX-41, UX-42) */}
      {showPairingModal && (
        <FamilyPairingModal
          onClose={() => {
            setShowPairingModal(false)
            refreshPatientData()
          }}
        />
      )}

      {/* Prescriptions Management Modal (With OCR & Missing Timing Detection) */}
      {showPrescriptionModal && (
        <PrescriptionsModal
          role={screen === 'caregiver' ? 'caregiver' : 'patient'}
          onClose={() => {
            setShowPrescriptionModal(false)
            refreshPatientData()
          }}
        />
      )}

      {/* Patient Profile & Doctor Setup Modal */}
      {showProfileModal && (
        <PatientProfileModal
          profile={patientProfile}
          onSwitchAccount={handleSwitchAccount}
          onClose={() => {
            setShowProfileModal(false)
            refreshPatientData()
          }}
        />
      )}

      {/* Doctor consultation and email approval modal (strict consent) */}
      {showDoctorModal && (
        <DoctorConsultModal
          patientProfile={patientProfile}
          role={screen === 'caregiver' ? 'caregiver' : 'patient'}
          onClose={() => setShowDoctorModal(false)}
        />
      )}

      {/* Conversation history and medication context modal */}
      {showMemoryModal && (
        <MemoryModal
          onClose={() => setShowMemoryModal(false)}
          onTestQuery={(q) => handleQuerySubmit(q, null)}
        />
      )}

      {/* Persistent Accessibility Bar (UX-02, UX-04) */}
      {screen !== 'role' && (
        <AccessibilityBar
          textSize={textSize}
          setTextSize={setTextSize}
          highContrast={highContrast}
          setHighContrast={setHighContrast}
          currentScreen={screen}
          showRoleSwitch={screen !== 'signup' && Boolean(localStorage.getItem('patient_registered') && getPatientToken())}
          onSwitchRole={() => setScreen(screen === 'caregiver' ? 'home' : 'caregiver')}
        />
      )}
    </div>
  )
}

/* -------------------------------------------------------------
   Professional Startup Signup Screen (Onboarding)
   Loads at startup for individual user, persists to SQLite DB
------------------------------------------------------------- */
function SignupScreen({
  onSignupSuccess,
  onCaregiverJoin,
}: {
  onSignupSuccess: (profile: PatientProfile) => void
  onCaregiverJoin: () => void
}) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [age, setAge] = useState('')
  const [emergencyContact, setEmergencyContact] = useState('')

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!fullName.trim()) {
      setErrorMsg('Please enter your full name.')
      return
    }

    setIsSubmitting(true)
    setErrorMsg(null)

    try {
      const res = await registerPatient({
        display_name: fullName.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        age: age.trim() ? parseInt(age.trim(), 10) : undefined,
        emergency_contact_name: emergencyContact.trim() || undefined,
      })

      let profile: PatientProfile
      try {
        profile = await getPatientProfile()
      } catch {
        profile = {
          patient_id: res.patient_id,
          display_name: res.display_name,
          email: res.email || email.trim() || null,
          phone: phone.trim() || null,
          age: age.trim() ? parseInt(age.trim(), 10) : null,
          emergency_contact_name: emergencyContact.trim() || null,
          doctor_name: null,
          doctor_email: null,
          doctor_specialty: null,
          doctor_phone: null,
          created_at: new Date().toISOString(),
        }
      }

      speakText(`Welcome to Sehat Saathi, ${res.display_name}. Your profile is ready.`)
      onSignupSuccess(profile)
    } catch (err: any) {
      console.error('Registration failed:', err)
      setErrorMsg('Unable to save user profile. Please check your connection and try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="signup-page-wrapper">
      <main className="signup-card" role="main" aria-label="Sehat Saathi Patient Registration">
        {/* Header with App Branding */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 16,
              background: 'var(--mint)',
              color: 'var(--green-dark)',
              display: 'grid',
              placeItems: 'center',
              flexShrink: 0,
            }}
          >
            <HeartPulse size={30} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <h1 style={{ fontSize: '1.45rem', fontWeight: 800, margin: 0, color: 'var(--ink)' }}>
                Sehat Saathi
              </h1>
            </div>
            <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
              A simple place for your daily care
            </p>
          </div>
        </div>

        <div style={{ background: '#f8fafc', padding: '14px 16px', borderRadius: 14, border: '1px solid var(--line)', marginBottom: 20 }}>
          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--ink)', lineHeight: 1.45 }}>
            <strong>Welcome.</strong> Add a few details so your care plan and reminders are ready.
          </p>
        </div>

        {errorMsg && (
          <div
            role="alert"
            style={{
              padding: '10px 14px',
              borderRadius: 12,
              background: '#fee2e2',
              color: '#991b1b',
              fontSize: '0.88rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 16,
            }}
          >
            <AlertCircle size={18} />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate={false}>
          {/* Section 1: Patient Details */}
          <div className="form-section-title">
            <User size={18} />
            <span>Your details</span>
          </div>

          <div className="profile-form-grid">
            <div className="form-field-group">
              <label htmlFor="signup-name">
                Full Name <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                id="signup-name"
                required
                type="text"
                placeholder="Enter patient full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>

            <div className="form-field-group">
              <label htmlFor="signup-email">Email <span className="field-optional">(optional)</span></label>
              <input
                id="signup-email"
                type="email"
                placeholder="your.email@gmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-field-group">
              <label htmlFor="signup-phone">Phone <span className="field-optional">(optional)</span></label>
              <input
                id="signup-phone"
                type="tel"
                placeholder="e.g. +1 (555) 000-0000"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <div className="form-field-group">
              <label htmlFor="signup-age">Age <span className="field-optional">(optional)</span></label>
              <input
                id="signup-age"
                type="number"
                min={1}
                max={120}
                placeholder="e.g. 68"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>

            <div className="form-field-group" style={{ gridColumn: 'span 2' }}>
              <label htmlFor="signup-emergency">Emergency contact <span className="field-optional">(optional)</span></label>
              <input
                id="signup-emergency"
                type="text"
                placeholder="e.g. Contact name, relationship, phone number"
                value={emergencyContact}
                onChange={(e) => setEmergencyContact(e.target.value)}
              />
            </div>
          </div>

          {/* Submit Button */}
          <div style={{ marginTop: 24 }}>
            <button
              type="submit"
              className="signup-submit-btn"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="spin" size={20} />
                  <span>Setting Up Your Account...</span>
                </>
              ) : (
                <>
                  <span>Continue to Sehat Saathi</span>
                  <ChevronRight size={20} />
                </>
              )}
            </button>
          </div>
        </form>

        {/* Alternate Navigation for Family Member / Caregiver */}
        <div style={{ marginTop: 20, textAlign: 'center', borderTop: '1px solid var(--line)', paddingTop: 16 }}>
          <p className="muted" style={{ margin: '0 0 8px 0', fontSize: '0.88rem' }}>
            Are you a family member or caregiver setting up remote monitoring?
          </p>
          <button
            type="button"
            onClick={onCaregiverJoin}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--blue)',
              fontWeight: 700,
              fontSize: '0.92rem',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              textDecoration: 'underline',
            }}
          >
            <Users size={16} />
            <span>Switch to Caregiver Portal</span>
          </button>
        </div>
      </main>
    </div>
  )
}

/* -------------------------------------------------------------
   Role Selection Screen (UX-39)
------------------------------------------------------------- */
function RoleScreen({ onChoose }: { onChoose: (role: 'patient' | 'caregiver') => void }) {
  return (
    <main className="center-page role-page">
      <div className="welcome-art">
        <HeartPulse size={48} strokeWidth={1.8} />
      </div>
      <div className="brand">
        <span className="brand-mark"><HeartPulse size={22} /></span>
        <span>Sehat Saathi</span>
      </div>
      <p className="eyebrow" style={{ marginTop: 12 }}>YOUR GENTLE HEALTH COMPANION</p>
      <h1>Who are you today?</h1>
      <p className="muted" style={{ maxWidth: 440, marginTop: 10 }}>
        A simpler, safer way to manage medicine and stay connected with loved ones.
      </p>

      <div className="role-options">
        <button className="role-card" onClick={() => onChoose('patient')}>
          <span className="role-icon"><HeartPulse size={30} /></span>
          <span>
            <strong>I am the Patient</strong>
            <small>Speak about your medicines and care needs</small>
          </span>
          <ChevronRight size={24} />
        </button>

        <button className="role-card" onClick={() => onChoose('caregiver')}>
          <span className="role-icon blue"><Users size={30} /></span>
          <span>
            <strong>I am a Family Member / Caregiver</strong>
            <small>Monitor vitals, receive emergency alerts, and manage prescriptions</small>
          </span>
          <ChevronRight size={24} />
        </button>
      </div>

      <p className="muted" style={{ fontSize: '0.8rem', marginTop: 28, display: 'flex', alignItems: 'center', gap: 6 }}>
        <ShieldCheck size={18} /> English-only Edition · WCAG AAA Accessible
      </p>
    </main>
  )
}

function ReminderScreen({
  nextMedicine,
  dueReminder,
  reminders,
  dismissedDueReminderId,
  linkedCaregiversCount,
  onBack,
  onTakeMedicine,
  onSnooze,
  onEmergencyClick,
  onPrescriptionsClick,
  onHomeClick,
  onVisitsClick,
  onRecordsClick,
}: {
  nextMedicine: string
  dueReminder: DueReminderResponse | null
  reminders: any[]
  dismissedDueReminderId: number | null
  linkedCaregiversCount: number
  onBack: () => void
  onTakeMedicine: (reminderId: number, timeOffsetMinutes: number, note?: string) => void
  onSnooze: (reminderId: number) => void
  onEmergencyClick: () => void
  onPrescriptionsClick: () => void
  onHomeClick: () => void
  onVisitsClick: () => void
  onRecordsClick: () => void
}) {
  const reminder = dueReminder?.reminder
  const isActive = Boolean(reminder && dismissedDueReminderId !== reminder.id)
  const medicineName = reminder?.medicine_name || nextMedicine.split(' ')[0] || 'Your medicine'
  const dose = reminder
    ? `${reminder.dose_text} · ${reminder.timing_text}`
    : nextMedicine || 'Add a medicine schedule to see it here'

  return (
    <main className="wire-reminder-page">
      <header className="wire-screen-header">
        <button className="wire-back-button" onClick={onBack} aria-label="Back to home">
          <ArrowLeft size={20} />
        </button>
        <span className="wire-time">18:30</span>
        <button className="wire-more-button" onClick={onPrescriptionsClick} aria-label="Manage medicines">
          <Pill size={20} />
        </button>
      </header>

      <section className="wire-reminder-card">
        <div className="wire-pill-icon" aria-hidden="true">
          <Pill size={54} strokeWidth={1.4} />
        </div>
        <p className="wire-eyebrow">MEDICINE REMINDER</p>
        <h1>Time for your<br />medicine</h1>

        <div className="wire-medicine-detail">
          <strong>{medicineName}</strong>
          <span>{dose}</span>
          {reminder && <span><Clock size={14} /> {reminder.timing_text}</span>}
        </div>

        {isActive && reminder ? (
          <>
            <button
              className="wire-taken-button"
              onClick={() => onTakeMedicine(reminder.id, 0, 'Taken just now')}
            >
              <Check size={18} />
              I have taken my medicine
            </button>
            <button className="wire-snooze-button" onClick={() => onSnooze(reminder.id)}>
              <Clock size={16} />
              Snooze for 10 minutes
            </button>
          </>
        ) : (
          <div className="wire-complete-state">
            <CheckCircle2 size={18} />
            {reminder ? 'Medicine recorded for this reminder' : 'No medicine due right now'}
          </div>
        )}

        <div className="wire-family-status">
          <CheckCircle2 size={17} />
          <span>
            <strong>{linkedCaregiversCount > 0 ? 'Family connected' : 'Family not connected'}</strong>
            <small>
              {linkedCaregiversCount > 0
                ? 'Your care team can see your reminder status.'
                : 'Connect a family member from the Family menu.'}
            </small>
          </span>
        </div>
      </section>

      <section className="wire-all-reminders">
        <div className="wire-section-heading">
          <h2>All reminders</h2>
          <button onClick={onPrescriptionsClick}>Manage</button>
        </div>
        {reminders.length === 0 ? (
          <p className="wire-empty-reminders">No reminders yet. Add a prescription to create one.</p>
        ) : (
          reminders.map((item) => (
            <div className={`wire-reminder-row ${item.id === reminder?.id && isActive ? 'current' : ''}`} key={item.id}>
              <span className="wire-reminder-row-icon"><Pill size={18} /></span>
              <span className="wire-reminder-row-copy">
                <strong>{item.medicine_name}</strong>
                <small>{item.dose_text} · {item.timing_text}</small>
              </span>
              <span className={`wire-status ${item.status === 'taken' ? 'taken' : ''}`}>
                {item.status === 'taken' ? 'Taken' : 'Upcoming'}
              </span>
            </div>
          ))
        )}
      </section>

      <button className="wire-help-button" onClick={onEmergencyClick}>
        <PhoneCall size={17} />
        Help / Emergency
      </button>

      <nav className="mobile-bottom-nav" aria-label="Main care navigation">
        <button onClick={onHomeClick}>
          <Home size={20} />
          <span>Home</span>
        </button>
        <button className="active" onClick={() => undefined}>
          <Pill size={20} />
          <span>Reminders</span>
        </button>
        <button onClick={onVisitsClick}>
          <Calendar size={20} />
          <span>Visits</span>
        </button>
        <button onClick={onRecordsClick}>
          <ClipboardList size={20} />
          <span>Records</span>
        </button>
      </nav>
    </main>
  )
}

/* -------------------------------------------------------------
   Patient Home Screen (UX-01, UX-10, UX-11, UX-17, UX-40)
------------------------------------------------------------- */
function HomeScreen({
  patientName,
  patientProfile,
  nextMedicine,
  turnState,
  holdingMessage,
  linkedCaregiversCount,
  dueReminder,
  dismissedDueReminderId,
  onSubmitQuery,
  onTakeMedicine,
  onDismissDueReminder,
  onEmergencyClick,
  onFamilyClick,
  onPrescriptionsClick,
  onDoctorClick,
  onProfileClick,
  onMemoryClick,
  onRoleSwitch,
  onReminderClick,
}: {
  patientName: string
  patientProfile: PatientProfile | null
  nextMedicine: string
  turnState: 'idle' | 'listening' | 'thinking' | 'speaking'
  holdingMessage: string
  linkedCaregiversCount: number
  dueReminder: DueReminderResponse | null
  dismissedDueReminderId: number | null
  onSubmitQuery: (text?: string, audioBase64?: string | null) => void
  onTakeMedicine: (reminderId: number, timeOffsetMinutes: number, note?: string) => void
  onDismissDueReminder: (reminderId: number) => void
  onEmergencyClick: () => void
  onFamilyClick: () => void
  onPrescriptionsClick: () => void
  onDoctorClick: () => void
  onProfileClick: () => void
  onMemoryClick: () => void
  onRoleSwitch: () => void
  onReminderClick: () => void
}) {
  const [typedQuestion, setTypedQuestion] = useState('')
  const [showTypedInput, setShowTypedInput] = useState(false)
  const [isRecording, setIsRecording] = useState(false)

  // Primary Mic Tap Handler (UX-10: Single tap starts, second tap stops)
  const handleMicTap = async () => {
    if (!isRecording) {
      const started = await audioRecorder.start()
      if (started) {
        setIsRecording(true)
      } else {
        // Fallback: prompt typed query if mic unsupported or denied
        setShowTypedInput(true)
      }
    } else {
      setIsRecording(false)
      const base64Audio = await audioRecorder.stop()
      onSubmitQuery(undefined, base64Audio)
    }
  }

  const handleSendTyped = () => {
    if (!typedQuestion.trim()) return
    const text = typedQuestion.trim()
    setTypedQuestion('')
    setShowTypedInput(false)
    onSubmitQuery(text, null)
  }

  return (
    <main className="page">
      {/* Top Bar with Persistent Help & Family */}
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><HeartPulse size={22} /></span>
          <span>Sehat Saathi</span>
        </div>
        <div className="header-actions">
          <button className="icon-button" onClick={onMemoryClick} aria-label="Conversation history">
            <History size={20} color="var(--green)" />
            <span>History</span>
          </button>
          <button className="icon-button" onClick={onPrescriptionsClick} aria-label="Prescriptions and scan">
            <Pill size={20} />
            <span>Medicines</span>
          </button>
          <button className="icon-button" onClick={onDoctorClick} aria-label="Consult Doctor">
            <Mail size={20} />
            <span>Doctor</span>
          </button>
          <button className="icon-button" onClick={onFamilyClick} aria-label="Family and caregivers">
            <Users size={20} />
            <span>Family {linkedCaregiversCount > 0 && `(${linkedCaregiversCount})`}</span>
          </button>
          <button className="icon-button" onClick={onProfileClick} aria-label="Account and Profile Settings">
            <User size={20} />
            <span>Profile</span>
          </button>
          <button className="icon-button emergency-mini" onClick={onEmergencyClick} aria-label="Emergency Assistance">
            <CircleHelp size={20} />
            <span>911 Help</span>
          </button>
        </div>
      </header>

      {/* Patient Greeting & Status */}
      <section className="home-heading">
        <div className="status-pill">
          <span className="status-dot-inner" />
          <span>Care plan ready · English</span>
        </div>
        <h1 style={{ marginTop: 12 }}>Good day, {patientName || 'Friend'}</h1>
        <p className="muted">What can I help you with today?</p>
      </section>

      {/* Active Medication Due Notification Banner */}
      {dueReminder && dueReminder.has_due_reminder && dueReminder.reminder && dismissedDueReminderId !== dueReminder.reminder.id && (
        <section
          className="medication-due-banner animate-fade-in"
          style={{
            background: '#ecfdf5',
            border: '2px solid #10b981',
            borderRadius: 16,
            padding: '16px 20px',
            margin: '14px 0 20px 0',
            boxShadow: '0 4px 14px rgba(16, 185, 129, 0.12)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0 }}>
              <Bell size={22} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#047857', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Medication Check
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#064e3b', marginTop: 2 }}>
                {dueReminder.prompt_text || `Did you take your ${dueReminder.reminder.medicine_name} ${dueReminder.reminder.dose_text}?`}
              </div>
              <p style={{ margin: '4px 0 0', fontSize: '0.88rem', color: '#065f46' }}>
                Scheduled for {dueReminder.reminder.timing_text}. Tap below or speak your response naturally!
              </p>
            </div>
            <button
              onClick={() => onDismissDueReminder(dueReminder.reminder!.id)}
              style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#6b7280', padding: 4 }}
              title="Dismiss for now"
            >
              <X size={20} />
            </button>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
            <button
              onClick={() => onTakeMedicine(dueReminder.reminder!.id, 0, 'Taken just now')}
              style={{
                background: '#059669', color: '#fff', border: 'none', borderRadius: 10,
                padding: '10px 16px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', minHeight: 46
              }}
            >
              <Check size={18} />
              <span>✓ Yes, just now</span>
            </button>

            <button
              onClick={() => onTakeMedicine(dueReminder.reminder!.id, 60, 'Patient took 1 hour ago')}
              style={{
                background: '#ffffff', color: '#065f46', border: '1.5px solid #059669', borderRadius: 10,
                padding: '10px 16px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', minHeight: 46
              }}
            >
              <Clock size={18} />
              <span>⏰ Took 1 hour ago</span>
            </button>

            <button
              onClick={() => onTakeMedicine(dueReminder.reminder!.id, 30, 'Patient took 30 min ago')}
              style={{
                background: '#ffffff', color: '#065f46', border: '1.5px solid #059669', borderRadius: 10,
                padding: '10px 16px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', minHeight: 46
              }}
            >
              <Clock size={18} />
              <span>⏰ 30 min ago</span>
            </button>

            <button
              onClick={() => {
                speakText(`Did you take your ${dueReminder.reminder!.medicine_name}? You can say 'Yes' or 'I took it 1 hour ago'.`)
              }}
              style={{
                background: '#ffffff', color: '#374151', border: '1.5px solid #d1d5db', borderRadius: 10,
                padding: '10px 16px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', minHeight: 46
              }}
            >
              <Mic size={18} />
              <span>Speak answer</span>
            </button>
          </div>
        </section>
      )}

      {/* Daily Medication Card */}
      <section className="daily-card" onClick={onReminderClick} style={{ cursor: 'pointer' }}>
        <div className="daily-icon">
          <Bell size={24} />
        </div>
        <div style={{ flex: 1 }}>
          <strong>Today at a glance</strong>
          <p>{nextMedicine || 'No medications scheduled yet · Tap to add prescriptions'}</p>
        </div>
        <ChevronRight size={22} color="var(--muted)" />
      </section>

      <button className="wire-family-link" onClick={onFamilyClick}>
        <Users size={19} />
        <span>
          <strong>{linkedCaregiversCount > 0 ? 'Family caregiver connected' : 'Add a family caregiver'}</strong>
          <small>{linkedCaregiversCount > 0 ? `${linkedCaregiversCount} linked caregiver${linkedCaregiversCount === 1 ? '' : 's'}` : 'Share reminders and emergency alerts with someone you trust'}</small>
        </span>
        <ChevronRight size={18} />
      </button>

      {/* Voice Zone with 120px+ Big Microphone Button (UX-01) */}
      <section className="voice-zone">
        {isRecording ? (
          <div className="state-badge listening">
            <Mic size={18} />
            <span>I am listening... tap again when done</span>
          </div>
        ) : turnState === 'thinking' ? (
          <div className="state-badge thinking">
            <Clock size={18} />
            <span>{holdingMessage || 'Preparing your information...'}</span>
          </div>
        ) : null}

        {isRecording && (
          <div className="waveform">
            <i /><i /><i /><i /><i /><i /><i />
          </div>
        )}

        <button
          className={`mic-button ${isRecording ? 'listening' : ''}`}
          onClick={handleMicTap}
          aria-label={isRecording ? 'Stop listening and submit' : 'Tap to speak'}
        >
          <span className="mic-ring">
            <Mic size={52} strokeWidth={1.8} />
          </span>
        </button>

        <h2>{isRecording ? 'Tap to finish' : 'Tap to speak'}</h2>
        <p className="muted">Ask anything about your medicines, foods, or discharge notes</p>
      </section>

      {/* Typed Input Fallback (UX-11: Reachable in 1 Tap) */}
      {showTypedInput ? (
        <div className="type-row">
          <input
            autoFocus
            type="text"
            value={typedQuestion}
            onChange={(e) => setTypedQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendTyped()}
            placeholder="Type your question here..."
            aria-label="Type your question"
          />
          <button className="send-button" onClick={handleSendTyped} aria-label="Send question">
            <Send size={22} />
          </button>
        </div>
      ) : (
        <button className="type-link" onClick={() => setShowTypedInput(true)}>
          <Keyboard size={20} />
          <span>Type a question instead</span>
        </button>
      )}

      {/* Quick Prompts */}
      <div className="quick-links">
        <button onClick={onDoctorClick} style={{ borderColor: 'var(--green)', background: '#f4fbf5' }}>
          <Mail size={18} color="var(--green)" />
          <span style={{ fontWeight: 700, color: 'var(--green-dark)' }}>Draft Email to Doctor</span>
        </button>
        <button onClick={() => onSubmitQuery("I've took this 1 hour till now")} style={{ borderColor: '#86efac', background: '#f0fdf4' }}>
          <Clock size={18} color="var(--green)" />
          <span style={{ fontWeight: 700, color: '#166534' }}>"I've took this 1 hour till now"</span>
        </button>
        <button onClick={() => onSubmitQuery("Did I take my medicine?")} style={{ borderColor: '#93c5fd', background: '#eff6ff' }}>
          <History size={18} color="#2563eb" />
          <span style={{ fontWeight: 700, color: '#1e40af' }}>"Did I take my medicine?"</span>
        </button>
        <button onClick={() => onSubmitQuery('When should I take Metformin?')}>
          <Pill size={18} color="var(--green)" />
          <span>When to take Metformin?</span>
        </button>
        <button onClick={() => onSubmitQuery('Can I take a warm shower after surgery?')}>
          <Calendar size={18} color="var(--green)" />
          <span>Can I take a warm shower?</span>
        </button>
        <button onClick={() => onSubmitQuery('What food can I eat today?')}>
          <CheckCircle2 size={18} color="var(--green)" />
          <span>What foods can I eat?</span>
        </button>
      </div>

      {/* Urgent Help Footer Strip */}
      <div className="help-strip">
        <PhoneCall size={22} />
        <span>Need emergency help right away?</span>
        <button onClick={onEmergencyClick}>
          <span>Emergency</span>
          <ChevronRight size={16} />
        </button>
      </div>

      <nav className="mobile-bottom-nav" aria-label="Main care navigation">
        <button className="active" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <Home size={20} />
          <span>Home</span>
        </button>
        <button onClick={onReminderClick}>
          <Pill size={20} />
          <span>Reminders</span>
        </button>
        <button onClick={onDoctorClick}>
          <Calendar size={20} />
          <span>Visits</span>
        </button>
        <button onClick={onMemoryClick}>
          <ClipboardList size={20} />
          <span>Records</span>
        </button>
      </nav>
    </main>
  )
}

/* -------------------------------------------------------------
   Patient Answer & Grounding View (UX-12, UX-13, UX-16)
------------------------------------------------------------- */
function AnswerScreen({ answer, onBack }: { answer: TurnResponse; onBack: () => void }) {
  const [isPlaying, setIsPlaying] = useState(true)
  const [playbackSpeed, setPlaybackSpeed] = useState<0.75 | 1.0>(1.0)

  const handleReplay = () => {
    setIsPlaying(true)
    speakText(answer.answer, playbackSpeed)
  }

  const toggleSpeed = () => {
    const newSpeed = playbackSpeed === 1.0 ? 0.75 : 1.0
    setPlaybackSpeed(newSpeed)
    speakText(answer.answer, newSpeed)
  }

  const togglePlayPause = () => {
    if (isPlaying) {
      stopSpeaking()
      setIsPlaying(false)
    } else {
      setIsPlaying(true)
      speakText(answer.answer, playbackSpeed)
    }
  }

  return (
    <main className="page answer-page">
      <div className="answer-top">
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={20} />
          <span>Back to Home</span>
        </button>
        <div className="brand">
          <span className="brand-mark"><HeartPulse size={20} /></span>
          <span>Sehat Saathi</span>
        </div>
      </div>

      {/* Transcript of patient query */}
      {answer.transcript && (
        <div className="answer-question">
          “{answer.transcript}”
        </div>
      )}

      {/* Grounding Confidence Badge (UX-16) */}
      <div className={`confidence-badge ${answer.confidence_badge.toLowerCase()}`}>
        {answer.confidence_badge === 'Certain' ? (
          <CheckCircle2 size={16} />
        ) : answer.confidence_badge === 'Possibly' ? (
          <AlertTriangle size={16} />
        ) : (
          <CircleHelp size={16} />
        )}
        <span>{answer.confidence_badge} Grounding ({Math.round(answer.confidence * 100)}%)</span>
      </div>

      {/* Primary Headline Answer */}
      <h1 className="answer-headline">{answer.answer}</h1>

      {/* Grounding Source Citation Card (UX-16) */}
      {answer.source_line && (
        <div className="source-card">
          <div className="source-title">
            <ShieldCheck size={18} />
            <span>From your discharge summary</span>
          </div>
          <p>“{answer.source_line}”</p>
        </div>
      )}

      {/* Synchronized Captions (UX-13) */}
      <div className="caption-card">
        <span className="caption-label">
          <Volume2 size={16} /> Spoken Words
        </span>
        <p>
          <mark>{answer.answer}</mark>
        </p>
      </div>

      {/* Audio Controls Bar (UX-12) */}
      <div className="audio-actions">
        <button onClick={handleReplay} aria-label="Replay audio">
          <RotateCcw size={18} />
          <span>Replay</span>
        </button>
        <button onClick={togglePlayPause} aria-label={isPlaying ? 'Pause audio' : 'Play audio'}>
          {isPlaying ? <VolumeX size={18} /> : <Play size={18} />}
          <span>{isPlaying ? 'Pause' : 'Play'}</span>
        </button>
        <button onClick={toggleSpeed} aria-label="Toggle playback speed">
          <Zap size={18} />
          <span>{playbackSpeed === 0.75 ? 'Speed: Slower (0.75x)' : 'Speed: Normal (1.0x)'}</span>
        </button>
      </div>

      <button className="done-button" onClick={onBack}>
        That’s all, thank you
      </button>
    </main>
  )
}

/* -------------------------------------------------------------
   Emergency Screen (UX-27)
------------------------------------------------------------- */
function EmergencyScreen({
  linkedCount,
  onSilenceSiren,
  onRestartSiren,
  onBack,
}: {
  linkedCount: number
  onSilenceSiren: () => void
  onRestartSiren: () => void
  onBack: () => void
}) {
  const [isSirenOn, setIsSirenOn] = useState(() => isEmergencySirenPlaying())

  // Ensure siren starts playing when screen is mounted
  useEffect(() => {
    if (!isEmergencySirenPlaying()) {
      onRestartSiren()
      setIsSirenOn(true)
    }
  }, [])

  const handleSilenceAlarm = () => {
    onSilenceSiren()
    setIsSirenOn(false)
  }

  const handleRestartAlarm = () => {
    onRestartSiren()
    setIsSirenOn(true)
  }

  return (
    <main className="emergency-page">
      <div className="emergency-siren-pill">
        <AlertTriangle size={20} />
        <span>EMERGENCY SIREN {isSirenOn ? 'ACTIVE' : 'MUTED'}</span>
      </div>

      <div className="emergency-icon">
        <PhoneCall size={44} color="#ffffff" />
      </div>
      <p className="eyebrow" style={{ color: '#fecaca', letterSpacing: '0.15em' }}>EMERGENCY ASSISTANCE</p>
      <h1>Help is close by</h1>
      <p>
        For chest pain, breathlessness, stroke signs, or severe discomfort, call <strong>911</strong> immediately.
      </p>

      <a href="tel:911" className="call-button">
        <PhoneCall size={28} />
        <span>Call 911 Now</span>
      </a>

      {/* Explicit alarm stop control */}
      <button
        type="button"
        className="emergency-silence-btn"
        onClick={handleSilenceAlarm}
        disabled={!isSirenOn}
        aria-label="Silence emergency alarm"
      >
        <VolumeX size={22} />
        <span>{isSirenOn ? 'Silence Alarm' : 'Alarm Silenced'}</span>
      </button>

      {!isSirenOn && (
        <button
          type="button"
          className="emergency-restart-btn"
          onClick={handleRestartAlarm}
          aria-label="Restart emergency alarm"
        >
          <Volume2 size={18} />
          <span>Restart Alarm</span>
        </button>
      )}

      <div className="notify-card">
        <strong>Family Notification Status</strong>
        <p>
          {linkedCount > 0
            ? '✓ Your linked family caregiver has been sent an emergency siren buzzer!'
            : 'No family member is linked yet. Please call 911 or emergency services.'}
        </p>
      </div>

      <button
        onClick={onBack}
        className="emergency-close-btn"
        aria-label="Close emergency alert and return home"
        style={{
          marginTop: 24,
          background: 'transparent',
          color: '#fee2e2',
          border: '2px solid rgba(255,255,255,0.4)',
          borderRadius: 16,
          padding: '14px 28px',
          fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        <X size={18} />
        Close Emergency Alert
      </button>
    </main>
  )
}

/* -------------------------------------------------------------
   Confirm-Before-Act Modal (UX-14, UX-15)
------------------------------------------------------------- */
function ConfirmModal({
  echoBack,
  emailDraft,
  onConfirm,
  onReject,
}: {
  echoBack: string
  emailDraft?: DoctorEmailItem | null
  onConfirm: () => void
  onReject: () => void
}) {
  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: emailDraft ? 620 : 480 }}>
        {emailDraft ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="email-status-badge draft">Review required: draft doctor email</span>
              <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Strict Explicit Consent</span>
            </div>
            <h2 style={{ fontSize: '1.4rem', marginBottom: 6 }}>Review Email for Dr. {emailDraft.doctor_name}</h2>
            <p className="muted" style={{ marginBottom: 14 }}>
              This clinical message is ready for your review. It will <strong>never</strong> be sent without your approval.
            </p>

            <div style={{ background: '#f8fafc', border: '1px solid var(--line)', borderRadius: 12, padding: 14, marginBottom: 16, textAlign: 'left' }}>
              <div style={{ marginBottom: 8, fontSize: '0.85rem' }}>
                <strong>To:</strong> Dr. {emailDraft.doctor_name} &lt;{emailDraft.doctor_email}&gt;
              </div>
              <div style={{ marginBottom: 8, fontSize: '0.85rem' }}>
                <strong>Subject:</strong> {emailDraft.subject}
              </div>
              <div style={{ borderTop: '1px solid var(--line)', paddingTop: 10, fontSize: '0.85rem', whiteSpace: 'pre-wrap', maxHeight: 220, overflowY: 'auto', color: 'var(--ink)' }}>
                {emailDraft.body}
              </div>
            </div>

            <div className="confirm-actions">
              <button className="btn-confirm-yes" onClick={onConfirm} style={{ background: 'var(--green)', borderColor: 'var(--green)' }}>
                <Check size={22} />
                <span>Approve & Send to Doctor</span>
              </button>
              <button className="btn-confirm-no" onClick={onReject}>
                <X size={22} />
                <span>Decline / Discard</span>
              </button>
            </div>
          </div>
        ) : (
          <div>
            <p className="eyebrow">CONFIRM BEFORE ACT</p>
            <h2>Please confirm this action</h2>
            <div className="confirm-box">
              “{echoBack}”
            </div>
            <p className="muted">Is this correct?</p>
            <div className="confirm-actions">
              <button className="btn-confirm-yes" onClick={onConfirm}>
                <Check size={24} />
                <span>Yes, correct</span>
              </button>
              <button className="btn-confirm-no" onClick={onReject}>
                <X size={24} />
                <span>No, say again</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Patient Family & Pairing Modal (UX-40, UX-41, UX-42)
------------------------------------------------------------- */
function FamilyPairingModal({ onClose }: { onClose: () => void }) {
  const [keyData, setKeyData] = useState<{ raw: string; formatted: string; expiresAt: string } | null>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string>('')
  const [secondsLeft, setSecondsLeft] = useState(600)
  const [pendingRequests, setPendingRequests] = useState<PairPendingItem[]>([])
  const [linkedCaregivers, setLinkedCaregivers] = useState<CaregiverLinkItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  // Generate pairing key on open
  const handleGenerateKey = async () => {
    setIsLoading(true)
    try {
      const res = await createPairingKey()
      setKeyData({ raw: res.key, formatted: res.formatted_key, expiresAt: res.expires_at })
      setSecondsLeft(res.expires_in_seconds)
    } catch (e) {
      alert('Could not create key. Please check connection.')
    } finally {
      setIsLoading(false)
    }
  }

  // Generate QR code data URL whenever pairing key changes
  useEffect(() => {
    if (keyData?.formatted) {
      QRCode.toDataURL(`sehat-pair:${keyData.formatted}`, {
        width: 240,
        margin: 2,
        color: {
          dark: '#14532d',
          light: '#ffffff',
        },
      })
        .then(setQrDataUrl)
        .catch((err) => {
          console.error('Error generating pairing QR code:', err)
        })
    }
  }, [keyData])

  // Load active links
  const loadLinks = async () => {
    try {
      const links = await getLinkedCaregivers()
      setLinkedCaregivers(links)
    } catch (e) {}
  }

  useEffect(() => {
    handleGenerateKey()
    loadLinks()
  }, [])

  // 10-minute timer countdown
  useEffect(() => {
    if (secondsLeft <= 0) return
    const timer = setInterval(() => setSecondsLeft((s) => s - 1), 1000)
    return () => clearInterval(timer)
  }, [secondsLeft])

  // Poll for incoming caregiver consent requests (UX-42)
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      try {
        const pending = await getPendingPairRequests()
        setPendingRequests(pending)
      } catch (e) {}
    }, 2000)
    return () => clearInterval(pollInterval)
  }, [])

  // Read code aloud
  const handleReadAloud = () => {
    if (!keyData) return
    const spelled = keyData.raw.split('').join(', ')
    speakText(`Your code is: ${spelled}`)
  }

  // Approve or decline request
  const handleDecide = async (pendingId: number, approve: boolean) => {
    await decidePairRequest(pendingId, approve)
    setPendingRequests((prev) => prev.filter((p) => p.pending_id !== pendingId))
    loadLinks()
    speakText(approve ? 'Caregiver approved and linked.' : 'Request declined.')
  }

  const handleRevoke = async (linkId: number) => {
    if (!confirm('Remove this caregiver?')) return
    await revokeCaregiverLink(linkId)
    loadLinks()
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <div>
            <p className="eyebrow">PATIENT CAREGIVER PAIRING</p>
            <h2>Link Family Member</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            <X size={22} />
          </button>
        </div>

        {/* Pending Approval Notice (UX-42) */}
        {pendingRequests.length > 0 && (
          <div style={{ background: '#fef3c7', border: '2px solid #f59e0b', borderRadius: 16, padding: 18, marginBottom: 20 }}>
            <h3 style={{ color: '#92400e', marginBottom: 6 }}>Approval Request</h3>
            <p style={{ color: '#78350f' }}>
              <strong>{pendingRequests[0].caregiver_name}</strong> wants to connect to your health account.
            </p>
            <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
              <button
                style={{ flex: 1, background: 'var(--green)', color: '#fff', borderRadius: 12, fontWeight: 700 }}
                onClick={() => handleDecide(pendingRequests[0].pending_id, true)}
              >
                ✓ Approve
              </button>
              <button
                style={{ flex: 1, background: '#ef4444', color: '#fff', borderRadius: 12, fontWeight: 700 }}
                onClick={() => handleDecide(pendingRequests[0].pending_id, false)}
              >
                ✕ Decline
              </button>
            </div>
          </div>
        )}

        {/* Pairing QR Code (UX-41) */}
        <div className="qr-display-box">
          {qrDataUrl ? (
            <img src={qrDataUrl} alt="Pairing QR Code" className="qr-image" />
          ) : (
            <div style={{ width: 190, height: 190, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <QrCode size={52} color="var(--green)" />
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, color: 'var(--green-dark)', fontWeight: 700, fontSize: '0.88rem' }}>
            <Camera size={16} />
            <span>Scan with Caregiver camera to link instantly</span>
          </div>
        </div>

        {/* Pairing Key (UX-41) */}
        <p className="muted" style={{ textAlign: 'center', fontSize: '0.85rem', margin: '4px 0 10px 0' }}>
          Or enter this 8-character code manually:
        </p>

        {keyData && (
          <div className="key-display">
            <div className="key-segment">{keyData.formatted.split('-')[0]}</div>
            <span style={{ fontSize: '2rem', fontWeight: 900, color: 'var(--muted)' }}>-</span>
            <div className="key-segment">{keyData.formatted.split('-')[1]}</div>
          </div>
        )}

        <div className="key-timer">
          <Clock size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
          Expires in {Math.floor(secondsLeft / 60)}:{(secondsLeft % 60).toString().padStart(2, '0')}
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button className="icon-button" style={{ flex: 1 }} onClick={handleReadAloud}>
            <Volume2 size={18} />
            <span>Read Aloud</span>
          </button>
          <button className="icon-button" style={{ flex: 1 }} onClick={handleGenerateKey} disabled={isLoading}>
            <RotateCcw size={18} />
            <span>New Key</span>
          </button>
        </div>

        {/* Currently Linked Caregivers List */}
        <h3 style={{ marginTop: 28, marginBottom: 12, fontSize: '1.1rem' }}>Linked Caregivers</h3>
        {linkedCaregivers.length === 0 ? (
          <p className="muted" style={{ fontStyle: 'italic' }}>No family members linked yet.</p>
        ) : (
          linkedCaregivers.map((link) => (
            <div key={link.link_id} className="rx-card">
              <div>
                <strong>{link.caregiver_name}</strong>
                <p>Linked {new Date(link.linked_at).toLocaleDateString()}</p>
              </div>
              <button
                style={{ minHeight: 44, padding: '8px 14px', background: '#fee2e2', color: '#991b1b', borderRadius: 10, fontWeight: 700 }}
                onClick={() => handleRevoke(link.link_id)}
              >
                Remove
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
/* -------------------------------------------------------------
   Prescription Management Modal (Shared: Patient & Caregiver)
   Prescription image extraction and missing timing warning
------------------------------------------------------------- */
function PrescriptionsModal({
  role,
  onClose,
}: {
  role: 'patient' | 'caregiver'
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<'list' | 'scan'>('list')
  const [prescriptions, setPrescriptions] = useState<PrescriptionItem[]>([])
  const [showAddForm, setShowAddForm] = useState(false)
  const [medName, setMedName] = useState('')
  const [dose, setDose] = useState('')
  const [timing, setTiming] = useState('')
  const [instructions, setInstructions] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // OCR Prescription Image Scanning State
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [ocrResult, setOcrResult] = useState<PrescriptionOCRResponse | null>(null)
  const [editableExtractedMeds, setEditableExtractedMeds] = useState<ExtractedMedicineItem[]>([])
  const [ocrError, setOcrError] = useState<string | null>(null)
  const [ocrSaveSuccess, setOcrSaveSuccess] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const loadPrescriptions = async () => {
    try {
      const list = await getPrescriptions(role)
      setPrescriptions(list)
    } catch (e) {}
  }

  useEffect(() => {
    loadPrescriptions()
  }, [])

  // Manual Add Form Submission
  const handleAddPrescription = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!medName.trim() || !dose.trim() || !timing.trim()) return

    setIsSubmitting(true)
    try {
      await createPrescription(
        {
          medicine_name: medName.trim(),
          dose_text: dose.trim(),
          timing_text: timing.trim(),
          instructions: instructions.trim() || undefined,
        },
        role
      )
      setMedName('')
      setDose('')
      setTiming('')
      setInstructions('')
      setShowAddForm(false)
      loadPrescriptions()
      speakText(`Added ${medName} to medications list. Reminders scheduled.`)
    } catch (err) {
      alert('Failed to save prescription.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Handle Prescription Image Selection (File or Camera)
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setOcrResult(null)
      setEditableExtractedMeds([])
      setOcrError(null)
      setOcrSaveSuccess(false)
    }
  }

  // Extract prescription details from the uploaded image
  const handleRunOcr = async () => {
    if (!selectedFile) return
    setIsScanning(true)
    setOcrError(null)
    setOcrResult(null)

    try {
      const res = await uploadPrescriptionImage(selectedFile)
      setOcrResult(res)
      setEditableExtractedMeds(res.extracted_medicines || [])

      if (res.has_missing_info) {
        speakText('Prescription scanned. Some information is missing, such as when to take the medicine. Please review the highlighted fields.')
      } else {
        speakText(`Extracted ${res.extracted_medicines.length} medications from prescription.`)
      }
    } catch (err: any) {
      setOcrError(err.message || 'Failed to extract medications from prescription.')
    } finally {
      setIsScanning(false)
    }
  }

  // Edit extracted field
  const updateExtractedMed = (idx: number, field: keyof ExtractedMedicineItem, value: any) => {
    setEditableExtractedMeds((prev) => {
      const copy = [...prev]
      copy[idx] = { ...copy[idx], [field]: value }
      if (field === 'timing_text' && value.trim()) {
        copy[idx].missing_fields = copy[idx].missing_fields.filter((f) => f !== 'timing_text')
      }
      return copy
    })
  }

  // Save all extracted medicines with missing timing validation
  const handleSaveAllExtracted = async () => {
    if (editableExtractedMeds.length === 0) return

    // Strict validation: Require medicine name & timing for each entry
    for (const med of editableExtractedMeds) {
      if (!med.medicine_name.trim()) {
        alert('Please specify a medicine name for all extracted entries.')
        return
      }
      if (!med.timing_text.trim()) {
        alert(`Missing timing: Please enter when to take "${med.medicine_name}" (e.g. "morning after breakfast" or "twice daily") so we can set reminders.`)
        return
      }
    }

    setIsSubmitting(true)
    try {
      for (const med of editableExtractedMeds) {
        await createPrescription(
          {
            medicine_name: med.medicine_name.trim(),
            dose_text: med.dose_text.trim() || '1 dose',
            timing_text: med.timing_text.trim(),
            instructions: med.instructions?.trim() || undefined,
          },
          role
        )
      }
      setOcrSaveSuccess(true)
      speakText('All extracted medications saved to schedule.')
      loadPrescriptions()
      setTimeout(() => {
        setActiveTab('list')
        setOcrResult(null)
        setSelectedFile(null)
        setPreviewUrl(null)
        setOcrSaveSuccess(false)
      }, 1000)
    } catch (err) {
      alert('Failed to save extracted prescriptions.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Remove this prescription?')) return
    await deletePrescription(id, role)
    loadPrescriptions()
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: 620 }}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">MEDICATION MANAGEMENT</p>
            <h2>Prescriptions & Medication</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            <X size={22} />
          </button>
        </div>

        {/* Mode Tabs */}
        <div className="ocr-mode-tabs">
          <button
            className={`ocr-mode-tab ${activeTab === 'list' ? 'active' : ''}`}
            onClick={() => setActiveTab('list')}
          >
            <Pill size={18} />
            <span>Active Prescriptions ({prescriptions.length})</span>
          </button>
          <button
            className={`ocr-mode-tab ${activeTab === 'scan' ? 'active' : ''}`}
            onClick={() => setActiveTab('scan')}
          >
            <Camera size={18} />
            <span>📷 Scan Prescription Image (OCR)</span>
          </button>
        </div>

        {/* Tab 1: Active Prescriptions & Manual Entry */}
        {activeTab === 'list' && (
          <div>
            <p className="muted" style={{ marginBottom: 16 }}>
              Medications are tracked with reminders so you can review them at any time.
            </p>

            {/* Prescription List */}
            {prescriptions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px 10px' }}>
                <Pill size={40} color="var(--muted)" style={{ opacity: 0.5, marginBottom: 8 }} />
                <p className="muted" style={{ fontStyle: 'italic' }}>No active prescriptions recorded yet.</p>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 14 }}>
                  <button className="primary-button" style={{ maxWidth: 220 }} onClick={() => setActiveTab('scan')}>
                    <Camera size={18} />
                    <span>Scan Prescription Image</span>
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ maxHeight: 360, overflowY: 'auto', paddingRight: 4 }}>
                {prescriptions.map((rx) => (
                  <div key={rx.id} className="rx-card">
                    <div>
                      <strong>
                        {rx.medicine_name}
                        <span className="rx-dose-tag">{rx.dose_text}</span>
                      </strong>
                      <p>Schedule: {rx.timing_text}</p>
                      {rx.instructions && <p style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Notes: {rx.instructions}</p>}
                    </div>
                    <button
                      style={{ minHeight: 44, width: 44, borderRadius: 10, background: '#fee2e2', color: '#991b1b', display: 'grid', placeItems: 'center' }}
                      onClick={() => handleDelete(rx.id)}
                      aria-label="Remove prescription"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add Prescription Toggle or Form */}
            {showAddForm ? (
              <form className="rx-form" onSubmit={handleAddPrescription}>
                <h3 style={{ fontSize: '1.1rem', marginTop: 10 }}>Add New Medication Manually</h3>
                <label>
                  Medicine Name
                  <input
                    required
                    type="text"
                    placeholder="e.g. Aspirin, Metformin"
                    value={medName}
                    onChange={(e) => setMedName(e.target.value)}
                  />
                </label>
                <label>
                  Dose / Strength
                  <input
                    required
                    type="text"
                    placeholder="e.g. 75mg, 1 tablet"
                    value={dose}
                    onChange={(e) => setDose(e.target.value)}
                  />
                </label>
                <label>
                  Schedule / Timing
                  <input
                    required
                    type="text"
                    placeholder="e.g. Once daily with dinner"
                    value={timing}
                    onChange={(e) => setTiming(e.target.value)}
                  />
                </label>
                <label>
                  Special Instructions (Optional)
                  <textarea
                    placeholder="e.g. Take with a full glass of water"
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    rows={2}
                  />
                </label>

                <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    style={{ flex: 1, background: 'var(--green)', color: '#fff', borderRadius: 14, fontWeight: 700 }}
                  >
                    {isSubmitting ? 'Saving...' : '+ Save Prescription'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    style={{ background: '#f3f4f6', color: '#374151', borderRadius: 14, padding: '0 18px', fontWeight: 700 }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                <button className="primary-button" style={{ flex: 1 }} onClick={() => setShowAddForm(true)}>
                  <Plus size={20} />
                  <span>Manual Entry</span>
                </button>
                <button
                  className="icon-button"
                  style={{ flex: 1, background: '#f0f7f2', border: '1.5px solid var(--green)', color: 'var(--green-dark)', fontWeight: 700 }}
                  onClick={() => setActiveTab('scan')}
                >
                  <Camera size={20} />
                  <span>Scan Prescription</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Prescription Image Scan */}
        {activeTab === 'scan' && (
          <div>
            <p className="muted" style={{ marginBottom: 14 }}>
              Upload or snap a photo of your doctor's prescription. We will identify medicines and highlight missing timing instructions for your review.
            </p>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            {!previewUrl ? (
              <div className="ocr-upload-zone" onClick={() => fileInputRef.current?.click()}>
                <div className="ocr-upload-icon-wrapper">
                  <Camera size={28} />
                </div>
                <strong>Tap to Take Photo or Upload Image</strong>
                <p className="muted" style={{ fontSize: '0.85rem', marginTop: 4 }}>
                  Supports camera capture, PNG, JPG, or WEBP photos of printed/handwritten prescriptions
                </p>
              </div>
            ) : (
              <div>
                <div className="ocr-preview-box">
                  <img src={previewUrl} alt="Prescription Preview" className="ocr-preview-img" />
                  {isScanning && (
                    <div className="ocr-scanning-overlay">
                      <div className="ocr-scanning-line" />
                      <RefreshCw size={28} className="spin-slow" />
                      <strong>Reading prescription...</strong>
                      <span style={{ fontSize: '0.8rem', opacity: 0.9 }}>Detecting medicines, dosage, and missing timing</span>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
                  <button
                    className="primary-button"
                    style={{ flex: 2 }}
                    onClick={handleRunOcr}
                    disabled={isScanning}
                  >
                    <FileText size={18} />
                    <span>{isScanning ? 'Extracting Medications...' : 'Extract Medications with OCR'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedFile(null)
                      setPreviewUrl(null)
                      setOcrResult(null)
                      setEditableExtractedMeds([])
                    }}
                    style={{ flex: 1, background: '#f3f4f6', borderRadius: 14, fontWeight: 700 }}
                  >
                    Change Photo
                  </button>
                </div>
              </div>
            )}

            {ocrError && (
              <div style={{ background: '#fee2e2', border: '1px solid #f87171', color: '#991b1b', borderRadius: 12, padding: 12, marginTop: 14, fontSize: '0.9rem' }}>
                <AlertCircle size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                {ocrError}
              </div>
            )}

            {/* Extracted Results & Missing Timing Warning */}
            {ocrResult && (
              <div style={{ marginTop: 20 }}>
                {/* Critical Requirement: Warning banner when timing or info is missing */}
                {ocrResult.has_missing_info && (
                  <div className="missing-timing-banner">
                    <AlertTriangle size={24} style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <strong>⚠️ MISSING TIMING INFORMATION DETECTED</strong>
                      <p>
                        {ocrResult.missing_summary ||
                          'The prescription does not specify when to take one or more medicines. Please enter the schedule (e.g. "morning after breakfast" or "twice daily") in the highlighted fields below before saving.'}
                      </p>
                    </div>
                  </div>
                )}

                <h3 style={{ fontSize: '1.05rem', margin: '14px 0 10px', color: 'var(--ink)' }}>
                  Extracted Medications ({editableExtractedMeds.length})
                </h3>

                {editableExtractedMeds.length === 0 ? (
                  <p className="muted" style={{ fontStyle: 'italic' }}>
                    No clear medications were detected. You can add them manually or try a clearer photo.
                  </p>
                ) : (
                  <div style={{ display: 'grid', gap: 12, maxHeight: 320, overflowY: 'auto', paddingRight: 4 }}>
                    {editableExtractedMeds.map((med, idx) => {
                      const isTimingMissing = med.missing_fields?.includes('timing_text') || !med.timing_text.trim()
                      return (
                        <div key={idx} className={`ocr-medicine-card ${isTimingMissing ? 'has-missing' : ''}`}>
                          <div className="ocr-med-header">
                            <strong>Medication #{idx + 1}</strong>
                            {isTimingMissing && (
                              <span className="missing-tag">
                                <AlertTriangle size={12} />
                                Timing Missing
                              </span>
                            )}
                          </div>

                          <div className="profile-form-grid" style={{ marginTop: 4 }}>
                            <div className="form-field-group">
                              <label>Medicine Name</label>
                              <input
                                required
                                type="text"
                                value={med.medicine_name}
                                onChange={(e) => updateExtractedMed(idx, 'medicine_name', e.target.value)}
                                placeholder="e.g. Metformin"
                              />
                            </div>
                            <div className="form-field-group">
                              <label>Dose / Strength</label>
                              <input
                                type="text"
                                value={med.dose_text}
                                onChange={(e) => updateExtractedMed(idx, 'dose_text', e.target.value)}
                                placeholder="e.g. 500 mg"
                              />
                            </div>
                          </div>

                          <div className="form-field-group">
                            <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: isTimingMissing ? '#b45309' : 'inherit' }}>
                              <span>Schedule / Timing {isTimingMissing && '(Required — Missing in Prescription)'}</span>
                            </label>
                            <input
                              required
                              type="text"
                              className={isTimingMissing ? 'input-missing-highlight' : ''}
                              value={med.timing_text}
                              onChange={(e) => updateExtractedMed(idx, 'timing_text', e.target.value)}
                              placeholder="e.g. Morning after breakfast, or Twice daily with meals"
                            />
                          </div>

                          <div className="form-field-group">
                            <label>Instructions (Optional)</label>
                            <input
                              type="text"
                              value={med.instructions || ''}
                              onChange={(e) => updateExtractedMed(idx, 'instructions', e.target.value)}
                              placeholder="e.g. Take with a glass of water"
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {editableExtractedMeds.length > 0 && (
                  <button
                    className="primary-button"
                    style={{ width: '100%', marginTop: 14 }}
                    onClick={handleSaveAllExtracted}
                    disabled={isSubmitting || ocrSaveSuccess}
                  >
                    {ocrSaveSuccess ? (
                      <>
                        <Check size={20} />
                        <span>Saved to My Medications!</span>
                      </>
                    ) : isSubmitting ? (
                      'Saving Medications...'
                    ) : (
                      <>
                        <Check size={20} />
                        <span>Save All to My Medications</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Doctor Consultation & Email Approval Modal
   Strict Requirement: Email is never sent automatically.
   Always drafts clinical email, displays preview, and requires user consent.
------------------------------------------------------------- */
function DoctorConsultModal({
  patientProfile,
  role,
  onClose,
}: {
  patientProfile: PatientProfile | null
  role: 'patient' | 'caregiver'
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<'draft' | 'history'>('draft')
  const [healthIssue, setHealthIssue] = useState('')
  const [isDrafting, setIsDrafting] = useState(false)
  const [activeDraft, setActiveDraft] = useState<DoctorEmailItem | null>(null)
  const [dispatchedEmail, setDispatchedEmail] = useState<DoctorEmailItem | null>(null)
  const [isApproving, setIsApproving] = useState(false)
  const [history, setHistory] = useState<DoctorEmailItem[]>([])
  const [actionNotice, setActionNotice] = useState<string | null>(null)

  const doctorName = patientProfile?.doctor_name || 'Primary Care Doctor'
  const doctorEmail = patientProfile?.doctor_email || ''
  const patientEmail = patientProfile?.email || ''

  const loadHistory = async () => {
    try {
      const items = await getDoctorEmails()
      setHistory(items)
    } catch (e) {}
  }

  useEffect(() => {
    loadHistory()
  }, [])

  // Draft email strictly as status='draft'
  const handleDraftEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!healthIssue.trim()) return
    setIsDrafting(true)
    setActionNotice(null)

    try {
      const draft = await draftDoctorEmail({
        health_issue: healthIssue.trim(),
        doctor_name: doctorName,
        doctor_email: doctorEmail,
      })
      setActiveDraft(draft)
      loadHistory()
      speakText('I have drafted a concise clinical email for your doctor with your current health issue and prescription history. Please review the message below and tap approve to send.')
    } catch (err: any) {
      alert('Failed to draft doctor email. Please check network.')
    } finally {
      setIsDrafting(false)
    }
  }

  // 2. Explicit User Consent: Patient/Caregiver clicks Approve & Send
  const handleApprove = async () => {
    if (!activeDraft) return
    setIsApproving(true)
    try {
      const res = await approveDoctorEmail(activeDraft.id)
      const approvedItem = res.email_item || activeDraft
      const docEmail = approvedItem.doctor_email || doctorEmail
      const subj = approvedItem.subject
      const body = approvedItem.body

      // Prepare standard runtime Gmail Web compose & native Mail URL
      const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(docEmail)}&su=${encodeURIComponent(subj)}&body=${encodeURIComponent(body)}`
      const mailtoUrl = `mailto:${encodeURIComponent(docEmail)}?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(body)}`

      // Universal runtime dispatch for mobile and desktop
      const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)
      if (isMobile) {
        // Native deep link launches Gmail app or mobile email client directly from patient's account
        window.location.href = mailtoUrl
      } else {
        const opened = window.open(gmailUrl, '_blank')
        if (!opened) {
          window.location.href = mailtoUrl
        }
      }

      setDispatchedEmail(approvedItem)
      setActiveDraft(null)
      setHealthIssue('')
      setActionNotice(`✓ Clinical email approved! Dispatched to Dr. ${approvedItem.doctor_name} (${docEmail}).`)
      speakText(`Clinical email approved and dispatched to Dr. ${approvedItem.doctor_name}.`)
      loadHistory()
    } catch (err: any) {
      alert('Failed to dispatch email. Please check doctor email settings.')
    } finally {
      setIsApproving(false)
    }
  }

  // 3. User declines: Discard draft without sending
  const handleDecline = async () => {
    if (!activeDraft) return
    if (!confirm('Discard this clinical email draft? Nothing will be sent to your doctor.')) return
    try {
      await declineDoctorEmail(activeDraft.id)
      setActiveDraft(null)
      setActionNotice('Draft email discarded. No message was sent to your doctor.')
      speakText('Draft email discarded. No message was sent.')
      loadHistory()
    } catch (err) {}
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content doctor-modal-content" style={{ maxWidth: 640 }}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">CLINICAL ASSISTANT</p>
            <h2>Consult Doctor via Email</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            <X size={22} />
          </button>
        </div>

        {/* Tab switch */}
        <div className="ocr-mode-tabs">
          <button
            className={`ocr-mode-tab ${activeTab === 'draft' ? 'active' : ''}`}
            onClick={() => setActiveTab('draft')}
          >
            <Mail size={18} />
            <span>Draft Clinical Email</span>
          </button>
          <button
            className={`ocr-mode-tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            <Clock size={18} />
            <span>Communications History ({history.length})</span>
          </button>
        </div>

        {activeTab === 'draft' && (
          <div>
            {/* Doctor info banner */}
            <div style={{ background: '#f0f7f2', border: '1px solid var(--line)', borderRadius: 12, padding: '10px 14px', marginBottom: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong style={{ fontSize: '0.9rem', color: 'var(--ink)' }}>Primary Doctor: {doctorName}</strong>
                <p style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Recipient: {doctorEmail}</p>
              </div>
              <span className="email-status-badge sent">Verified Contact</span>
            </div>

            {actionNotice && (
              <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', padding: 12, borderRadius: 12, marginBottom: 14, fontSize: '0.9rem' }}>
                {actionNotice}
              </div>
            )}

            {dispatchedEmail && (
              <div className="email-dispatched-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#166534', fontWeight: 700, fontSize: '1.05rem', marginBottom: 6 }}>
                  <CheckCircle2 size={24} color="#16a34a" />
                  <span>Clinical Email Dispatched</span>
                </div>
                <p style={{ color: '#15803d', fontSize: '0.88rem', lineHeight: 1.45, marginBottom: 14 }}>
                  Your inquiry to <strong>Dr. {dispatchedEmail.doctor_name}</strong> ({dispatchedEmail.doctor_email}) has been authorized and opened in your email client. You can re-open or send it anytime using the options below:
                </p>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <a
                    href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(dispatchedEmail.doctor_email)}&su=${encodeURIComponent(dispatchedEmail.subject)}&body=${encodeURIComponent(dispatchedEmail.body)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="primary-button"
                    style={{ flex: 1, minWidth: 160, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, textDecoration: 'none', background: '#ea4335' }}
                  >
                    <Mail size={18} />
                    <span>Open in Gmail</span>
                    <ExternalLink size={14} />
                  </a>
                  <a
                    href={`mailto:${encodeURIComponent(dispatchedEmail.doctor_email)}?subject=${encodeURIComponent(dispatchedEmail.subject)}&body=${encodeURIComponent(dispatchedEmail.body)}`}
                    className="secondary-button"
                    style={{ flex: 1, minWidth: 160, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, textDecoration: 'none' }}
                  >
                    <Send size={18} />
                    <span>Send via Mail App</span>
                  </a>
                  <button
                    type="button"
                    className="secondary-button"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    onClick={() => {
                      navigator.clipboard.writeText(`To: ${dispatchedEmail.doctor_email}\nSubject: ${dispatchedEmail.subject}\n\n${dispatchedEmail.body}`)
                      alert('Email text copied to clipboard!')
                    }}
                  >
                    <Copy size={16} />
                    <span>Copy Text</span>
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setDispatchedEmail(null)}
                  style={{ marginTop: 12, background: 'transparent', color: '#15803d', fontWeight: 700, fontSize: '0.86rem', border: 'none', cursor: 'pointer', padding: 0 }}
                >
                  + Draft Another Email
                </button>
              </div>
            )}

            {!activeDraft ? (
              <form onSubmit={handleDraftEmail}>
                <label style={{ display: 'block', fontWeight: 700, fontSize: '0.88rem', marginBottom: 6 }}>
                  Describe Your Current Health Issue or Symptoms
                </label>
                <p className="muted" style={{ fontSize: '0.82rem', marginBottom: 8 }}>
                  e.g., “I have severe pain in my chest and feel dizzy”, or “My blood pressure is higher than usual today”. Your information will be used to prepare a professional clinical memo with your active medication list.
                </p>

                <textarea
                  required
                  rows={4}
                  value={healthIssue}
                  onChange={(e) => setHealthIssue(e.target.value)}
                  placeholder="Describe how you are feeling or what immediate advice/medicine you need from the doctor..."
                  style={{ width: '100%', padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line)', fontSize: '0.95rem' }}
                />

                <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                  <button
                    type="submit"
                    className="primary-button"
                    style={{ flex: 1 }}
                    disabled={isDrafting}
                  >
                    <FileText size={18} />
                    <span>{isDrafting ? 'Drafting Clinical Email...' : 'Draft Clinical Email for Doctor'}</span>
                  </button>
                </div>
              </form>
            ) : (
              /* Review & Approval Stage (Strict User Consent) */
              <div>
                {/* Critical Approval Notice */}
                <div className="email-consent-notice">
                  <ShieldCheck size={20} style={{ flexShrink: 0 }} />
                  <div>
                    <strong>Approval Required Before Sending</strong>
                    <div>This email will never be sent automatically. Review the details below and tap Approve when you are ready.</div>
                  </div>
                </div>

                <div className="email-preview-container">
                  <div className="email-preview-header">
                    <div className="email-header-row">
                      <strong>To:</strong>
                      <span>{activeDraft.doctor_name} &lt;{activeDraft.doctor_email}&gt;</span>
                    </div>
                    <div className="email-header-row">
                      <strong>From:</strong>
                      <span>{patientProfile?.display_name || 'Patient'} &lt;{activeDraft.patient_email || patientEmail}&gt;</span>
                    </div>
                    <div className="email-header-row">
                      <strong>Subject:</strong>
                      <span style={{ fontWeight: 600 }}>{activeDraft.subject}</span>
                    </div>
                  </div>

                  <div className="email-preview-body">
                    {activeDraft.body}
                  </div>
                </div>

                {/* Consent Action Buttons */}
                <div className="email-action-row">
                  <button
                    className="btn-approve-email"
                    onClick={handleApprove}
                    disabled={isApproving}
                  >
                    <Check size={20} />
                    <span>{isApproving ? 'Sending Email...' : '✓ Approve & Send to Doctor'}</span>
                  </button>
                  <button
                    className="btn-decline-email"
                    onClick={handleDecline}
                    disabled={isApproving}
                  >
                    <X size={20} />
                    <span>✕ Decline & Discard</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Communications History */}
        {activeTab === 'history' && (
          <div className="history-tab-pane">
            <p className="muted" style={{ marginBottom: 14 }}>
              Record of all clinical emails drafted, approved, and sent to your doctor.
            </p>

            {history.length === 0 ? (
              <div className="history-empty-state">
                <Mail size={36} className="history-empty-icon" />
                <p>No doctor communications yet.</p>
                <small>Draft an email about your health symptoms to see it recorded here.</small>
              </div>
            ) : (
              <div className="history-list-container">
                {history.map((item) => (
                  <div key={item.id} className="history-item-card">
                    <div className="history-item-header">
                      <div className="history-item-title-col">
                        <strong className="history-item-subject">{item.subject}</strong>
                        <div className="history-item-meta">
                          <span className="history-doctor-label">To: {item.doctor_name}</span>
                          <span className="history-divider">•</span>
                          <span className="history-email-text">{item.doctor_email}</span>
                          <span className="history-divider">•</span>
                          <span className="history-date-text">
                            {new Date(item.created_at).toLocaleDateString()} {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      </div>
                      <span className={`email-status-badge ${item.status}`}>
                        {item.status.toUpperCase()}
                      </span>
                    </div>

                    <div className="history-item-body">
                      <div className="history-field-row">
                        <span className="history-field-label">Health Issue:</span>
                        <span className="history-field-value">{item.health_issue}</span>
                      </div>
                      {item.prescriptions_summary && (
                        <div className="history-field-row" style={{ marginTop: 4 }}>
                          <span className="history-field-label">Medications Summary:</span>
                          <span className="history-field-value muted">{item.prescriptions_summary}</span>
                        </div>
                      )}
                      <div className="history-mail-preview">
                        <div className="history-mail-preview-label">
                          <Mail size={14} />
                          Message preview
                        </div>
                        <p>{item.body}</p>
                      </div>
                    </div>

                    <div className="history-item-actions">
                      <a
                        href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(item.doctor_email)}&su=${encodeURIComponent(item.subject)}&body=${encodeURIComponent(item.body)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="icon-button"
                        style={{ textDecoration: 'none', fontSize: '0.8rem', padding: '6px 12px', background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' }}
                      >
                        <Mail size={14} />
                        <span>Send / Open in Gmail</span>
                        <ExternalLink size={12} />
                      </a>
                      <a
                        href={`mailto:${encodeURIComponent(item.doctor_email)}?subject=${encodeURIComponent(item.subject)}&body=${encodeURIComponent(item.body)}`}
                        className="icon-button"
                        style={{ textDecoration: 'none', fontSize: '0.8rem', padding: '6px 12px' }}
                      >
                        <Send size={14} />
                        <span>Mail App</span>
                      </a>
                      <button
                        type="button"
                        className="icon-button"
                        style={{ fontSize: '0.8rem', padding: '6px 12px' }}
                        onClick={() => {
                          navigator.clipboard.writeText(`To: ${item.doctor_email}\nSubject: ${item.subject}\n\n${item.body}`)
                          alert('Email text copied to clipboard!')
                        }}
                      >
                        <Copy size={14} />
                        <span>Copy</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Patient Profile & Doctor Setup Modal
   Configures personal Gmail and Primary Care Doctor info
------------------------------------------------------------- */
function PatientProfileModal({
  profile,
  onSwitchAccount,
  onClose,
}: {
  profile: PatientProfile | null
  onSwitchAccount?: () => void
  onClose: () => void
}) {
  const [displayName, setDisplayName] = useState(profile?.display_name || '')
  const [email, setEmail] = useState(profile?.email || '')
  const [phone, setPhone] = useState(profile?.phone || '')
  const [age, setAge] = useState(profile?.age ? String(profile.age) : '')
  const [emergencyContact, setEmergencyContact] = useState(profile?.emergency_contact_name || '')
  const [doctorName, setDoctorName] = useState(profile?.doctor_name || '')
  const [doctorEmail, setDoctorEmail] = useState(profile?.doctor_email || '')
  const [doctorSpecialty, setDoctorSpecialty] = useState(profile?.doctor_specialty || '')
  const [doctorPhone, setDoctorPhone] = useState(profile?.doctor_phone || '')
  const [isSaving, setIsSaving] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      await updatePatientProfile({
        display_name: displayName.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        age: age.trim() ? parseInt(age.trim(), 10) : undefined,
        emergency_contact_name: emergencyContact.trim() || undefined,
        doctor_name: doctorName.trim() || undefined,
        doctor_email: doctorEmail.trim() || undefined,
        doctor_specialty: doctorSpecialty.trim() || undefined,
        doctor_phone: doctorPhone.trim() || undefined,
      })
      localStorage.setItem('patient_display_name', displayName.trim())
      setSavedSuccess(true)
      speakText('Profile and doctor settings saved.')
      setTimeout(() => {
        onClose()
      }, 700)
    } catch (err) {
      alert('Failed to save profile. Please try again.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: 580 }}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">ACCOUNT & CLINICAL DIRECTORY</p>
            <h2>Patient Profile & Doctor Setup</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            <X size={22} />
          </button>
        </div>

        <p className="muted" style={{ marginBottom: 14 }}>
          Enter your personal email and your primary doctor's Gmail so you can prepare clinical updates when you have symptoms.
        </p>

        <form onSubmit={handleSave}>
          <div className="form-section-title">
            <User size={18} />
            <span>Personal Information</span>
          </div>

          <div className="profile-form-grid">
            <div className="form-field-group">
              <label>Patient Full Name</label>
              <input
                required
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="e.g. Robert Jenkins"
              />
            </div>
            <div className="form-field-group">
              <label>Personal Gmail / Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="robert.jenkins@gmail.com"
              />
            </div>
            <div className="form-field-group">
              <label>Phone Number</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="e.g. +1 (555) 349-8201"
              />
            </div>
            <div className="form-field-group">
              <label>Age</label>
              <input
                type="number"
                min={1}
                max={120}
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="e.g. 72"
              />
            </div>
            <div className="form-field-group" style={{ gridColumn: 'span 2' }}>
              <label>Emergency Family Contact</label>
              <input
                type="text"
                value={emergencyContact}
                onChange={(e) => setEmergencyContact(e.target.value)}
                placeholder="e.g. Mary Jenkins (Daughter) - +1 (555) 349-8209"
              />
            </div>
          </div>

          <div className="form-section-title">
            <Stethoscope size={18} />
            <span>Primary Care Doctor</span>
          </div>

          <div className="profile-form-grid">
            <div className="form-field-group">
              <label>Doctor's Name</label>
              <input
                required
                type="text"
                value={doctorName}
                onChange={(e) => setDoctorName(e.target.value)}
                placeholder="e.g. Dr. Sarah Mitchell"
              />
            </div>
            <div className="form-field-group">
              <label>Doctor's Gmail Address</label>
              <input
                required
                type="email"
                value={doctorEmail}
                onChange={(e) => setDoctorEmail(e.target.value)}
                placeholder="dr.mitchell@gmail.com"
              />
            </div>
            <div className="form-field-group">
              <label>Specialty</label>
              <input
                type="text"
                value={doctorSpecialty}
                onChange={(e) => setDoctorSpecialty(e.target.value)}
                placeholder="e.g. Cardiologist, GP"
              />
            </div>
            <div className="form-field-group">
              <label>Clinic Phone (Optional)</label>
              <input
                type="tel"
                value={doctorPhone}
                onChange={(e) => setDoctorPhone(e.target.value)}
                placeholder="e.g. +1 (555) 234-5678"
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 22 }}>
            <button
              type="submit"
              disabled={isSaving}
              style={{
                flex: 1,
                minHeight: 48,
                background: savedSuccess ? '#15803d' : 'var(--green)',
                color: '#fff',
                borderRadius: 14,
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
              }}
            >
              {savedSuccess ? (
                <>
                  <Check size={18} /> Saved Successfully
                </>
              ) : isSaving ? (
                'Saving Profile...'
              ) : (
                'Save Profile & Settings'
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              style={{
                minHeight: 48,
                background: '#f3f4f6',
                color: '#374151',
                borderRadius: 14,
                padding: '0 20px',
                fontWeight: 700,
              }}
            >
              Cancel
            </button>
          </div>

          {onSwitchAccount && (
            <div
              style={{
                marginTop: 22,
                paddingTop: 16,
                borderTop: '1px solid var(--line)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 10,
              }}
            >
              <div>
                <p style={{ fontWeight: 700, fontSize: '0.86rem', margin: 0, color: 'var(--ink)' }}>
                  Switch Account or Register New User?
                </p>
                <small className="muted">Clears local device profile so you can register a new patient</small>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm('Are you sure you want to sign out and register a new user profile?')) {
                    onSwitchAccount()
                  }
                }}
                style={{
                  background: '#fff',
                  color: '#dc2626',
                  border: '1.5px solid #fca5a5',
                  borderRadius: 10,
                  padding: '7px 14px',
                  fontSize: '0.82rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Sign Out / Register New User
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Professional Startup Splash Loading Screen
------------------------------------------------------------- */
function SplashScreen() {
  return (
    <div className="splash-screen" role="dialog" aria-modal="true" aria-label="Starting health companion">
      <div className="splash-logo-container">
        <div className="splash-pulse-ring" />
        <div className="splash-logo-circle">
          <HeartPulse size={44} strokeWidth={2.2} />
        </div>
      </div>
      <div className="splash-title">Sehat Saathi</div>
      <div className="splash-subtitle">Your Gentle Health Companion</div>
      <div className="splash-progress-track">
        <div className="splash-progress-bar" />
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   QR Scanner Modal for Caregiver Pairing (Camera + Fallback)
------------------------------------------------------------- */
function QRScannerModal({
  onScanSuccess,
  onClose,
}: {
  onScanSuccess: (scannedText: string) => void
  onClose: () => void
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [isScanning, setIsScanning] = useState(true)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    let active = true

    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        })
        if (!active) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
      } catch (err: any) {
        console.warn('Camera error:', err)
        setErrorMsg('Camera access is unavailable or was denied. You can still scan by uploading an image of the QR code below.')
      }
    }

    startCamera()

    return () => {
      active = false
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  // Continuous frame analysis with jsQR
  useEffect(() => {
    let timer: any = null

    const checkFrame = () => {
      if (!isScanning) return
      const video = videoRef.current
      if (video && video.readyState === video.HAVE_ENOUGH_DATA) {
        let canvas = canvasRef.current
        if (!canvas) {
          canvas = document.createElement('canvas')
          canvasRef.current = canvas
        }
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height)
          const code = jsQR(imgData.data, imgData.width, imgData.height, {
            inversionAttempts: 'dontInvert',
          })
          if (code && code.data) {
            setIsScanning(false)
            if (streamRef.current) {
              streamRef.current.getTracks().forEach((t) => t.stop())
            }
            onScanSuccess(code.data)
            return
          }
        }
      }
      timer = setTimeout(checkFrame, 200)
    }

    timer = setTimeout(checkFrame, 300)
    return () => {
      if (timer) clearTimeout(timer)
    }
  }, [isScanning, onScanSuccess])

  // Fallback: Pick or capture image file
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = img.width
        canvas.height = img.height
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.drawImage(img, 0, 0)
          const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height)
          const code = jsQR(imgData.data, imgData.width, imgData.height)
          if (code && code.data) {
            onScanSuccess(code.data)
          } else {
            alert('Could not find a valid pairing QR code in this image. Please ensure the code is clear and well-lit.')
          }
        }
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: 440, textAlign: 'center' }}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">CAREGIVER CAMERA SCANNER</p>
            <h2>Scan Patient QR Code</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close scanner">
            <X size={22} />
          </button>
        </div>

        <p className="muted" style={{ fontSize: '0.88rem', margin: '4px 0 16px 0' }}>
          Point your device camera at the QR code displayed on the patient’s phone screen.
        </p>

        {errorMsg ? (
          <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', padding: 14, borderRadius: 12, marginBottom: 16, fontSize: '0.88rem' }}>
            {errorMsg}
          </div>
        ) : (
          <div style={{ position: 'relative', width: '100%', height: 260, borderRadius: 16, overflow: 'hidden', background: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <video
              ref={videoRef}
              playsInline
              autoPlay
              muted
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
            {/* Viewfinder Reticle */}
            <div style={{
              position: 'absolute',
              width: 180,
              height: 180,
              border: '3px solid #22c55e',
              borderRadius: 16,
              boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.45)',
              pointerEvents: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 2,
                background: '#4ade80',
                boxShadow: '0 0 10px #22c55e',
                animation: 'scannerLine 2s linear infinite'
              }} />
            </div>
          </div>
        )}

        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label className="icon-button" style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '10px 14px' }}>
            <Upload size={18} />
            <span>Upload QR Image Instead</span>
            <input
              type="file"
              accept="image/*"
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Caregiver Screen (UX-35 to UX-38, UX-43, UX-44)
------------------------------------------------------------- */
function CaregiverScreen({
  onSwitchToPatient,
  patientProfile,
  activeEmergencyAlert,
  setActiveEmergencyAlert,
  onTriggerSiren,
  onSilenceSiren,
  onMarkHandled,
  onDoctorClick,
  onProfileClick,
}: {
  onSwitchToPatient: () => void
  patientProfile?: PatientProfile | null
  activeEmergencyAlert: { id: number; transcript: string; created_at: string } | null
  setActiveEmergencyAlert: (alert: any) => void
  onTriggerSiren: (alert: any) => void
  onSilenceSiren: () => void
  onMarkHandled: (id: number) => void
  onDoctorClick?: () => void
  onProfileClick?: () => void
}) {
  const [token, setToken] = useState<string>(() => getCaregiverToken())
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [showRxModal, setShowRxModal] = useState(false)
  const [showScanner, setShowScanner] = useState(false)

  // Pairing Entry State
  const [pairKey, setPairKey] = useState('')
  const [caregiverName, setCaregiverName] = useState('Sarah Khan')
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [pairStatusMsg, setPairStatusMsg] = useState('')
  const [isRedeeming, setIsRedeeming] = useState(false)

  const [handlingAlertId, setHandlingAlertId] = useState<number | null>(null)
  const [confirmAlertId, setConfirmAlertId] = useState<number | null>(null)
  const [handledMessage, setHandledMessage] = useState('')

  // Handle scanned QR Code from camera or upload
  const handleQrScanned = async (scannedCode: string) => {
    setShowScanner(false)
    let code = scannedCode.replace(/^sehat-pair:/i, '').trim().toUpperCase()
    const match = code.match(/([A-Z0-9]{4})-?([A-Z0-9]{4})/)
    if (match) {
      code = `${match[1]}-${match[2]}`
    }
    setPairKey(code)
    speakText('QR code scanned. Connecting to patient...')

    const nameToUse = caregiverName.trim() || 'Family Caregiver'
    if (!caregiverName.trim()) {
      setCaregiverName('Family Caregiver')
    }

    setIsRedeeming(true)
    setPairStatusMsg('Submitting scanned pairing key...')
    try {
      const res = await redeemPairingKey(code.trim(), nameToUse)
      setPendingId(res.pending_id)
      setPairStatusMsg('Waiting for patient to approve on their phone...')
    } catch (err: any) {
      setPairStatusMsg(err.message || 'Key is incorrect or expired.')
    } finally {
      setIsRedeeming(false)
    }
  }

  // Load Dashboard Data
  const loadDashboard = async () => {
    try {
      const data = await getCaregiverDashboard()
      setDashboard(data)
    } catch (err: any) {
      if (err.message === 'REVOKED') {
        setToken('')
        alert('Your connection to the patient has been revoked.')
      }
    }
  }

  // Periodic Polling
  useEffect(() => {
    if (!token) return
    loadDashboard()
    const interval = setInterval(loadDashboard, 5000)
    return () => clearInterval(interval)
  }, [token])

  // Real-Time Server-Sent Events (SSE) Stream
  useEffect(() => {
    if (!token) return

    const eventSource = new EventSource(`${API_BASE}/api/caregiver/events?token=${token}`)

    const handleEmergencyAlert = (raw: any) => {
      const alertData = {
        id: raw.alert_id || raw.id,
        transcript: raw.transcript_excerpt || raw.transcript || 'Emergency reported',
        created_at: raw.timestamp || new Date().toISOString(),
      }
      onTriggerSiren(alertData)
      speakText(`Emergency alert from patient! Patient reported: ${alertData.transcript}`)
      loadDashboard()
    }

    eventSource.addEventListener('emergency_buzzer', (e) => {
      try {
        const raw = JSON.parse(e.data)
        handleEmergencyAlert(raw)
      } catch (err) {
        console.error('Failed to parse emergency buzzer event:', err)
      }
    })

    // Also handle fallback message events
    eventSource.onmessage = (e) => {
      try {
        const raw = JSON.parse(e.data)
        if (raw.event === 'emergency_buzzer' || raw.data?.alert_type === 'RED_FLAG' || raw.alert_type === 'RED_FLAG') {
          handleEmergencyAlert(raw.data || raw)
        }
      } catch (err) {}
    }

    eventSource.addEventListener('prescription_updated', () => {
      loadDashboard()
    })

    eventSource.onerror = () => {
      // EventSource auto reconnects
    }

    return () => {
      eventSource.close()
    }
  }, [token])

  // Caregiver Key Submit (UX-43)
  const handleRedeemKey = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!pairKey.trim() || !caregiverName.trim()) return

    setIsRedeeming(true)
    setPairStatusMsg('Submitting key...')
    try {
      const res = await redeemPairingKey(pairKey.trim(), caregiverName.trim())
      setPendingId(res.pending_id)
      setPairStatusMsg('Waiting for patient to approve on their phone...')
    } catch (err: any) {
      setPairStatusMsg(err.message || 'Key is incorrect or expired.')
    } finally {
      setIsRedeeming(false)
    }
  }

  // Poll for Approval Status
  useEffect(() => {
    if (!pendingId) return
    const poll = setInterval(async () => {
      try {
        const res = await checkPairStatus(pendingId)
        if (res.status === 'approved' && res.session_token) {
          clearInterval(poll)
          setCaregiverToken(res.session_token)
          setToken(res.session_token)
          setPendingId(null)
          setPairStatusMsg('')
        } else if (res.status === 'declined') {
          clearInterval(poll)
          setPendingId(null)
          setPairStatusMsg('Patient declined the link request.')
        }
      } catch (e) {}
    }, 2000)
    return () => clearInterval(poll)
  }, [pendingId])

  const handleCaregiverMarkHandled = async (alertId: number) => {
    if (handlingAlertId !== null) return
    setHandlingAlertId(alertId)
    setHandledMessage('')
    try {
      await onMarkHandled(alertId)
      setDashboard((current) => current ? {
        ...current,
        alerts: current.alerts.filter((alert) => alert.id !== alertId),
        summary: {
          ...current.summary,
          open_alerts_count: Math.max(0, current.summary.open_alerts_count - 1),
        },
      } : current)
      setActiveEmergencyAlert((current: { id: number; transcript: string; created_at: string } | null) =>
        current?.id === alertId ? null : current
      )
      setHandledMessage('Emergency alert marked as handled.')
      setConfirmAlertId(null)
      await loadDashboard()
    } catch (error) {
      setHandledMessage(error instanceof Error ? error.message : 'Could not mark the alert as handled.')
    } finally {
      setHandlingAlertId(null)
    }

  }

  const requestMarkHandled = (alertId: number) => {
    if (handlingAlertId === null) {
      setHandledMessage('')
      setConfirmAlertId(alertId)
    }
  }

  // 1. Caregiver Key Entry Screen (UX-43)
  if (!token) {
    return (
      <main className="center-page caregiver-connect-page">
        <div className="brand" style={{ marginBottom: 20 }}>
          <span className="brand-mark"><HeartPulse size={22} /></span>
          <span>Sehat Saathi · Caregiver Portal</span>
        </div>
        <h1>Connect with Patient</h1>
        <p className="muted" style={{ maxWidth: 460, marginTop: 10 }}>
          Scan the QR code on the patient's phone screen or enter their 8-character pairing code.
        </p>

        {/* Quick QR Scanner Option */}
        <div style={{ width: '100%', maxWidth: 440, marginTop: 20 }}>
          <button
            type="button"
            className="primary-button"
            onClick={() => setShowScanner(true)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, background: 'var(--green-dark)', padding: '14px 18px', borderRadius: 14 }}
          >
            <Camera size={22} />
            <span>Scan Patient QR Code to Link</span>
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', maxWidth: 440, margin: '18px 0 6px 0', color: 'var(--muted)', fontSize: '0.82rem' }}>
          <hr style={{ flex: 1, border: 'none', borderTop: '1.5px solid var(--line)' }} />
          <span>OR ENTER CODE MANUALLY</span>
          <hr style={{ flex: 1, border: 'none', borderTop: '1.5px solid var(--line)' }} />
        </div>

        <form onSubmit={handleRedeemKey} style={{ width: '100%', maxWidth: 440, marginTop: 10, display: 'grid', gap: 14 }}>
          <label style={{ textAlign: 'left', fontWeight: 700, fontSize: '0.85rem' }}>
            Your Name
            <input
              required
              type="text"
              placeholder="e.g. Sarah Khan"
              value={caregiverName}
              onChange={(e) => setCaregiverName(e.target.value)}
              style={{ width: '100%', minHeight: 56, marginTop: 6, padding: '12px 16px', borderRadius: 14, border: '2px solid var(--line)' }}
            />
          </label>

          <label style={{ textAlign: 'left', fontWeight: 700, fontSize: '0.85rem' }}>
            8-Character Pairing Code
            <input
              required
              type="text"
              maxLength={9}
              placeholder="e.g. A3F9-7C21"
              value={pairKey}
              onChange={(e) => setPairKey(e.target.value.toUpperCase())}
              style={{ width: '100%', minHeight: 56, marginTop: 6, padding: '12px 16px', borderRadius: 14, border: '2px solid var(--line)', fontFamily: 'monospace', fontSize: '1.2rem', textAlign: 'center' }}
            />
          </label>

          {pairStatusMsg && (
            <p style={{ color: pendingId ? 'var(--green-dark)' : 'var(--crimson)', fontWeight: 700, fontSize: '0.9rem' }}>
              {pairStatusMsg}
            </p>
          )}

          <button
            type="submit"
            disabled={isRedeeming || pendingId !== null}
            className="primary-button"
            style={{ marginTop: 10 }}
          >
            {isRedeeming ? 'Connecting...' : 'Link to Patient'}
          </button>

          <button
            type="button"
            onClick={onSwitchToPatient}
            style={{ background: 'transparent', color: 'var(--muted)', marginTop: 10, fontWeight: 700 }}
          >
            Switch to Patient Mode
          </button>
        </form>

        {showScanner && (
          <QRScannerModal
            onScanSuccess={handleQrScanned}
            onClose={() => setShowScanner(false)}
          />
        )}
      </main>
    )
  }

  // 2. Caregiver Dashboard View (UX-35 to UX-38)
  return (
    <main className="page caregiver-page">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><HeartPulse size={22} /></span>
          <span>Sehat Saathi · Caregiver</span>
        </div>
        <div className="header-actions">
          <button className="icon-button" onClick={() => setShowRxModal(true)} aria-label="Prescriptions">
            <Pill size={18} />
            <span>Prescriptions</span>
          </button>
          {onDoctorClick && (
            <button className="icon-button" onClick={onDoctorClick} aria-label="Consult Doctor">
              <Mail size={18} />
              <span>Doctor</span>
            </button>
          )}
          {onProfileClick && (
            <button className="icon-button" onClick={onProfileClick} aria-label="Settings">
              <User size={18} />
              <span>Settings</span>
            </button>
          )}
          <button className="icon-button" onClick={() => setShowScanner(true)} aria-label="Scan Patient QR Code">
            <QrCode size={18} />
            <span>Pair QR</span>
          </button>
          <button className="icon-button" onClick={onSwitchToPatient} aria-label="Switch to Patient Mode">
            <HeartPulse size={18} />
            <span>Patient</span>
          </button>
        </div>
      </header>

      {/* Real-time Emergency Siren Takeover Banner */}
      {activeEmergencyAlert && (
        <div className="siren-takeover">
          <h2>
            <AlertTriangle size={28} />
            <span>EMERGENCY ALERT: Heart / Red-Flag Detected!</span>
          </h2>
          <p style={{ marginTop: 8, fontSize: '1.05rem', color: '#fee2e2' }}>
            Patient words: <strong>“{activeEmergencyAlert.transcript}”</strong>
          </p>
          <div className="siren-actions">
            <button className="btn-silence" onClick={onSilenceSiren}>
              <VolumeX size={20} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Silence Siren
            </button>
            <button
              className="btn-handled"
              onClick={() => requestMarkHandled(activeEmergencyAlert.id)}
              disabled={handlingAlertId === activeEmergencyAlert.id}
            >
              <Check size={20} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              {handlingAlertId === activeEmergencyAlert.id ? 'Handling...' : 'Mark as Handled'}
            </button>
          </div>
          {confirmAlertId === activeEmergencyAlert.id && (
            <div className="handled-confirmation" role="alertdialog" aria-live="polite">
              <strong>Can you really mark this issue as handled?</strong>
              <div className="handled-confirmation-actions">
                <button
                  type="button"
                  onClick={() => handleCaregiverMarkHandled(activeEmergencyAlert.id)}
                >
                  Yes, mark handled
                </button>
                <button type="button" onClick={() => setConfirmAlertId(null)}>
                  No, keep alert
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Patient Overview Hero (UX-35) */}
      <section className="caregiver-hero">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <p className="eyebrow">MONITORING PATIENT</p>
            <h1 style={{ fontSize: '1.8rem' }}>{dashboard?.summary.patient_display_name || 'Robert Jenkins'}</h1>
          </div>
          <div className="status-pill">
            <span className="status-dot-inner" />
            <span>Live Stream Active</span>
          </div>
        </div>

        {/* Doctor Contact Chip */}
        {patientProfile?.doctor_name && (
          <div style={{ marginTop: 12, padding: '8px 14px', background: '#ffffff', borderRadius: 12, display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', border: '1px solid var(--line)' }}>
            <Stethoscope size={16} color="var(--green)" />
            <span>Primary Doctor: <strong>{patientProfile.doctor_name}</strong> ({patientProfile.doctor_email || 'dr.mitchell@clinic.com'})</span>
            {onDoctorClick && (
              <button
                onClick={onDoctorClick}
                style={{ marginLeft: 8, color: 'var(--green-dark)', fontWeight: 700, background: '#f0f7f2', padding: '4px 10px', borderRadius: 8 }}
              >
                Draft Email &rarr;
              </button>
            )}
          </div>
        )}

        {/* Stats Grid */}
        <div className="stats-grid">
          <div className="stat-card alert-stat">
            <strong>{dashboard?.summary.open_alerts_count || 0}</strong>
            <small>Open Alerts</small>
          </div>
          <div className="stat-card">
            <strong>{dashboard?.summary.reminders_taken_today || 0}</strong>
            <small>Pills Taken Today</small>
          </div>
          <div className="stat-card">
            <strong>{dashboard?.summary.reminders_missed_today || 0}</strong>
            <small>Pills Missed</small>
          </div>
        </div>
      </section>

      {handledMessage && (
        <p className="caregiver-action-message" role="status">{handledMessage}</p>
      )}

      {/* High-Priority Emergency Alerts Section (UX-36) */}
      <div className="section-title">
        <h2>Emergency & Red-Flag Alerts</h2>
      </div>
      {(!dashboard?.alerts || dashboard.alerts.length === 0) ? (
        <p className="muted" style={{ fontStyle: 'italic', marginBottom: 20 }}>No unhandled emergency alerts.</p>
      ) : (
        dashboard.alerts.map((alert) => (
          <div key={alert.id} className="alert-card-caregiver">
            <div className="time">Alert #{alert.id} · {new Date(alert.created_at).toLocaleTimeString()}</div>
            <div className="words">“{alert.transcript_excerpt}”</div>
            <p style={{ fontSize: '0.85rem', color: '#991b1b' }}>Action: {alert.action_taken}</p>
            <button
              onClick={() => requestMarkHandled(alert.id)}
              disabled={handlingAlertId === alert.id}
              style={{ marginTop: 12, minHeight: 44, padding: '8px 16px', background: 'var(--green)', color: '#fff', borderRadius: 10, fontWeight: 700 }}
            >
              {handlingAlertId === alert.id ? 'Handling...' : '✓ Mark Handled'}
            </button>
            {confirmAlertId === alert.id && (
              <div className="handled-confirmation" role="alertdialog" aria-live="polite">
                <strong>Can you really mark this issue as handled?</strong>
                <div className="handled-confirmation-actions">
                  <button type="button" onClick={() => handleCaregiverMarkHandled(alert.id)}>
                    Yes, mark handled
                  </button>
                  <button type="button" onClick={() => setConfirmAlertId(null)}>
                    No, keep alert
                  </button>
                </div>
              </div>
            )}
          </div>
        ))
      )}

      {/* Medication & Reminders Schedule */}
      <div className="section-title">
        <h2>Active Reminders</h2>
        <button
          onClick={() => setShowRxModal(true)}
          style={{ minHeight: 44, padding: '6px 14px', background: '#eef7ed', color: 'var(--green-dark)', borderRadius: 10, fontWeight: 700 }}
        >
          + Add Prescription
        </button>
      </div>
      {(!dashboard?.reminders || dashboard.reminders.length === 0) ? (
        <p className="muted" style={{ fontStyle: 'italic', marginBottom: 20 }}>No active medication reminders.</p>
      ) : (
        dashboard.reminders.map((rem) => (
          <div key={rem.id} className="rx-card">
            <div>
              <strong>{rem.medicine_name} <span className="rx-dose-tag">{rem.dose_text}</span></strong>
              <p>{rem.timing_text}</p>
            </div>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--green)' }}>Active</span>
          </div>
        ))
      )}

      {/* Upcoming Appointments */}
      <div className="section-title">
        <h2>Next Appointments</h2>
      </div>
      {(!dashboard?.appointments || dashboard.appointments.length === 0) ? (
        <p className="muted" style={{ fontStyle: 'italic', marginBottom: 20 }}>No scheduled appointments.</p>
      ) : (
        dashboard.appointments.map((app) => (
          <div key={app.id} className="rx-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Calendar size={22} color="var(--green)" />
              <div>
                <strong>Clinic Visit</strong>
                <p>{app.slot_start}</p>
              </div>
            </div>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--green)' }}>Confirmed</span>
          </div>
        ))
      )}

      {/* Prescription Management Modal for Caregiver */}
      {showRxModal && (
        <PrescriptionsModal
          role="caregiver"
          onClose={() => {
            setShowRxModal(false)
            loadDashboard()
          }}
        />
      )}

      {showScanner && (
        <QRScannerModal
          onScanSuccess={handleQrScanned}
          onClose={() => setShowScanner(false)}
        />
      )}
    </main>
  )
}

/* -------------------------------------------------------------
   Conversation History & Medication Context Modal
------------------------------------------------------------- */
function MemoryModal({
  onClose,
  onTestQuery
}: {
  onClose: () => void
  onTestQuery: (q: string) => void
}) {
  const [memories, setMemories] = useState<PatientMemoryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const data = await getPatientMemories(15)
      setMemories(data)
      setLoading(false)
    }
    load()
  }, [])

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Conversation and Medication History">
      <div className="modal-content memory-modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ background: 'var(--mint)', color: 'var(--green-dark)', padding: 10, borderRadius: 12, display: 'grid', placeItems: 'center' }}>
              <History size={24} />
            </span>
            <div>
              <p className="eyebrow" style={{ margin: 0 }}>CONTEXT & CARE MEMORY</p>
              <h2 style={{ fontSize: '1.25rem', margin: 0 }}>Conversation & Care History</h2>
            </div>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close history modal">
            <X size={20} />
          </button>
        </div>

        <div className="history-explainer-banner">
          <Clock size={18} style={{ flexShrink: 0, marginTop: 2, color: 'var(--green)' }} />
          <span>
            Sehat Saathi retains your past questions, symptom reports, and medicine confirmations so clinical recommendations stay coherent across conversations.
          </span>
        </div>

        {/* Quick query chips */}
        <div style={{ margin: '14px 0 16px' }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--ink)', display: 'block', marginBottom: 8 }}>
            Quick memory checks:
          </span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="history-chip-btn"
              onClick={() => { onClose(); onTestQuery('Did I take my medicine today?'); }}
            >
              "Did I take my medicine today?"
            </button>
            <button
              type="button"
              className="history-chip-btn"
              onClick={() => { onClose(); onTestQuery('What did the doctor say about my diet?'); }}
            >
              "What did the doctor say about my diet?"
            </button>
          </div>
        </div>

        {/* List of memory items */}
        <div className="history-list-container">
          {loading ? (
            <div className="history-empty-state">
              <RefreshCw className="spin" size={28} />
              <p>Loading conversation memory...</p>
            </div>
          ) : memories.length === 0 ? (
            <div className="history-empty-state">
              <History size={36} className="history-empty-icon" />
              <p>No conversation history recorded yet.</p>
              <small>Ask a health question or record medication intake to begin building your care memory timeline.</small>
            </div>
          ) : (
            memories.map((m, idx) => (
              <div key={m.id || idx} className="memory-history-card">
                <div className="memory-card-header">
                  <span className={`memory-intent-tag ${m.intent || 'general'}`}>
                    {(m.intent || 'general').toUpperCase()}
                  </span>
                  <span className="memory-time-tag">
                    {m.created_at ? new Date(m.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : ''}
                  </span>
                </div>
                <div className="memory-user-query">
                  <span className="memory-speaker-label">Patient:</span>
                  <span className="memory-query-text">"{m.user_query}"</span>
                </div>
                <div className="memory-assistant-response">
                  <span className="memory-assistant-label">Care note:</span>
                  <span className="memory-response-text">{m.assistant_response}</span>
                </div>
              </div>
            ))
          )}
        </div>

        <div style={{ marginTop: 20 }}>
          <button type="button" className="primary-button" onClick={onClose} style={{ minHeight: 48, fontSize: '0.95rem' }}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------
   Persistent Accessibility Bar (UX-02, UX-04)
------------------------------------------------------------- */
function AccessibilityBar({
  textSize,
  setTextSize,
  highContrast,
  setHighContrast,
  currentScreen,
  showRoleSwitch = true,
  onSwitchRole,
}: {
  textSize: TextSize
  setTextSize: (size: TextSize) => void
  highContrast: boolean
  setHighContrast: (v: boolean) => void
  currentScreen: Screen
  showRoleSwitch?: boolean
  onSwitchRole: () => void
}) {
  const cycleTextSize = () => {
    if (textSize === 'normal') setTextSize('large')
    else if (textSize === 'large') setTextSize('extra')
    else setTextSize('normal')
  }

  return (
    <nav className="accessibility-bar" aria-label="Accessibility settings">
      <button onClick={cycleTextSize} aria-label={`Current text size: ${textSize}. Tap to enlarge.`}>
        <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>A</span>
        <span style={{ fontSize: '1.15rem', fontWeight: 800 }}>A+</span>
        <span style={{ fontSize: '0.75rem', marginLeft: 4 }}>({textSize})</span>
      </button>

      <button
        className={highContrast ? 'selected' : ''}
        onClick={() => setHighContrast(!highContrast)}
        aria-label="Toggle high contrast mode"
      >
        <Settings size={16} />
        <span>Contrast</span>
      </button>

      {showRoleSwitch && (
        <button onClick={onSwitchRole} aria-label="Switch between patient and caregiver mode">
          <Users size={16} />
          <span>{currentScreen === 'caregiver' ? 'Patient' : 'Caregiver'}</span>
        </button>
      )}
    </nav>
  )
}
