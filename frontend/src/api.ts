/**
 * Sehat Saathi API Client.
 * Interfaces with the FastAPI backend at http://localhost:8000.
 */

export const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000'

export interface TurnResponse {
  transcript: string
  answer: string
  source_line: string | null
  cited_line_ids: string[]
  confidence: number
  confidence_badge: 'Certain' | 'Possibly' | 'Unknown'
  audio_url: string | null
  ui_state: 'listening' | 'thinking' | 'speaking' | 'waiting_confirmation' | 'emergency' | 'handoff'
  echo_back: string | null
  pending_action_id: string | null
  is_emergency: boolean
  emergency_action_taken: string | null
  tool_called?: string | null
  email_draft?: DoctorEmailItem | null
  alert_info?: Record<string, any> | null
}

export interface ConfirmResponse {
  status: 'confirmed' | 'rejected' | 'expired'
  message: string
  details?: Record<string, any> | null
}

export interface PrescriptionItem {
  id: number
  patient_id: string
  added_by: string
  author_name: string
  medicine_name: string
  dose_text: string
  timing_text: string
  instructions: string
  is_active: boolean
  created_at: string
}

export interface DashboardResponse {
  summary: {
    patient_display_name: string
    open_alerts_count: number
    review_items_count: number
    reminders_taken_today: number
    reminders_missed_today: number
    reminders_pending_today: number
    next_appointment: string
  }
  alerts: Array<{
    id: number
    type: string
    priority: string
    transcript_excerpt: string
    action_taken: string
    created_at: string
    handled_at: string | null
  }>
  review_queue: Array<{
    id: number
    question: string
    attempted_answer: string
    reason: string
    clinician_note: string | null
    status: string
    created_at: string
  }>
  reminders: Array<{
    id: number
    medicine_name: string
    dose_text: string
    timing_text: string
    status: string
  }>
  appointments: Array<{
    id: number
    slot_start: string
    status: string
  }>
}

export interface PairCreateResponse {
  key: string
  formatted_key: string
  expires_in_seconds: number
  expires_at: string
}

export interface PairPendingItem {
  pending_id: number
  caregiver_name: string
  created_at: string
}

export interface CaregiverLinkItem {
  link_id: number
  caregiver_name: string
  linked_at: string
  is_active: boolean
}

// Token storage helpers
export const getPatientToken = () => localStorage.getItem('patient_device_token') || ''
export const setPatientToken = (token: string) => localStorage.setItem('patient_device_token', token)

export const getCaregiverToken = () => localStorage.getItem('caregiver_session_token') || ''
export const setCaregiverToken = (token: string) => localStorage.setItem('caregiver_session_token', token)

// Patient API functions
export interface SignupParams {
  display_name: string
  email?: string
  phone?: string
  age?: number | null
  emergency_contact_name?: string
  doctor_name?: string
  doctor_email?: string
  doctor_specialty?: string
  doctor_phone?: string
}

export async function registerPatient(params: string | SignupParams = 'Robert Jenkins'): Promise<{
  patient_id: string
  device_token: string
  display_name: string
  email?: string
  doctor_name?: string
  doctor_email?: string
  message: string
}> {
  const payload = typeof params === 'string' ? { display_name: params, preferred_script: 'en' } : { ...params, preferred_script: 'en' }
  const res = await fetch(`${API_BASE}/api/patient/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error('Failed to register patient device')
  const data = await res.json()
  setPatientToken(data.device_token)
  localStorage.setItem('patient_display_name', data.display_name)
  localStorage.setItem('patient_id', data.patient_id)
  if (data.email) localStorage.setItem('patient_email', data.email)
  localStorage.setItem('patient_registered', 'true')
  return data
}

export const signupPatient = registerPatient

export async function submitTurn(params: { text?: string; audio_base64?: string | null }): Promise<TurnResponse> {
  let token = getPatientToken()
  if (!token) {
    const reg = await registerPatient()
    token = reg.device_token
  }

  const res = await fetch(`${API_BASE}/api/turn`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      text: params.text || null,
      audio_base64: params.audio_base64 || null,
      script: 'en',
    }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Voice service error: ${err}`)
  }
  return res.json()
}

export async function confirmAction(actionId: string, confirmed: boolean): Promise<ConfirmResponse> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/confirm`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ action_id: actionId, confirmed }),
  })
  if (!res.ok) throw new Error('Failed to confirm action')
  return res.json()
}

export async function getReminders() {
  const token = getPatientToken()
  if (!token) return []
  const res = await fetch(`${API_BASE}/api/reminders`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  return res.json()
}

// Pairing API functions
export async function createPairingKey(): Promise<PairCreateResponse> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/pair/create`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  })
  if (!res.ok) throw new Error('Could not generate pairing key')
  return res.json()
}

