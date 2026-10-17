"""OCR Prescription Extraction & LLM Structuring Service.
Scans prescription images, extracts text via OCR, sends the extracted data to the LLM
to parse into structured medication objects, and verifies required missing fields (such as timing of taking medication).
"""
import re
import json
import logging
from typing import List, Dict, Any, Optional
import httpx
from backend.config import settings

logger = logging.getLogger("sehat_saathi.ocr")

# Clinical vocabulary for fallback rule-based parser
COMMON_MEDICINES = [
    "Metformin", "Aspirin", "Amlodipine", "Paracetamol", "Panadol",
    "Atorvastatin", "Omeprazole", "Lisinopril", "Amoxicillin", "Azithromycin",
    "Ciprofloxacin", "Losartan", "Pantoprazole", "Insulin", "Clopidogrel",
    "Gabapentin", "Hydrochlorothiazide", "Levothyroxine", "Furosemide", "Ibuprofen",
    "Lipitor", "Augmentin", "Nexium", "Plavix", "Glucophage", "Zithromax"
]

TIMING_PATTERNS = [
    r"\b(morning after breakfast|in the morning|after breakfast|with breakfast)\b",
    r"\b(night after dinner|at night|before bed|after dinner|with dinner|at bedtime)\b",
    r"\b(twice daily|twice a day|bid|b\.i\.d\.|every 12 hours)\b",
    r"\b(three times daily|three times a day|tid|t\.i\.d\.|every 8 hours)\b",
    r"\b(once daily|once a day|od|q\.d\.|every morning|every evening)\b",
    r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b",
    r"\b(after meals?|before meals?|with food|empty stomach)\b",
    r"\b(as needed|sos|prn|p\.r\.n\.)\b"
]

DOSE_PATTERNS = [
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|tablets?|capsules?|pills?|units?|drops?))\b",
    r"\b(one tablet|two tablets|1 tablet|2 tablets|1 capsule|2 capsules)\b"
]


