"""Caregiver pairing and access control service.
Enforces SRS FR-19 through FR-25, UX-40 through UX-44 (English-only edition).
"""
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict, Any
from backend.config import settings
from backend.database import get_db_connection, hash_token
from backend.utils import utc_now, utc_now_iso


class PairingService:
    @staticmethod
    def normalize_key(raw_key: str) -> str:
        """Normalizes pairing key: case-insensitive, removes dashes and spaces."""
        return raw_key.replace("-", "").replace(" ", "").upper().strip()

    async def register_patient_device(
        self,
        display_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        age: Optional[int] = None,
        emergency_contact_name: Optional[str] = None,
        doctor_name: Optional[str] = None,
        doctor_email: Optional[str] = None,
        doctor_specialty: Optional[str] = None,
        doctor_phone: Optional[str] = None,
        seed_reminders: bool = False
    ) -> Tuple[str, str]:
        """FR-19: Creates an individual patient record with details and issues a long random device token."""
        patient_id = f"pat_{secrets.token_hex(6)}"
        device_token = secrets.token_urlsafe(32)
        device_token_hash = hash_token(device_token)

        conn = await get_db_connection()
        try:
            now_iso = utc_now_iso()
            await conn.execute(
                """
                INSERT INTO patients (
                    id, display_name, device_token_hash, preferred_script,
                    email, phone, age, emergency_contact_name,
                    doctor_name, doctor_email, doctor_specialty, doctor_phone,
                    created_at
                )
                VALUES (?, ?, ?, 'en', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id, display_name, device_token_hash,
                    email, phone, age, emergency_contact_name,
                    doctor_name, doctor_email, doctor_specialty, doctor_phone,
                    now_iso
                )
            )

            # Seed standard initial discharge medication reminders if requested
            if seed_reminders:
                await conn.execute(
                    """
                    INSERT INTO reminders (patient_id, medicine_name, dose_text, timing_text, status, created_at)
                    VALUES (?, 'Metformin', '500 mg', '8:00 AM after breakfast', 'active', ?)
                    """,
                    (patient_id, now_iso)
                )
                await conn.execute(
                    """
                    INSERT INTO reminders (patient_id, medicine_name, dose_text, timing_text, status, created_at)
                    VALUES (?, 'Amlodipine', '5 mg', '9:00 PM after dinner', 'active', ?)
                    """,
                    (patient_id, now_iso)
                )

            await conn.commit()
            return patient_id, device_token
        finally:
            await conn.close()

    async def verify_patient_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Authenticates patient device token."""
        if not token:
            return None
        token_hash = hash_token(token)
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id, display_name, preferred_script FROM patients WHERE device_token_hash = ?",
                (token_hash,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            await conn.close()

    async def generate_pairing_key(self, patient_id: str) -> Tuple[str, str, int, str]:
        """FR-20: Generates 8-hex character pairing key, invalidates prior unused keys."""
        raw_key = secrets.token_hex(4).upper()  # 8 hex chars
        formatted_key = f"{raw_key[:4]}-{raw_key[4:]}"
        key_hash = hash_token(raw_key)

        ttl_seconds = settings.PAIRING_KEY_TTL_SECONDS
        expires_at_dt = utc_now() + timedelta(seconds=ttl_seconds)
        expires_at_iso = expires_at_dt.isoformat().replace("+00:00", "Z")

        conn = await get_db_connection()
        try:
            # Invalidate any prior unused key for this patient
            now_iso = utc_now_iso()
            await conn.execute(
                "UPDATE pairing_keys SET used_at = ? WHERE patient_id = ? AND used_at IS NULL",
                (now_iso, patient_id)
            )

            # Insert new key
            await conn.execute(
                """
                INSERT INTO pairing_keys (key_hash, patient_id, expires_at, used_at)
                VALUES (?, ?, ?, NULL)
                """,
                (key_hash, patient_id, expires_at_iso)
            )
            await conn.commit()
            return raw_key, formatted_key, ttl_seconds, expires_at_iso
        finally:
            await conn.close()

    async def check_rate_limit(self, client_ip: str) -> bool:
        """FR-25: Returns True if client_ip has exceeded failed redemption limit."""
        conn = await get_db_connection()
        try:
            cutoff = time.time() - settings.PAIRING_FAILURE_WINDOW_SECONDS
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM rate_limit_records WHERE client_ip = ? AND timestamp >= ? AND action = 'failed_redeem'",
                (client_ip, cutoff)
            )
            count = (await cursor.fetchone())[0]
            return count >= settings.PAIRING_MAX_FAILURES
        finally:
            await conn.close()

    async def record_failed_attempt(self, client_ip: str):
        conn = await get_db_connection()
        try:
            await conn.execute(
                "INSERT INTO rate_limit_records (client_ip, timestamp, action) VALUES (?, ?, 'failed_redeem')",
                (client_ip, time.time())
            )
            await conn.commit()
        finally:
            await conn.close()

    async def redeem_pairing_key(
        self,
        raw_key: str,
        caregiver_name: str,
        client_ip: str
    ) -> Tuple[bool, Optional[int], str]:
        """FR-21: Redeems key, marks used immediately, creates pending link."""
        if await self.check_rate_limit(client_ip):
            return False, None, "Too many failed attempts. Please wait 10 minutes before trying again."

        normalized = self.normalize_key(raw_key)
        if len(normalized) != 8:
            await self.record_failed_attempt(client_ip)
            return False, None, "Invalid or expired key. Please ask for a new key."

        key_hash = hash_token(normalized)
        now_iso = utc_now_iso()

        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT patient_id, expires_at, used_at FROM pairing_keys WHERE key_hash = ?",
                (key_hash,)
            )
            row = await cursor.fetchone()
            if not row:
                await self.record_failed_attempt(client_ip)
                return False, None, "Invalid or expired key. Please ask for a new key."

            patient_id, expires_at_str, used_at_str = row[0], row[1], row[2]

            # Check if used or expired
            if used_at_str is not None:
                await self.record_failed_attempt(client_ip)
                return False, None, "Invalid or expired key. Please ask for a new key."

            expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(expires_at_dt.tzinfo) > expires_at_dt:
                await self.record_failed_attempt(client_ip)
                return False, None, "Invalid or expired key. Please ask for a new key."

            # Mark key used immediately (FR-21)
            await conn.execute(
                "UPDATE pairing_keys SET used_at = ? WHERE key_hash = ?",
                (now_iso, key_hash)
            )

            # Create pending caregiver link
            cur = await conn.execute(
                """
                INSERT INTO caregiver_links (patient_id, caregiver_name, token_hash, status, created_at)
                VALUES (?, ?, NULL, 'pending', ?)
                """,
                (patient_id, caregiver_name, now_iso)
            )
            pending_id = cur.lastrowid
            await conn.commit()

            return True, pending_id, "Link requested. Waiting for patient consent on their device."
        finally:
            await conn.close()

    async def get_pending_requests(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieves pending caregiver link requests for patient approval."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id as pending_id, caregiver_name, created_at FROM caregiver_links WHERE patient_id = ? AND status = 'pending' ORDER BY id DESC",
                (patient_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def decide_link_request(self, patient_id: str, pending_id: int, approve: bool) -> Tuple[bool, str]:
        """FR-22: Patient approves or declines link. Issues 128-bit session token if approved."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id, caregiver_name, status FROM caregiver_links WHERE id = ? AND patient_id = ?",
                (pending_id, patient_id)
            )
            row = await cursor.fetchone()
            if not row or row[2] != "pending":
                return False, "Pending link request not found or already processed."

            if approve:
                # Generate at least 128-bit session token (16 bytes = 128 bits, 32 hex chars)
                session_token = secrets.token_hex(20)  # 160 bits
                token_hash = hash_token(session_token)

                await conn.execute(
                    "UPDATE caregiver_links SET status = 'active', token_hash = ? WHERE id = ?",
                    (token_hash, pending_id)
                )
                await conn.commit()
                # Temporarily save raw session token for the caregiver to retrieve once via polling
                self._cache_issued_token(pending_id, session_token)
                return True, "Caregiver link approved successfully."
            else:
                await conn.execute(
                    "UPDATE caregiver_links SET status = 'declined' WHERE id = ?",
                    (pending_id,)
                )
                await conn.commit()
                return True, "Caregiver link request declined."
        finally:
            await conn.close()

    # Ephemeral memory for one-time session token delivery upon approval (FR-22)
    _issued_tokens: Dict[int, str] = {}

    @classmethod
    def _cache_issued_token(cls, pending_id: int, token: str):
        cls._issued_tokens[pending_id] = token

    async def check_pairing_status(self, pending_id: int) -> Tuple[str, Optional[str], Optional[str], str]:
        """Caregiver polls for link approval status."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT status, caregiver_name FROM caregiver_links WHERE id = ?",
                (pending_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return "expired", None, None, "Invalid pairing request."

            status, name = row[0], row[1]
            if status == "active":
                token = self._issued_tokens.pop(pending_id, None)
                return "approved", token, name, "Link approved by patient."
            elif status == "declined":
                return "declined", None, name, "The patient has not approved the link yet."
            elif status == "revoked":
                return "declined", None, name, "Your connection has been removed."
            else:
                return "pending", None, name, "Waiting for patient consent."
        finally:
            await conn.close()

    async def verify_caregiver_token(self, token: str) -> Optional[Dict[str, Any]]:
        """FR-23: Scoping. Verifies caregiver session token and resolves linked patient_id."""
        if not token:
            return None
        token_hash = hash_token(token)
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT c.id, c.patient_id, c.caregiver_name, c.status, p.display_name as patient_display_name
                FROM caregiver_links c
                JOIN patients p ON c.patient_id = p.id
                WHERE c.token_hash = ? AND c.status = 'active'
                """,
                (token_hash,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            await conn.close()

    async def list_patient_links(self, patient_id: str) -> List[Dict[str, Any]]:
        """FR-24: Lists all active and past links for patient."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id, caregiver_name, status, created_at, revoked_at FROM caregiver_links WHERE patient_id = ? AND status = 'active' ORDER BY id DESC",
                (patient_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def revoke_caregiver_link(self, patient_id: str, link_id: int) -> bool:
        """FR-24: Revokes a caregiver link immediately."""
        conn = await get_db_connection()
        try:
            now_iso = utc_now_iso()
            cursor = await conn.execute(
                "UPDATE caregiver_links SET status = 'revoked', revoked_at = ? WHERE id = ? AND patient_id = ?",
                (now_iso, link_id, patient_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()


pairing_service = PairingService()