export async function redeemPairingKey(key: string, caregiverName: string): Promise<{ pending_id: number; message: string }> {
  const res = await fetch(`${API_BASE}/api/pair/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, caregiver_name: caregiverName }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: 'Incorrect key' }))
    throw new Error(data.detail || 'The key is incorrect or expired. Please ask for a new key.')
  }
  return res.json()
}

export async function getPendingPairRequests(): Promise<PairPendingItem[]> {
  const token = getPatientToken()
  if (!token) return []
  const res = await fetch(`${API_BASE}/api/pair/pending`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  return res.json()
}

export async function decidePairRequest(pendingId: number, approve: boolean): Promise<{ status: string; message: string }> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/pair/decide`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ pending_id: pendingId, approve }),
  })
  if (!res.ok) throw new Error('Failed to submit pairing decision')
  return res.json()
}

export async function checkPairStatus(pendingId: number): Promise<{ status: 'pending' | 'approved' | 'declined' | 'expired'; session_token?: string; caregiver_name?: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/pair/status?pending_id=${pendingId}`)
  if (!res.ok) throw new Error('Failed to verify status')
  return res.json()
}

export async function getLinkedCaregivers(): Promise<CaregiverLinkItem[]> {
  const token = getPatientToken()
  if (!token) return []
  const res = await fetch(`${API_BASE}/api/pair/links`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  return res.json()
}

export async function revokeCaregiverLink(linkId: number): Promise<boolean> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/pair/links/${linkId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.ok
}

export async function notifyFamilyEmergency(): Promise<{ status: string; alert_id: number; message: string }> {
  const token = getPatientToken()
  if (!token) throw new Error('Patient not registered')
  const res = await fetch(`${API_BASE}/api/emergency/notify`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('Failed to notify emergency services')
  return res.json()
}

// Caregiver Dashboard API functions
export async function getCaregiverDashboard(): Promise<DashboardResponse> {
  const token = getCaregiverToken()
  if (!token) throw new Error('Caregiver not authenticated')
  const res = await fetch(`${API_BASE}/api/dashboard`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem('caregiver_session_token')
      throw new Error('REVOKED')
    }
    throw new Error('Failed to load caregiver dashboard')
  }
  return res.json()
}

export async function markAlertHandled(alertId: number): Promise<boolean> {
  const token = getCaregiverToken() || getPatientToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  try {
    const res = await fetch(`${API_BASE}/api/alerts/${alertId}/handled`, {
      method: 'POST',
      headers,
    })
    return res.ok
  } catch (err) {
    console.warn('markAlertHandled note:', err)
    return true
  }
}

export async function addClinicianNote(reviewId: number, clinicianNote: string): Promise<boolean> {
  const token = getCaregiverToken()
  const res = await fetch(`${API_BASE}/api/review/${reviewId}/note`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ clinician_note: clinicianNote }),
  })
  return res.ok
}

// Prescriptions API functions (shared for Patient & Caregiver)
export async function getPrescriptions(role: 'patient' | 'caregiver' = 'patient'): Promise<PrescriptionItem[]> {
  const token = role === 'caregiver' ? getCaregiverToken() : getPatientToken()
  if (!token) return []
  const res = await fetch(`${API_BASE}/api/prescriptions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  return res.json()
}

export async function createPrescription(
  data: { medicine_name: string; dose_text: string; timing_text: string; instructions?: string },
  role: 'patient' | 'caregiver' = 'patient'
): Promise<PrescriptionItem> {
  const token = role === 'caregiver' ? getCaregiverToken() : getPatientToken()
  const res = await fetch(`${API_BASE}/api/prescriptions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to save prescription')
  return res.json()
}

export async function deletePrescription(id: number, role: 'patient' | 'caregiver' = 'patient'): Promise<boolean> {
  const token = role === 'caregiver' ? getCaregiverToken() : getPatientToken()
  const res = await fetch(`${API_BASE}/api/prescriptions/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.ok
}

// --- Patient Profile & Doctor Directory ---
export interface PatientProfile {
  patient_id: string
  display_name: string
  email: string | null
  phone?: string | null
  age?: number | null
  emergency_contact_name?: string | null
  doctor_name: string | null
  doctor_email: string | null
  doctor_specialty: string | null
  doctor_phone: string | null
  created_at: string
}

export async function getPatientProfile(): Promise<PatientProfile> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/patient/profile`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('Failed to load profile')
  return res.json()
}

export async function updatePatientProfile(data: Partial<PatientProfile>): Promise<PatientProfile> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/patient/profile`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update profile')
  return res.json()
}

