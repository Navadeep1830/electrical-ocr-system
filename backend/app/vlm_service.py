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


VLM_SYSTEM_PROMPT = """You are an expert electrical engineer and forensic document analyzer.
Your task is to analyze scanned CPRI (Central Power Research Institute) Customer Request Forms (format CPRI/QAF/01A).
Carefully read both printed text and handwritten entries across all sheets.
Disaggregate and extract every specification with extreme accuracy into a clean JSON object.

Extract into this exact JSON structure:
{
  "format_no": "CPRI/QAF/01A",
  "issue_no": "02",
  "revision_no": "00",
  "division_name": "SHORT CIRCUIT LABORATORY",
  "customer_name": "...",
  "customer_address": "...",
  "sample_name": "...",
  "rating_raw": "...",
  "sample_description": "...",
  "sample_type": "...",
  "serial_number": "...",
  "manufacturer_details": "...",
  "drawing_number": "...",
  "customer_requirement": "...",
  "evaluation_criteria": "...",
  "number_of_samples": "...",
  "sample_disposal": "...",
  "tests_requested": "...",
  "specific_instructions": "...",
  "customer_representative": "...",
  "witness_other": "...",
  "report_dispatch_to": "...",
  "report_dispatch_mode": "...",
  "additional_reports": "...",
  "msme_discount": "Applicable or Not Applicable",
  "conformity_required": true,
  "conformity_rule": "...",
  "physical_condition_sample": "Suitable for Testing or Not suitable",
  "lab_capability": "Yes or No",
  "test_engineer_name": "...",
  "deviations_noticed": "...",
  "confidence_scores": {
    "customer_name": 0.95,
    "rating_raw": 0.92,
    "serial_number": 0.90,
    "manufacturer_details": 0.88,
    "tests_requested": 0.91,
    "conformity_rule": 0.89
  }
}

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

    def extract_document(self, page_image_paths: List[str]) -> FormExtractionData:
        """Extract all structured fields from document page images using VLM or fallback OCR."""
        if not page_image_paths:
            return FormExtractionData()

        # Step 1: Execute OCR on each page (also used for fallback and spatial context)
        page_texts: List[str] = []
        page_dict: Dict[int, str] = {}
        for idx, path in enumerate(page_image_paths):
            try:
                img = Image.open(path)
                ocr_str = pytesseract.image_to_string(img, config="--psm 6")
                page_texts.append(ocr_str)
                page_dict[idx + 1] = ocr_str.strip()
            except Exception as ocr_err:
                logger.warning(f"OCR failed for {path}: {ocr_err}")
                page_texts.append("")
                page_dict[idx + 1] = ""

        full_raw_text = "\n\n=== SHEET BREAK ===\n\n".join(
            [f"--- SHEET {i+1} ---\n{t}" for i, t in enumerate(page_texts)]
        )

        # Document Classification & Validation
        combined_text = full_raw_text.lower()
        if "customer request form" in combined_text or "cpri/qaf/01a" in combined_text:
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

        # Step 2: Attempt VLM inference if model is ready
        vlm_data: Optional[Dict[str, Any]] = None
        if self.is_loaded and self.model is not None and self.processor is not None:
            try:
                vlm_data = self._infer_vlm(page_image_paths)
            except Exception as vlm_err:
                logger.error(f"VLM inference encounter error: {vlm_err}. Falling back to rule-based engine.")

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
                "text": "Analyze all pages of this CPRI Customer Request Form and extract all information into JSON as requested."
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
        """Extract and parse JSON object from markdown block or raw text."""
        # Check ```json ... ```
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            candidate = match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Check raw curly brackets { ... }
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

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
