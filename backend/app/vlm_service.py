import os
import re
import json
import logging
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path
from PIL import Image

import pytesseract
from app.config import VLM_MODEL_ID, VLM_DEVICE, VLM_TORCH_DTYPE, VLM_MAX_NEW_TOKENS
from app.parser import ElectricalRatingParser, FormLayoutRuleParser
from app.schemas import FormExtractionData, ElectricalRatingDisaggregated

logger = logging.getLogger("vlm_service")
logging.basicConfig(level=logging.INFO)


VLM_SYSTEM_PROMPT = """You are an expert document OCR and forensic document analysis AI.
Your task is to analyze and extract text from this document with extreme accuracy.
Carefully read ALL printed text, tabular columns, headers, check marks, and all handwritten notes/entries across all pages.
CRITICAL: Do NOT output placeholder dots like '...'. If text or handwriting is present, transcribe the exact words into the field.

Return a valid JSON object with the following fields:
1. "document_type": "CUSTOMER_REQUEST_FORM" if format CPRI/QAF/01A, "WORK_INSTRUCTION" if work instruction, "LOGSHEET" if log sheet, "DATASHEET" if datasheet, or "GENERAL_DOCUMENT".
2. "is_valid_crf": true if standard CPRI Customer Request Form (CPRI/QAF/01A), else false.
3. If CPRI Customer Request Form (CPRI/QAF/01A), transcribe all handwritten and printed values:
   "format_no": "CPRI/QAF/01A",
   "issue_no": "02",
   "revision_no": "00",
   "division_name": "SHORT CIRCUIT LABORATORY",
   "customer_name": "Transcribe exact customer company name from Sheet 1, e.g. A.P. TRANSFORMERS",
   "customer_address": "Transcribe customer address from Sheet 1",
   "sample_name": "Transcribe sample name, e.g. Distribution Transformer",
   "rating_raw": "Transcribe complete electrical rating string, e.g. 250 KVA/11kV/433V, 3PH, 50Hz Copperwound",
   "sample_description": "Transcribe sample description",
   "sample_type": "Transcribe type/indoor/outdoor",
   "serial_number": "Transcribe serial number, e.g. APT/250-11/001 or 1098",
   "manufacturer_details": "Transcribe manufacturer details",
   "drawing_number": "Transcribe drawing number",
   "customer_requirement": "Customer requirement standard or specification",
   "evaluation_criteria": "Evaluation criteria standard",
   "number_of_samples": "Number of samples",
   "sample_disposal": "Taking back the sample after testing",
   "tests_requested": "Transcribe tests requested, e.g. Type test",
   "specific_instructions": "Specific testing instructions",
   "customer_representative": "Name of customer representative",
   "witness_other": "Witness details if any",
   "report_dispatch_to": "Report dispatch address",
   "report_dispatch_mode": "Report dispatch mode",
   "additional_reports": "Additional reports required",
   "msme_discount": "Applicable or Not Applicable",
   "conformity_required": true,
   "conformity_rule": "Conformity rule statement",
   "physical_condition_sample": "Suitable for Testing",
   "lab_capability": "Yes",
   "test_engineer_name": "Name of test engineer",
   "deviations_noticed": "Any deviations noticed",
   "confidence_scores": {
     "customer_name": 0.95,
     "rating_raw": 0.95,
     "serial_number": 0.90,
     "manufacturer_details": 0.88,
     "tests_requested": 0.92,
     "conformity_rule": 0.90
   },
4. "full_transcription": "Complete verbatim transcription of all text, handwriting, and tables across all pages in natural reading order."

Return ONLY the valid JSON block without introductory or concluding conversational text."""


