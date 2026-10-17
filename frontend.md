# Master Prompt: Sehat Saathi Frontend (English-only Edition)

> **Prompt Objective**: Copy and paste the prompt below into your frontend coding agent or give it to your developer to build the complete, production-grade, accessible Progressive Web App (PWA) for **Sehat Saathi (English-only Edition)**.

---

```markdown
# TASK INSTRUCTION: Build the Sehat Saathi Frontend (PWA)

You are an expert Frontend Architect specializing in accessible, healthcare-focused Progressive Web Apps (PWAs). Your task is to build the complete, standalone, production-ready frontend for **Sehat Saathi (English-only Edition)**.

The frontend must interface seamlessly with our existing **FastAPI backend** running at `http://localhost:8000` (or configurable via `VITE_API_BASE_URL` / `API_BASE_URL`).

---

## 1. Guiding Principles & User Persona
- **Primary Users**: Elderly patients (age 60+) who may have tremors, poor vision, hearing impairment, and low digital literacy.
- **Secondary Users**: Family caregivers and clinicians who monitor the patient remotely.
- **User Experience (UX) First**:
  1. **One thing at a time**: Each screen has one clear purpose and one obvious next action.
  2. **Never leave the patient guessing**: The screen and spoken audio must always communicate state: **Listening**, **Thinking**, **Speaking**, or **Waiting for confirmation**.
  3. **Never blame the patient**: Phrased as the app's difficulty ("I could not hear that clearly. Please say it again."), never as a user mistake.
  4. **Large controls & High contrast**: Minimum button sizes, WCAG AAA 7:1 contrast, generous spacing.
  5. **Dual-Role Single App**: The exact same installable PWA serves both the **Patient** and the **Caregiver** via role selection.

---

## 2. Mandatory UX & Accessibility Requirements (Strictly Enforced)

| ID | Requirement | Implementation Detail |
|---|---|---|
| **UX-01** | **Primary Control** | The home screen has **exactly one primary control**: a large microphone button, **at least 120px in diameter**, centred in the lower half within easy thumb reach. One small secondary control, "Family" (UX-40), sits in the top-right corner. |
| **UX-02** | **Text Sizing** | Base text size is at least **24px**, headline answers at least **28px**. Provide a persistent "Text Size" control with at least 3 levels (Normal 24px, Large 28px, Extra Large 34px) that persists in `localStorage`. |
| **UX-03** | **Touch Targets** | Every button and interactive control must be at least **56 × 56 px** with at least **12px** spacing between adjacent targets. |
| **UX-04** | **Contrast & Color** | Body text contrast must meet **WCAG AAA (7:1)** against backgrounds. Provide a High-Contrast Mode toggle. **Color is never the only carrier of meaning**: every status color is paired with an icon and a text label. |
| **UX-07** | **Simplicity** | Screens contain **no more than 1 paragraph of text** and **no more than 3 buttons at a time** (not counting persistent Help and Family controls). Avoid vertical scrolling on Home and Confirmation screens. |
| **UX-10** | **Tremor Accommodating Mic** | Push-to-talk by tap-and-hold is NOT required. A **single tap starts listening** and a **second tap** (or 2 seconds of detected silence) stops it. |
| **UX-11** | **Typed Fallback** | A typed-input field / keyboard toggle is reachable in **one tap** from the home screen. Typed and spoken queries follow the identical pipeline. |
| **UX-12** | **Audio Controls** | Every answer view displays a **"Replay"** button and a **"Slower"** button (adjusting audio playback rate between 0.75x, 0.9x, and 1.0x). |
| **UX-13** | **Synchronized Captions** | Spoken answers display as large, visible captions in real-time, highlighting the current sentence so hearing-impaired users are not excluded. |
| **UX-14** | **Confirm-Before-Act** | Before booking an appointment or saving a reminder, display an echo-back screen: *"I heard: [Action details]. Is that correct?"* with two large buttons: **"Yes"** and **"No"**. Spoken "yes" and "no" must also be accepted. |
| **UX-15** | **Polite 'No' Handling** | Pressing "No" never triggers an error message. It returns the patient to the home screen with: *"All right, please say it again."* |
| **UX-16** | **Grounding Badge** | Display the discharge summary source line: *"Your discharge summary says: ..."* and a confidence badge with an icon and word: `Certain` (Green), `Possibly` (Yellow), or `Unknown` (Gray). |
| **UX-17** | **Persistent Emergency** | A persistent, red-bordered **"Help / Emergency"** button is always visible. Tapping it shows 911 dialing instructions and a one-tap **"Notify Family"** button. If no family is linked, state: *"No family member is linked yet."* |
| **UX-18** | **Onboarding Flow** | A simple 3-step walkthrough on first launch: (1) Test microphone, (2) Test audio speaker, (3) Optional "Link a family member now?". Can be skipped. |
| **UX-19** | **Distinct System States** | Clearly show 4 visual states with distinct icons, colors, and audio prompts: <br>• **Listening** (Blue pulsing, "I am listening")<br>• **Thinking** (Amber spinner, "I am thinking", switches within 300ms)<br>• **Speaking** (Green audio wave, playing audio + captions)<br>• **Waiting Confirmation** (Purple question, echo-back buttons) |
| **UX-21** | **Holding Phrase** | If backend response takes > 4 seconds, speak and display: *"Please wait a moment."* After 10s, offer: *"Try again"* and the typed input fallback. |
| **UX-24** | **No Technical Jargon** | Never display technical errors, HTTP codes, or vendor names ("AMD", "Hugging Face", "model", "vLLM", "500"). Errors must be patient-friendly: e.g., *"The key is incorrect or expired. Please ask for a new key."* |
| **UX-27** | **Emergency View** | If a red-flag condition is detected (chest pain, stroke, fainting, severe bleeding, breathlessness), immediately replace the entire screen with a high-contrast emergency view: a large red **"Call 911"** button, spoken instruction, and confirmation that family was alerted. |
| **UX-30** | **Reminder Alerts** | When a reminder is due, open a full-screen card speaking the alert with a large **"I have taken my medicine"** button, plus a **"Snooze (15m)"** button. |