class OCRService:
    def __init__(self):
        self.hf_token = settings.HF_TOKEN

    async def extract_from_image_bytes(self, image_bytes: bytes, filename: str = "prescription.jpg") -> Dict[str, Any]:
        """Runs OCR extraction and structures prescription information using the LLM."""
        raw_text = await self._perform_ocr(image_bytes, filename)
        logger.info(f"OCR extracted raw text ({len(raw_text)} chars): {raw_text[:120]}...")

        if not raw_text.strip():
            return {
                "raw_text": "Could not extract legible text from image.",
                "extracted_medicines": [],
                "missing_summary": "No text could be recognized from this image. Please take a clear, well-lit photo of the prescription.",
                "has_missing_info": True
            }

        # Send extracted OCR text to the LLM to structure data and verify missing fields
        extracted = await self.structure_with_llm(raw_text)
        return extracted

    async def _perform_ocr(self, image_bytes: bytes, filename: str) -> str:
        """Multi-tier OCR extraction:
        1. Plain text / UTF-8 decode (for uploaded text files / notes)
        2. High-accuracy online OCR API (OCR.Space)
        3. Hugging Face TrOCR / Vision model (if configured)
        4. Local heuristic text extraction from document stream
        """
        # 1. Check if payload is already plain text (non-binary)
        if not (image_bytes.startswith(b"\xff\xd8") or image_bytes.startswith(b"\x89PNG") or image_bytes.startswith(b"GIF") or image_bytes.startswith(b"RIFF")):
            try:
                decoded = image_bytes.decode("utf-8")
                words = [w for w in decoded.split() if len(w) > 2]
                if len(words) >= 2:
                    logger.info("Input recognized as plain text prescription document.")
                    return decoded.strip()
            except UnicodeDecodeError:
                pass

        # 2. Online OCR engine (OCR.Space API)
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                files = {"file": (filename or "prescription.jpg", image_bytes, "image/jpeg")}
                data = {
                    "apikey": "helloworld",
                    "language": "eng",
                    "isOverlayRequired": "false",
                    "detectOrientation": "true",
                    "scale": "true"
                }
                resp = await client.post("https://api.ocr.space/parse/image", files=files, data=data)
                if resp.status_code == 200:
                    res_json = resp.json()
                    parsed_results = res_json.get("ParsedResults", [])
                    if parsed_results:
                        text = parsed_results[0].get("ParsedText", "").strip()
                        if text:
                            logger.info(f"OCR.Space successfully extracted text: {text[:80]}...")
                            return text
        except Exception as e:
            logger.warning(f"OCR.Space extraction failed: {e}. Trying fallback...")

        # 3. Hugging Face TrOCR / Vision (if token configured)
        if self.hf_token:
            try:
                headers = {"Authorization": f"Bearer {self.hf_token}"}
                url = "https://api-inference.huggingface.co/models/microsoft/trocr-base-printed"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, content=image_bytes)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                            hf_txt = data[0]["generated_text"].strip()
                            if hf_txt:
                                return hf_txt
            except Exception as e:
                logger.warning(f"HF Vision OCR failed: {e}")

        # 4. Extract printable ASCII strings from binary document stream
        try:
            printable_matches = re.findall(rb"[A-Za-z0-9 ,.:;/\-]{4,}", image_bytes)
            candidate_strings = [m.decode("ascii", errors="ignore").strip() for m in printable_matches]
            medical_keywords = {"rx", "mg", "tablet", "capsule", "daily", "dr", "take", "morning", "night", "patient"}
            filtered = [s for s in candidate_strings if any(k in s.lower() for k in medical_keywords)]
            if filtered:
                return "\n".join(filtered[:15])
        except Exception:
            pass

        return ""

    async def structure_with_llm(self, raw_text: str) -> Dict[str, Any]:
        """Sends extracted raw OCR text to the LLM to structure into medications
        and verify missing required fields like medication timing.
        """
        prompt = (
            "You are a clinical pharmacy and prescription analysis specialist.\n"
            "Analyze the following raw OCR text extracted from a medical prescription:\n\n"
            "--- RAW OCR TEXT ---\n"
            f"{raw_text}\n"
            "--- END RAW OCR TEXT ---\n\n"
            "Extract every prescribed medicine into JSON with this exact schema:\n"
            "{\n"
            '  "medicines": [\n'
            "    {\n"
            '      "medicine_name": "<exact or generic/brand name of medicine, e.g. Metformin, Ciprofloxacin, Atorvastatin>",\n'
            '      "dose_text": "<strength or dose, e.g. 500mg, 20mg, 1 tablet, 10ml, or \'Not specified\'>",\n'
            '      "timing_text": "<exact schedule e.g. \'Once daily at night after dinner\', \'Twice daily with meals\', \'Every 8 hours\'. If timing/schedule is absent or missing, return empty string \'\'>",\n'
            '      "instructions": "<special administration notes, e.g. \'Take with a full glass of water\', or \'Take as directed\'>",\n'
            '      "missing_fields": ["timing_text" if timing is absent/missing, "dose_text" if dose is absent],\n'
            '      "confidence": 0.95\n'
            "    }\n"
            "  ],\n"
            '  "missing_summary": "<clear clinical notice explaining specifically what critical fields are missing, or null if complete>",\n'
            '  "has_missing_info": <true if any medicine has missing timing or dose, else false>\n'
            "}\n\n"
            "STRICT RULES:\n"
            "1. Extract ONLY the medicines that are actually present in the raw OCR text. Do NOT hallucinate or default to Amoxicillin unless Amoxicillin is explicitly in the text.\n"
            "2. Critically check whether the timing/schedule of taking each medicine is present or MISSING. If missing, 'timing_text' MUST be in missing_fields, timing_text must be '', and has_missing_info must be true.\n"
            "3. Return ONLY valid JSON."
        )

        # 1. Try Groq (High-speed LPU)
        if settings.GROQ_API_KEY:
            try:
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": settings.GROQ_LLM_MODEL or "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": "You are a clinical pharmacy and prescription analysis specialist. Output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        json_match = re.search(r"\{.*\}", content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            if "medicines" in parsed and isinstance(parsed["medicines"], list):
                                logger.info(f"Groq successfully structured {len(parsed['medicines'])} medicines from OCR.")
                                return self._format_llm_result(raw_text, parsed)
            except Exception as e:
                logger.warning(f"Groq LLM prescription structuring failed: {e}. Trying fallback...")

        # 2. Try OpenRouter
        if settings.OPENROUTER_API_KEY:
            try:
                headers = {
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": settings.OPENROUTER_LLM_MODEL or "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [
                        {"role": "system", "content": "You are a clinical pharmacy specialist. Output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        json_match = re.search(r"\{.*\}", content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            if "medicines" in parsed and isinstance(parsed["medicines"], list):
                                return self._format_llm_result(raw_text, parsed)
            except Exception as e:
                logger.warning(f"OpenRouter prescription structuring failed: {e}. Trying fallback...")

        # 3. Deterministic rule-based fallback clinical parser
        return self.parse_prescription_text_fallback(raw_text)

    def _format_llm_result(self, raw_text: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and enforces field consistency on LLM output."""
        medicines = []
        overall_missing = []

        for m in parsed.get("medicines", []):
            name = str(m.get("medicine_name", "")).strip()
            if not name:
                continue
            dose = str(m.get("dose_text", "")).strip() or "As directed"
            timing = str(m.get("timing_text", "")).strip()
            inst = str(m.get("instructions", "")).strip() or "Take as directed by doctor"
            missing = list(m.get("missing_fields", []))

            # Strict verification of missing timing
            if not timing or timing.lower() in ["none", "n/a", "not specified", "null"]:
                timing = ""
                if "timing_text" not in missing:
                    missing.append("timing_text")

            if not dose or dose.lower() in ["not specified", "unknown"]:
                if "dose_text" not in missing:
                    missing.append("dose_text")

            if "timing_text" in missing:
                overall_missing.append(f"Timing of taking {name} is missing from the prescription.")
            if "dose_text" in missing:
                overall_missing.append(f"Dose / strength for {name} is missing.")

            medicines.append({
                "medicine_name": name,
                "dose_text": dose,
                "timing_text": timing,
                "instructions": inst,
                "missing_fields": missing,
                "confidence": float(m.get("confidence", 0.95))
            })

        has_missing = len(overall_missing) > 0 or parsed.get("has_missing_info", False)
        summary = parsed.get("missing_summary")
        if not summary and overall_missing:
            summary = "; ".join(overall_missing)

        return {
            "raw_text": raw_text,
            "extracted_medicines": medicines,
            "missing_summary": summary,
            "has_missing_info": has_missing
        }

    def parse_prescription_text_fallback(self, text: str) -> Dict[str, Any]:
        """Parses extracted text into medicines, identifies missing timings/doses using clinical rules."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        medicines: List[Dict[str, Any]] = []
        overall_missing = []

        for line in lines:
            line_lower = line.lower()
            found_med_name = None

            # 1. Check known common medicine list
            for med in COMMON_MEDICINES:
                if re.search(r"\b" + re.escape(med.lower()) + r"\b", line_lower):
                    found_med_name = med
                    break

            # 2. Check Rx / Tab / Cap prefix for any medicine name
            if not found_med_name:
                rx_match = re.search(r"(?:rx|tab|cap|tablet|capsule|syr|inj)[:\s]+([A-Za-z]{3,25})", line, re.IGNORECASE)
                if rx_match:
                    found_med_name = rx_match.group(1).capitalize()

            if found_med_name:
                # Extract dose
                dose = ""
                for dp in DOSE_PATTERNS:
                    dm = re.search(dp, line, re.IGNORECASE)
                    if dm:
                        dose = dm.group(0).strip()
                        break

                # Extract timing
                timing = ""
                for tp in TIMING_PATTERNS:
                    tm = re.search(tp, line, re.IGNORECASE)
                    if tm:
                        timing = tm.group(0).strip()
                        break

                # Extract instructions
                instructions = ""
                inst_match = re.search(r"(?:take|with|after|before)\s+.*", line, re.IGNORECASE)
                if inst_match and not timing:
                    instructions = inst_match.group(0).strip()

                # Identify missing critical elements
                missing_fields = []
                if not timing:
                    missing_fields.append("timing_text")
                    overall_missing.append(f"Timing of taking {found_med_name} is missing from the prescription.")
                if not dose:
                    missing_fields.append("dose_text")
                    overall_missing.append(f"Dose / strength for {found_med_name} is missing.")

                medicines.append({
                    "medicine_name": found_med_name,
                    "dose_text": dose if dose else "As directed",
                    "timing_text": timing if timing else "",
                    "instructions": instructions if instructions else "Take as directed by doctor",
                    "missing_fields": missing_fields,
                    "confidence": 0.92 if not missing_fields else 0.75
                })

        # Do NOT invent Amoxicillin if nothing was found
        if not medicines:
            return {
                "raw_text": text,
                "extracted_medicines": [],
                "missing_summary": "No medications could be recognized in the prescription text. Please verify or enter manually.",
                "has_missing_info": True
            }

        return {
            "raw_text": text,
            "extracted_medicines": medicines,
            "missing_summary": "; ".join(overall_missing) if overall_missing else None,
            "has_missing_info": len(overall_missing) > 0
        }


ocr_service = OCRService()