class VLMInferenceEngine:
    """Manages local VLM inference (Qwen2.5-VL-3B-Instruct) with device memory management,

    concurrency locks, and high-accuracy deterministic OCR fallback.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.model_id = VLM_MODEL_ID
        self.device_setting = VLM_DEVICE
        self.torch_dtype = VLM_TORCH_DTYPE
        self.max_new_tokens = VLM_MAX_NEW_TOKENS

        self.model = None
        self.processor = None
        self.is_loaded = False
        self.loading_in_progress = False
        self.load_error: Optional[str] = None
        self.inference_lock = threading.Lock()

        self._initialized = True

    def get_status(self) -> Dict[str, Any]:
        """Return runtime status of the VLM engine and GPU memory usage."""
        gpu_info = {"available": False, "device_name": None, "vram_allocated_mb": 0, "vram_reserved_mb": 0}

        try:
            import torch
            if torch.cuda.is_available():
                gpu_info["available"] = True
                gpu_info["device_name"] = torch.cuda.get_device_name(0)
                gpu_info["vram_allocated_mb"] = round(torch.cuda.memory_allocated(0) / (1024 * 1024), 2)
                gpu_info["vram_reserved_mb"] = round(torch.cuda.memory_reserved(0) / (1024 * 1024), 2)
        except Exception:
            pass

        return {
            "model_id": self.model_id,
            "is_loaded": self.is_loaded,
            "loading_in_progress": self.loading_in_progress,
            "load_error": self.load_error,
            "device_setting": self.device_setting,
            "gpu": gpu_info,
            "ocr_fallback_ready": True,
        }

    def load_model(self, async_load: bool = True) -> None:
        """Trigger loading of Qwen2.5-VL-3B-Instruct weights."""
        if self.is_loaded or self.loading_in_progress:
            return

        if async_load:
            thread = threading.Thread(target=self._load_model_worker, daemon=True)
            thread.start()
        else:
            self._load_model_worker()

    def _load_model_worker(self) -> None:
        with self._lock:
            if self.is_loaded or self.loading_in_progress:
                return
            self.loading_in_progress = True
            self.load_error = None

        logger.info(f"Starting VLM load: {self.model_id}")
        try:
            import torch
            from transformers import AutoProcessor

            # Try importing Qwen2_5_VL or general AutoModel
            try:
                from transformers import Qwen2_5_VLForConditionalGeneration as ModelClass
            except ImportError:
                from transformers import AutoModelForVision2Seq as ModelClass

            target_dtype = torch.float16 if self.torch_dtype == "float16" and torch.cuda.is_available() else torch.float32
            device_map = "auto" if torch.cuda.is_available() and self.device_setting in ("auto", "cuda") else None

            logger.info(f"Loading processor for {self.model_id}...")
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                trust_remote_code=True,
                local_files_only=os.path.isdir(self.model_id)
            )

            logger.info(f"Loading model weights for {self.model_id} (dtype={target_dtype}, device_map={device_map})...")
            model_kwargs = {
                "trust_remote_code": True,
                "local_files_only": os.path.isdir(self.model_id)
            }

            if torch.cuda.is_available():
                try:
                    from transformers import BitsAndBytesConfig
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_quant_type="nf4",
                    )
                    model_kwargs["quantization_config"] = bnb_config
                    logger.info("Configured 4-bit NF4 quantization for GPU VRAM optimization!")
                except Exception as bnb_err:
                    logger.warning(f"BitsAndBytes config skipped: {bnb_err}. Using float16.")
                    model_kwargs["torch_dtype"] = target_dtype
            else:
                model_kwargs["torch_dtype"] = target_dtype

            if device_map:
                model_kwargs["device_map"] = device_map

            self.model = ModelClass.from_pretrained(self.model_id, **model_kwargs)

            if not device_map and torch.cuda.is_available() and self.device_setting in ("auto", "cuda"):
                self.model = self.model.to("cuda")

            self.model.eval()
            self.is_loaded = True
            logger.info("VLM loaded successfully and ready for inference!")
        except Exception as exc:
            self.load_error = str(exc)
            logger.warning(f"Failed to load VLM model ({self.model_id}): {exc}. Engine will use OCR+heuristic pipeline.")
        finally:
            self.loading_in_progress = False

    def _run_enhanced_ocr(self, image_path: str) -> str:
        """Run adaptive multi-pass OCR using PIL/OpenCV for maximum accuracy."""
        try:
            import cv2
            img = Image.open(image_path)
            # Pass 1: Standard PSM 3 (auto page segmentation)
            text_p3 = pytesseract.image_to_string(img, config="--oem 1 --psm 3").strip()
            
            # Pass 2: Grayscale with CLAHE contrast enhancement for low-contrast/faded scans
            try:
                cv_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                if cv_img is not None:
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    enhanced = clahe.apply(cv_img)
                    text_p6 = pytesseract.image_to_string(enhanced, config="--oem 1 --psm 6").strip()
                    if len(text_p6) > len(text_p3) * 1.15:
                        return text_p6
            except Exception:
                pass
            return text_p3 if text_p3 else pytesseract.image_to_string(img, config="--oem 1 --psm 6").strip()
        except Exception as err:
            logger.warning(f"OCR failed for {image_path}: {err}")
            return ""

    def extract_document(
        self, 
        page_image_paths: List[str],
        embedded_texts: Optional[Dict[int, str]] = None
    ) -> FormExtractionData:
        """Extract all structured fields from document page images using VLM or fallback OCR."""
        if not page_image_paths:
            return FormExtractionData()

        # Step 1: Execute OCR or use native embedded PDF text
        page_texts: List[str] = []
        page_dict: Dict[int, str] = {}
        for idx, path in enumerate(page_image_paths):
            page_num = idx + 1
            if embedded_texts and embedded_texts.get(page_num) and len(embedded_texts[page_num].strip()) > 30:
                p_text = embedded_texts[page_num].strip()
            else:
                p_text = self._run_enhanced_ocr(path)
            page_texts.append(p_text)
            page_dict[page_num] = p_text

        # Step 2: Attempt VLM inference if model is ready
        vlm_data: Optional[Dict[str, Any]] = None
        if self.is_loaded and self.model is not None and self.processor is not None:
            try:
                vlm_data = self._infer_vlm(page_image_paths)
            except Exception as vlm_err:
                logger.error(f"VLM inference encountered error: {vlm_err}. Falling back to rule-based engine.")

        # If VLM provided page-by-page transcriptions, integrate them for highest accuracy
        if vlm_data and vlm_data.get("page_transcriptions"):
            page_trans = vlm_data["page_transcriptions"]
            for idx in range(len(page_image_paths)):
                page_num = idx + 1
                v_text = page_trans.get(str(page_num)) or page_trans.get(page_num)
                if v_text and len(str(v_text).strip()) > 30:
                    page_dict[page_num] = str(v_text).strip()
            page_texts = [page_dict[i + 1] for i in range(len(page_image_paths))]

        full_raw_text = "\n\n=== SHEET BREAK ===\n\n".join(
            [f"--- SHEET {i+1} ---\n{page_dict[i+1]}" for i in range(len(page_image_paths))]
        )

        if vlm_data and vlm_data.get("full_transcription") and len(str(vlm_data["full_transcription"]).strip()) > len(full_raw_text):
            full_raw_text = str(vlm_data["full_transcription"]).strip()

        # Document Classification & Validation
        combined_text = full_raw_text.lower()
        if vlm_data and "document_type" in vlm_data and vlm_data["document_type"] in ("CUSTOMER_REQUEST_FORM", "WORK_INSTRUCTION", "LOGSHEET", "DATASHEET"):
            doc_type = vlm_data["document_type"]
            is_valid_crf = vlm_data.get("is_valid_crf", doc_type == "CUSTOMER_REQUEST_FORM")
            if is_valid_crf:
                val_msg = "Valid CPRI/QAF/01A Customer Request Form detected. Field identification active."
            else:
                val_msg = f"Document identified as {doc_type.replace('_', ' ').title()}. It does not contain standard Customer Request Form fields."
        elif "customer request form" in combined_text or "cpri/qaf/01a" in combined_text:
            doc_type = "CUSTOMER_REQUEST_FORM"
            is_valid_crf = True
            val_msg = "Valid CPRI/QAF/01A Customer Request Form detected. Field identification active."
        elif "work instruction" in combined_text or "cpri/qaf/02" in combined_text:
            doc_type = "WORK_INSTRUCTION"
            is_valid_crf = False
            val_msg = "Document identified as 'Work Instruction' (CPRI/QAF/02). It does not contain standard Customer Request Form fields."
        elif any(k in combined_text for k in ["log sheet", "log-sheet", "loss measurement", "routine test", "short circuit", "oil leakage", "temp. rise"]):
            doc_type = "LOGSHEET"
            is_valid_crf = False
            val_msg = "Document identified as Laboratory Test Logsheet. It does not contain standard Customer Request Form fields."
        elif "proforma for transformers" in combined_text:
            doc_type = "TRANSFORMER_PROFORMA"
            is_valid_crf = False
            val_msg = "Document identified as Transformer Proforma. It does not contain standard Customer Request Form fields."
        else:
            doc_type = "GENERAL_DOCUMENT"
            is_valid_crf = False
            val_msg = "This document does not match standard CPRI Customer Request Form (CPRI/QAF/01A) fields. Raw text extracted below."

        # Step 3: Rule-based extraction from OCR
        rule_data = FormLayoutRuleParser.extract_from_ocr_pages(page_texts)

        # Step 4: Merge results intelligently
        final_payload = self._merge_extractions(vlm_data, rule_data)

        # Step 5: Ensure electrical ratings are rigorously disaggregated
        raw_rating_text = (
            f"{final_payload.get('rating_raw', '')} "
            f"{final_payload.get('sample_description', '')} "
            f"{final_payload.get('sample_type', '')}"
        )
        final_payload["ratings"] = ElectricalRatingParser.parse_ratings(raw_rating_text)

        # Prepend clean identified summary to Sheet 1 text if valid CRF
        if is_valid_crf and final_payload.get("customer_name"):
            header_summary = (
                f"[IDENTIFIED CPRI CRF FIELDS]\n"
                f"Customer Name: {final_payload.get('customer_name')}\n"
                f"Rating: {final_payload.get('rating_raw')}\n"
                f"Sample: {final_payload.get('sample_name') or final_payload.get('sample_description')}\n"
                f"Serial Number: {final_payload.get('serial_number')}\n"
                f"Tests Requested: {final_payload.get('tests_requested')}\n"
                f"{'=' * 45}\n\n"
            )
            if header_summary not in full_raw_text:
                full_raw_text = header_summary + full_raw_text
            if 1 in page_dict and header_summary not in page_dict[1]:
                page_dict[1] = header_summary + page_dict[1]

        # Attach raw text and document validation
        final_payload["document_type"] = doc_type
        final_payload["is_valid_crf"] = is_valid_crf
        final_payload["validation_message"] = val_msg
        final_payload["raw_extracted_text"] = full_raw_text
        final_payload["page_texts"] = page_dict

        # Build schema
        return FormExtractionData(**final_payload)

    def _infer_vlm(self, page_image_paths: List[str]) -> Optional[Dict[str, Any]]:
        """Run multi-image prompt through Qwen2.5-VL."""
        import torch

        with self.inference_lock:
            images = []
            for p in page_image_paths:
                img = Image.open(p).convert("RGB")
                img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                images.append(img)

            logger.info(f"Running VLM generation on {len(images)} pages (resolution: {[img.size for img in images]})...")

            # Construct message with images
            content = []
            for img in images:
                content.append({"type": "image", "image": img})
            content.append({
                "type": "text",
                "text": "Analyze all pages of this document. Transcribe the text verbatim and extract all actual handwritten and printed values into the JSON fields. Do not output placeholder dots ('...')."
            })

            messages = [
                {"role": "system", "content": VLM_SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ]

            # Process input
            try:
                from qwen_vl_utils import process_vision_info
                image_inputs, video_inputs = process_vision_info(messages)
            except ImportError:
                image_inputs = images
                video_inputs = None

            prompt_text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.processor(
                text=[prompt_text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )

            # Move inputs to model device
            target_device = self.model.device if hasattr(self.model, "device") else "cuda" if torch.cuda.is_available() else "cpu"
            inputs = inputs.to(target_device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    temperature=0.1,
                    do_sample=False,
                )

            # Slice output tokens
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
            ]
            output_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            logger.info(f"VLM raw output generated (length {len(output_text)} chars): {output_text[:300]}...")
            return self._parse_json_from_text(output_text)

    def _parse_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from markdown block or raw text with repair support."""
        # 1. Extract JSON candidate block
        candidate = None
        match = re.search(r'```(?:json)?\s*([\s\S]*?)(?:```|$)', text)
        if match:
            candidate = match.group(1).strip()
        else:
            first_brace = text.find('{')
            if first_brace != -1:
                candidate = text[first_brace:].strip()

        if not candidate:
            return None

        # 2. Try direct parse
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 3. Try standard regex curly bracket match
        curly_match = re.search(r'\{[\s\S]*\}', candidate)
        if curly_match:
            try:
                return json.loads(curly_match.group(0))
            except Exception:
                pass

        # 4. Truncated JSON repair: step backwards through lines, balance quotes and braces
        lines = candidate.splitlines()
        for i in range(len(lines), 0, -1):
            sub_str = "\n".join(lines[:i]).strip()
            sub_str = re.sub(r',\s*$', '', sub_str)
            if sub_str.count('"') % 2 != 0:
                sub_str += '"'
            sub_str = re.sub(r',\s*$', '', sub_str)
            open_curly = sub_str.count('{') - sub_str.count('}')
            open_square = sub_str.count('[') - sub_str.count(']')
            fixed = sub_str + (']' * max(0, open_square)) + ('}' * max(0, open_curly))
            try:
                parsed = json.loads(fixed)
                logger.info(f"Successfully repaired truncated VLM JSON ({len(parsed)} keys recovered)")
                return parsed
            except Exception:
                continue

        return None

    def _merge_extractions(self, vlm_data: Optional[Dict[str, Any]], rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fuse VLM and rule-based extractions with confidence estimation."""
        result = dict(rule_data)
        confidence: Dict[str, float] = {}

        # Default confidence for rule/OCR baseline
        for key in result.keys():
            if result.get(key):
                confidence[key] = 0.85
            else:
                confidence[key] = 0.50

        # If VLM succeeded, merge fields and boost confidence
        if vlm_data:
            vlm_conf = vlm_data.get("confidence_scores", {})
            for key, val in vlm_data.items():
                if key in ("ratings", "confidence_scores"):
                    continue
                if val:
                    val_str = str(val).strip()
                    if val_str not in ("...", "N/A", "None", "-"):
                        result[key] = val
                        confidence[key] = vlm_conf.get(key, 0.94)

        result["confidence_scores"] = confidence
        return result


# Global singleton instance
vlm_engine = VLMInferenceEngine()