---

## 3. Screen-by-Screen Specifications

### Screen 1: Role Selection (`UX-39`)
- Displayed on first app launch (stored in `localStorage` as `user_role: "patient" | "caregiver"`).
- Two large 56px+ buttons:
  - `[ I am the Patient ]` ➔ Registers device via `POST /api/patient/register` and opens Patient Home.
  - `[ I am a Family Member / Caregiver ]` ➔ Opens Caregiver Key Entry screen.

---

### Screen 2: Patient Home Screen (`UX-01`, `UX-11`, `UX-17`, `UX-40`)
- **Top Bar**:
  - Left: Persistent **"Help / Emergency"** button (`UX-17`).
  - Center: **Text Size Toggle** (`A` / `A+` / `A++`) & High Contrast toggle.
  - Right: **"Family"** icon button (`UX-40`) showing linked caregiver count.
- **Center Canvas**:
  - Animated State Card showing state: Idle, Listening ("I am listening"), Thinking ("I am thinking"), Speaking (with large captions), or Waiting for confirmation.
- **Lower Half**:
  - **Single Big Mic Button** (120px diameter, circular, high contrast, thumb reach).
  - One tap starts recording via browser `MediaRecorder`; second tap stops recording and submits to `POST /api/turn`.
  - Secondary icon button below: **"Type Question"** (opens simple single-line input field).

---

### Screen 3: Answer & Grounding View (`UX-12`, `UX-13`, `UX-16`)
- **Headline Answer**: Large 28px+ text answering the query.
- **Source Line Card**: Light background card reading: *"Your discharge summary says: [exact line text]"*.
- **Confidence Badge**:
  - `Certain` (Green checkmark icon)
  - `Possibly` (Yellow alert icon)
  - `Unknown` (Gray question icon)
- **Audio Control Bar**:
  - `[ 🔁 Replay ]`
  - `[ 🐢 Slower (0.8x) ]`
  - `[ ✕ Close / Done ]`

---

### Screen 4: Confirmation Echo-Back Modal (`UX-14`, `UX-15`)
- Full-screen or modal overlay preventing accidental clicks.
- Heading: *"Please Confirm"*
- Echo-Back Text: *"I heard: Take Metformin 500mg in the morning after breakfast. Is that correct?"*
- Two massive buttons side-by-side:
  - `[ ✓ Yes, that is correct ]` (Green, calls `POST /api/confirm` with `confirmed: true`)
  - `[ ✕ No, say again ]` (Red/Neutral, calls `POST /api/confirm` with `confirmed: false`, returns cleanly to Home without error)

