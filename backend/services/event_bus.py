"""In-memory real-time event bus for Server-Sent Events (SSE).
Enables zero-cost real-time emergency buzzer and prescription sync between Patient and Caregiver PWAs.
"""
import asyncio
import json
import logging
from typing import Dict, List, Any
from backend.utils import utc_now_iso

logger = logging.getLogger("sehat_saathi.event_bus")


class EventBus:
    def __init__(self):
        # Map patient_id -> list of asyncio.Queue for connected caregiver streams
        self._caregiver_subscribers: Dict[str, List[asyncio.Queue]] = {}
        # Map patient_id -> list of asyncio.Queue for connected patient streams
        self._patient_subscribers: Dict[str, List[asyncio.Queue]] = {}

    def subscribe_caregiver(self, patient_id: str) -> asyncio.Queue:
        """Subscribes a caregiver SSE connection to events for a specific patient."""
        queue: asyncio.Queue = asyncio.Queue()
        if patient_id not in self._caregiver_subscribers:
            self._caregiver_subscribers[patient_id] = []
        self._caregiver_subscribers[patient_id].append(queue)
        logger.info(f"Caregiver subscribed to SSE for patient {patient_id}. Total subscribers: {len(self._caregiver_subscribers[patient_id])}")
        return queue

    def unsubscribe_caregiver(self, patient_id: str, queue: asyncio.Queue):
        """Removes a caregiver SSE queue when connection closes."""
        if patient_id in self._caregiver_subscribers:
            try:
                self._caregiver_subscribers[patient_id].remove(queue)
                if not self._caregiver_subscribers[patient_id]:
                    del self._caregiver_subscribers[patient_id]
                logger.info(f"Caregiver unsubscribed from SSE for patient {patient_id}")
            except ValueError:
                pass

    def subscribe_patient(self, patient_id: str) -> asyncio.Queue:
        """Subscribes patient device SSE connection."""
        queue: asyncio.Queue = asyncio.Queue()
        if patient_id not in self._patient_subscribers:
            self._patient_subscribers[patient_id] = []
        self._patient_subscribers[patient_id].append(queue)
        return queue

    def unsubscribe_patient(self, patient_id: str, queue: asyncio.Queue):
        if patient_id in self._patient_subscribers:
            try:
                self._patient_subscribers[patient_id].remove(queue)
                if not self._patient_subscribers[patient_id]:
                    del self._patient_subscribers[patient_id]
            except ValueError:
                pass

    async def broadcast_to_caregivers(self, patient_id: str, event_type: str, payload: Dict[str, Any]):
        """Dispatches an event (e.g. emergency buzzer) to all active linked caregiver connections."""
        queues = self._caregiver_subscribers.get(patient_id, [])
        message = {
            "event": event_type,
            "patient_id": patient_id,
            "timestamp": utc_now_iso(),
            "data": payload
        }
        for q in list(queues):
            try:
                await q.put(message)
            except Exception as e:
                logger.warning(f"Failed to queue event for caregiver: {e}")

    async def broadcast_to_patient(self, patient_id: str, event_type: str, payload: Dict[str, Any]):
        """Dispatches an event (e.g. prescription added by caregiver) to patient device."""
        queues = self._patient_subscribers.get(patient_id, [])
        message = {
            "event": event_type,
            "patient_id": patient_id,
            "timestamp": utc_now_iso(),
            "data": payload
        }
        for q in list(queues):
            try:
                await q.put(message)
            except Exception as e:
                logger.warning(f"Failed to queue event for patient: {e}")


event_bus = EventBus()