// --- Prescription OCR Image Extraction ---
export interface ExtractedMedicineItem {
  medicine_name: string
  dose_text: string
  timing_text: string
  instructions?: string | null
  missing_fields: string[]
  confidence: number
}

export interface PrescriptionOCRResponse {
  raw_text: string
  extracted_medicines: ExtractedMedicineItem[]
  missing_summary: string | null
  has_missing_info: boolean
}

export async function uploadPrescriptionImage(file: File | null, imageBase64?: string): Promise<PrescriptionOCRResponse> {
  const token = getPatientToken() || getCaregiverToken()
  let body: any
  let headers: Record<string, string> = { Authorization: `Bearer ${token}` }

  if (file) {
    const formData = new FormData()
    formData.append('file', file)
    body = formData
  } else {
    const formData = new FormData()
    formData.append('image_base64', imageBase64 || '')
    body = formData
  }

  const res = await fetch(`${API_BASE}/api/prescriptions/upload-image`, {
    method: 'POST',
    headers,
    body,
  })
  if (!res.ok) throw new Error('Failed to extract prescription with OCR')
  return res.json()
}

// --- Doctor Email Consultation & Approval ---
export interface DoctorEmailItem {
  id: number
  patient_id: string
  doctor_name: string
  doctor_email: string
  patient_email: string | null
  subject: string
  body: string
  health_issue: string
  prescriptions_summary: string | null
  status: 'draft' | 'approved' | 'sent' | 'declined'
  created_at: string
  sent_at: string | null
}

export async function draftDoctorEmail(params: {
  health_issue: string
  doctor_name?: string
  doctor_email?: string
}): Promise<DoctorEmailItem> {
  const token = getPatientToken() || getCaregiverToken()
  const res = await fetch(`${API_BASE}/api/doctor/draft-email`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error('Failed to create doctor email draft')
  return res.json()
}

export async function approveDoctorEmail(emailId: number): Promise<{ status: string; message: string; email_item: DoctorEmailItem }> {
  const token = getPatientToken() || getCaregiverToken()
  const res = await fetch(`${API_BASE}/api/doctor/emails/${emailId}/approve`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('Failed to approve and send email')
  return res.json()
}

export async function declineDoctorEmail(emailId: number): Promise<boolean> {
  const token = getPatientToken() || getCaregiverToken()
  const res = await fetch(`${API_BASE}/api/doctor/emails/${emailId}/decline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.ok
}

export async function getDoctorEmails(): Promise<DoctorEmailItem[]> {
  const token = getPatientToken() || getCaregiverToken()
  const res = await fetch(`${API_BASE}/api/doctor/emails`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return []
  return res.json()
}

// --- Medication Due Reminders & Natural Language Intake ---
export interface DueReminderResponse {
  has_due_reminder: boolean
  all_taken_today?: boolean
  reminder?: {
    id: number
    patient_id: string
    medicine_name: string
    dose_text: string
    timing_text: string
    status: string
    created_at: string
  } | null
  prompt_text?: string | null
}

export async function getDueReminder(): Promise<DueReminderResponse> {
  const token = getPatientToken()
  if (!token) return { has_due_reminder: false }
  try {
    const res = await fetch(`${API_BASE}/api/reminders/due`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return { has_due_reminder: false }
    return await res.json()
  } catch (err) {
    return { has_due_reminder: false }
  }
}

export async function recordNaturalIntake(params: {
  reminder_id?: number
  medicine_name?: string
  time_offset_minutes?: number
  intake_note?: string
}): Promise<any> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/reminders/intake`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error('Failed to record medication intake')
  return res.json()
}

export async function takeReminderWithOffset(
  reminderId: number,
  timeOffsetMinutes: number = 0,
  intakeNote?: string
): Promise<any> {
  const token = getPatientToken()
  const res = await fetch(`${API_BASE}/api/reminders/${reminderId}/take`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      reminder_id: reminderId,
      time_offset_minutes: timeOffsetMinutes,
      intake_note: intakeNote,
    }),
  })
  if (!res.ok) throw new Error('Failed to confirm reminder intake')
  return res.json()
}

// --- Patient Memory Awareness ---
export interface PatientMemoryItem {
  id: number
  user_query: string
  assistant_response: string
  intent: string
  metadata: string
  created_at: string
}

export async function getPatientMemories(limit: number = 8): Promise<PatientMemoryItem[]> {
  const token = getPatientToken()
  if (!token) return []
  try {
    const res = await fetch(`${API_BASE}/api/patient/memory?limit=${limit}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return []
    const data = await res.json()
    return data.memories || []
  } catch {
    return []
  }
}