---

### Screen 5: Emergency View (`UX-27`)
- Full-screen high-contrast Crimson/Red alert view.
- Headline: *"EMERGENCY ASSISTANCE"*
- Description: Critical symptom detected (e.g. Chest pain / Stroke signs).
- Instructions: *"Please call 911 immediately. Your family has been alerted."*
- Actions:
  - `[ 📞 Call 911 Now ]` (href="tel:911", height: 70px)
  - Status banner: *"Family Alert: Notified at [Timestamp]"* or *"No family linked yet."*

---

### Screen 6: Patient Family & Pairing Management (`UX-40`, `UX-41`, `UX-42`)
- Accessible from the top-right "Family" button on Patient Home.
- **Primary Action**: `[ + Link a Family Member ]`
- When tapped, calls `POST /api/pair/create` and displays:
  - Pairing key in **giant monospaced text split in two groups** (e.g., `A3F9 - 7C21`).
  - Active 10-minute countdown timer bar (`PAIRING_KEY_TTL_SECONDS`).
  - `[ 🔊 Read Aloud ]` button (speaks the 8 characters one-by-one via browser speech).
  - `[ 🔄 New Key ]` button.
- **Incoming Consent Prompt (`UX-42`)**:
  - Polls `GET /api/pair/pending`. If a caregiver redeems the key, triggers an audio prompt and modal:
    > *"Ahmed would like to link with you. Is that okay?"*
    > Buttons: `[ ✓ Yes, Approve ]` | `[ ✕ No, Decline ]`
    > Calls `POST /api/pair/decide`.
- **Linked Caregivers List**:
  - Shows each linked name and linked date.
  - Each item has a `[ Remove ]` button (calls `DELETE /api/pair/links/{id}`).

---

### Screen 7: Caregiver Key Entry Screen (`UX-43`, `UX-44`)
- Displayed when caregiver launches app or when their link is revoked.
- Large input field: accepts 8-character key (case-insensitive, with or without dashes/spaces).
- Caregiver Name input: *"Enter your name (e.g., Sarah)"*.
- Action: `[ Link to Patient ]` (calls `POST /api/pair/redeem`).
- State: Shows *"Waiting for patient to approve on their phone..."* while polling `GET /api/pair/status?pending_id=...`.
- Once approved, stores `caregiver_session_token` in `localStorage` and transitions directly to Dashboard.
- **Revocation Notice (`UX-44`)**: If the patient revokes access, dashboard immediately redirects here with:
  > *"Your connection has been removed."*

---

### Screen 8: Caregiver Dashboard (`UX-35` to `UX-38`)
- Automatically updates every 5 seconds (via polling `GET /api/dashboard`).
- **Section 1: "Today's Status" Summary Card (`UX-35`)**:
  - Patient Display Name (top header)
  - Open Emergency Alerts badge (Red)
  - Pending Clinician Review Items badge (Yellow)
  - Today's Medication Adherence: Taken count, Missed count, Pending count
  - Next Scheduled Appointment (Date, Time)
- **Section 2: High-Priority Emergency Alerts (`UX-36`)**:
  - Distinct red cards showing time, patient's exact words, action taken.
  - Action button: `[ Mark as Handled ]` (calls `POST /api/alerts/{id}/handled`).
- **Section 3: Clinician Review Queue (`UX-37`)**:
  - Cards showing patient questions that resulted in an honest handoff.
  - Shows patient question, reason not found in discharge summary, and an inline input for clinician:
    - Input: *"Add doctor's note or instructions"*
    - Button: `[ Submit Note ]` (calls `POST /api/review/{id}/note`).
- **Section 4: Active Reminders & Adherence Logs (`UX-30`)**:
  - Lists medicines with exact dose and timing.
- **Section 5: Booked Appointments**:
  - Lists upcoming clinic slots.

---

## 4. Backend API Integration Specifications

### Base Configuration
- Default backend host: `http://localhost:8000`
- All requests should include `Content-Type: application/json`.
- Patient-authenticated endpoints require: `Authorization: Bearer <patient_device_token>`
- Caregiver-authenticated endpoints require: `Authorization: Bearer <caregiver_session_token>`

### Core API Contracts

#### 1. Patient Registration & Turn
```typescript
// POST /api/patient/register
// Body: { display_name: "Robert Jenkins", preferred_script: "en" }
// Response: { patient_id: "pat_...", device_token: "...", message: "..." }

// POST /api/turn
// Headers: { "Authorization": "Bearer <device_token>" }
// Body: { text: "When should I take Metformin?", script: "en", audio_base64: null }
// Response:
interface TurnResponse {
  transcript: string;
  answer: string;
  source_line: string | null;
  cited_line_ids: string[];
  confidence: number;
  confidence_badge: "Certain" | "Possibly" | "Unknown";
  audio_url: string | null;
  ui_state: "listening" | "thinking" | "speaking" | "waiting_confirmation" | "emergency" | "handoff";
  echo_back: string | null;
  pending_action_id: string | null;
  is_emergency: boolean;
  emergency_action_taken: string | null;
}
```

#### 2. Confirm-Before-Act
```typescript
// POST /api/confirm
// Headers: { "Authorization": "Bearer <device_token>" }
// Body: { action_id: "act_...", confirmed: true }
// Response: { status: "confirmed" | "rejected" | "expired", message: "...", details: {} }
```

#### 3. Caregiver Pairing Flow
```typescript
// 1. Patient creates key:
// POST /api/pair/create -> { key: "A3F97C21", formatted_key: "A3F9-7C21", expires_in_seconds: 600 }

// 2. Caregiver redeems key:
// POST /api/pair/redeem -> Body: { key: "A3F9-7C21", caregiver_name: "Sarah" } -> { pending_id: 12 }

// 3. Patient polls pending:
// GET /api/pair/pending -> [{ pending_id: 12, caregiver_name: "Sarah", created_at: "..." }]

// 4. Patient approves/declines:
// POST /api/pair/decide -> Body: { pending_id: 12, approve: true }

// 5. Caregiver polls status:
// GET /api/pair/status?pending_id=12 -> { status: "approved", session_token: "...", caregiver_name: "Sarah" }
```

#### 4. Caregiver Scoped Dashboard
```typescript
// GET /api/dashboard
// Headers: { "Authorization": "Bearer <caregiver_session_token>" }
// Response:
interface DashboardResponse {
  summary: {
    patient_display_name: string;
    open_alerts_count: number;
    review_items_count: number;
    reminders_taken_today: number;
    reminders_missed_today: number;
    reminders_pending_today: number;
    next_appointment: string;
  };
  alerts: Array<{ id: number; type: string; priority: string; transcript_excerpt: string; action_taken: string; created_at: string; handled_at: string | null }>;
  review_queue: Array<{ id: number; question: string; attempted_answer: string; reason: string; clinician_note: string | null; status: string; created_at: string }>;
  reminders: Array<{ id: number; medicine_name: string; dose_text: string; timing_text: string; status: string }>;
  appointments: Array<{ id: number; slot_start: string; status: string }>;
}
```

#### 5. Real-Time Emergency Buzzer (Server-Sent Events)
Caregiver PWA subscribes via standard browser `EventSource`:
```javascript
// Connect to real-time event stream
const eventSource = new EventSource(`${API_BASE_URL}/api/caregiver/events?token=${caregiverSessionToken}`);

eventSource.addEventListener('emergency_buzzer', (e) => {
  const alertData = JSON.parse(e.data);
  // 1. Play loud 100% free siren sound via Web Audio API (see section 5.2)
  playEmergencySiren();
  // 2. Vibrate caregiver phone
  if (navigator.vibrate) navigator.vibrate([800, 300, 800, 300, 800]);
  // 3. Display full-screen emergency takeover modal
  showEmergencyModal(alertData);
});

eventSource.addEventListener('prescription_updated', (e) => {
  // Real-time notification when prescription is added
  fetchDashboardData();
});
```

#### 6. Prescription Management (Caregiver & Patient)
```typescript
// POST /api/prescriptions
// Headers: { "Authorization": "Bearer <device_token | session_token>" }
// Body:
interface PrescriptionCreateRequest {
  medicine_name: string;    // e.g., "Aspirin"
  dose_text: string;        // e.g., "75mg"
  timing_text: string;      // e.g., "once daily with dinner"
  instructions?: string;    // e.g., "Take with a full glass of water"
}

// GET /api/prescriptions -> Array of active prescriptions
// DELETE /api/prescriptions/:id -> Deactivates prescription
```

---

### Screen 9: Prescription Management View (Caregiver & Patient)
- Designed to make the patient's life effortless by allowing the family caregiver to set up and update current medications remotely.
- **Header**: *"Current Prescriptions & Medications"*
- **Add Prescription Form**:
  - Medicine Name input (*"e.g. Metformin, Aspirin"*)
  - Dose input (*"e.g. 500mg, 1 tablet"*)
  - Schedule input (*"e.g. Morning after breakfast, Night after dinner"*)
  - Special Instructions (*"e.g. Take with food"*)
  - Button: `[ + Add to Patient's Medication List ]`
- **What happens automatically upon submission**:
  1. The medicine is saved to the patient's prescription record.
  2. An active in-app reminder is immediately generated so the patient's phone sounds when the dose is due.
  3. The medication instructions are dynamically indexed into the patient's discharge summary lines (`L9`, `L10`, etc.) so the AI voice assistant can immediately answer: *"When do I take my Aspirin?"*.
  4. Real-time notification is broadcast to the patient's phone.

---

## 5. Technical Stack & PWA Recommendations
1. **Framework**: React 18+ (with Vite) or Clean Modern HTML5/CSS3/ES Modules.
2. **Free 100% Client-Side Emergency Siren (Web Audio API)**:
   Does not require any external audio files, paid notification services, or third-party libraries:
   ```javascript
   function playEmergencySiren() {
     const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
     const osc = audioCtx.createOscillator();
     const gain = audioCtx.createGain();
     osc.type = 'sawtooth';
     gain.gain.setValueAtTime(0.8, audioCtx.currentTime);

     // Oscillate frequency between 700Hz and 1100Hz like an ambulance siren
     let high = false;
     const interval = setInterval(() => {
       if (audioCtx.state === 'closed') { clearInterval(interval); return; }
       osc.frequency.setValueAtTime(high ? 700 : 1100, audioCtx.currentTime);
       high = !high;
     }, 400);

     osc.connect(gain);
     gain.connect(audioCtx.destination);
     osc.start();

     // Returns a function to silence the buzzer
     return () => {
       clearInterval(interval);
       try { osc.stop(); audioCtx.close(); } catch(e) {}
     };
   }
   ```
3. **Styling**: Tailwind CSS configured with a custom color palette meeting WCAG AAA (high contrast blue `#1E40AF`, amber `#B45309`, green `#15803D`, crimson `#B91C1C`).
4. **PWA Manifest (`manifest.json`)**:
   - `name`: "Sehat Saathi"
   - `short_name`: "SehatSaathi"
   - `theme_color`: "#1E40AF"
   - `background_color`: "#FFFFFF"
   - `display`: "standalone"
   - `icons`: 192x192 and 512x512 PNGs.
5. **Audio Handling**:
   - Web Audio API / `navigator.mediaDevices.getUserMedia({ audio: true })`.
   - Record in WAV / WebM format, convert blob to Base64, and transmit in `POST /api/turn`.
   - Audio playback using standard `<audio>` element for backend `audio_url`, with browser `window.speechSynthesis` as an automatic zero-latency fallback if remote audio fails to load.

---

## 6. Definition of Done (Acceptance Criteria)
1. **Elderly Usability Test**: A non-technical user can press the big mic button, ask *"When do I take my morning pill?"*, hear the spoken answer, and see the highlighted citation line without seeing any technical error.
2. **Sudden Heart Pain & Real-time Caregiver Buzzer**: When a patient speaks *"I have the pain in my heart so hard"*, the patient screen immediately shows the 911 emergency view, and within 1 second, the Caregiver PWA rings an emergency siren buzzer, vibrates the phone, and displays the patient's exact words.
3. **Caregiver Remote Prescription Entry**: A family caregiver enters a new medication (*"Aspirin 75mg once daily"*); the patient app receives the update in real-time, sets up a reminder, and the AI agent can now answer questions about Aspirin.
4. **Pairing Handshake**: Generating an 8-character code on Patient mode, entering it on Caregiver mode, approving on Patient mode, and seeing the Caregiver dashboard populate immediately.
5. **PWA Installation**: Installable to Android / iOS home screen as a standalone app.
```

