import os
import re
import json
import logging
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path
from PIL import Image

import pytesseract
import requests
from app.config import (
    VLM_MODEL_ID, VLM_DEVICE, VLM_TORCH_DTYPE, VLM_MAX_NEW_TOKENS,
    OLLAMA_API_URL, CODER_MODEL_ID
)
from app.parser import ElectricalRatingParser, FormLayoutRuleParser
from app.schemas import FormExtractionData, ElectricalRatingDisaggregated

logger = logging.getLogger("vlm_service")
logging.basicConfig(level=logging.INFO)


def auto_orient_image(image: Image.Image) -> Image.Image:
    """Detects if an image is rotated (90, 180, 270) and returns the upright PIL Image."""
    try:
        w, h = image.size
        scale = min(1.0, 900 / max(w, h))
        thumb = image.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR) if scale < 1.0 else image

        scores = {}
        for ang in [0, 90, 180, 270]:
            t_img = thumb.rotate(ang, expand=True) if ang != 0 else thumb
            txt = pytesseract.image_to_string(t_img, config="--oem 1 --psm 3")
            words = re.findall(r"[a-zA-Z]{3,}", txt)
            scores[ang] = len(words)

        score_0 = scores[0]
        best_ang = 0
        best_score = score_0
        for ang in [90, 180, 270]:
            if scores[ang] > best_score:
                best_score = scores[ang]
                best_ang = ang

        # Require alternate angle to have at least 1.4x more valid words than 0° to rotate
        if best_ang != 0 and best_score >= max(20, score_0 * 1.4):
            logger.info(f"Auto-orientation corrected page by {best_ang}° (score={best_score} vs {score_0})")
            return image.rotate(best_ang, expand=True)
    except Exception as e:
        logger.debug(f"Orientation detection error: {e}")
    return image



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
        self.ollama_url = OLLAMA_API_URL
        self.coder_model_id = CODER_MODEL_ID

        self.model = None
        self.processor = None
        self.is_loaded = False
        self.loading_in_progress = False
        self.load_error: Optional[str] = None
        self.inference_lock = threading.Lock()

        self._initialized = True

    def unload_from_gpu(self) -> None:
        """Unload Qwen2.5-VL weights and free CUDA VRAM completely for local LLM inference."""
        with self.inference_lock:
            if self.model is not None or self.processor is not None:
                logger.info("Unloading Vision Model (Qwen2.5-VL) from GPU to free VRAM for LLM...")
                try:
                    import torch, gc
                    del self.model
                    del self.processor
                    self.model = None
                    self.processor = None
                    self.is_loaded = False
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.ipc_collect()
                    logger.info("GPU VRAM successfully freed!")
                except Exception as e:
                    logger.warning(f"Error unloading VLM: {e}")

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
            # Evict Ollama models from GPU to give VLM maximum VRAM
            try:
                requests.post(f"{self.ollama_url}/api/generate", json={"model": self.coder_model_id, "keep_alive": 0}, timeout=5)
            except Exception:
                pass

            import torch, gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

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
        """Run clean multi-pass OCR with natural line grouping (space-joined, no artificial pipe bars)."""
        try:
            img = Image.open(image_path)
            # Run image_to_data for bounding box coordinates
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--oem 1 --psm 3")
            
            # Cluster words into horizontal rows based on Y-coordinates
            lines_dict = {}
            for i in range(len(data.get("text", []))):
                txt = data["text"][i].strip()
                conf = int(data["conf"][i]) if str(data["conf"][i]).isdigit() or isinstance(data["conf"][i], (int, float)) else 0
                if not txt or conf < 15:
                    continue
                top = data["top"][i]
                left = data["left"][i]
                
                bucket = None
                for y in lines_dict:
                    if abs(y - top) <= 18:
                        bucket = y
                        break
                if bucket is None:
                    bucket = top
                    lines_dict[bucket] = []
                lines_dict[bucket].append((left, txt))
            
            cleaned_text = ""
            if len(lines_dict) >= 5:
                sorted_y = sorted(lines_dict.keys())
                reconstructed_lines = []
                for y in sorted_y:
                    row_words = sorted(lines_dict[y], key=lambda x: x[0])
                    # Join words with space for clean reading order, NEVER artificial '|'
                    row_str = " ".join([w[1] for w in row_words])
                    reconstructed_lines.append(row_str)
                cleaned_text = "\n".join(reconstructed_lines)

            # Standard PSM 3 text
            std_text = pytesseract.image_to_string(img, config="--oem 1 --psm 3").strip()
            
            if cleaned_text and len(cleaned_text) > len(std_text) * 0.7:
                return cleaned_text
            return std_text if std_text else cleaned_text
        except Exception as err:
            logger.warning(f"OCR failed for {image_path}: {err}")
            try:
                return pytesseract.image_to_string(Image.open(image_path), config="--oem 1 --psm 3").strip()
            except Exception:
                return ""

    def _query_local_coder_llm(self, document_text: str, doc_hint: str = "") -> Optional[Dict[str, Any]]:
        """Query local Qwen 2.5 Coder via Ollama on GPU to reconstruct tables and extract structured fields."""
        try:
            logger.info(f"Querying local Coder LLM ({self.coder_model_id}) on GPU for table reconstruction & field synthesis...")
            prompt = f"""You are an expert electrical test documentation engineer.
Analyze the following text and table data extracted via high-resolution OCR from an electrical test document:

\"\"\"
{document_text[:12000]}
\"\"\"

Your tasks:
1. Identify the Document Type and Format Number (e.g. CPRI Customer Request Form CPRI/QAF/01A, Transformer Loss Measurement Datasheet, Pressure Test Logsheet, Routine Test Logsheet, etc.).
2. Extract all metadata into structured fields:
   - "customer_name": Customer / manufacturer company name
   - "customer_address": Customer address
   - "rating_raw": Complete electrical rating string (e.g. 250 KVA/11kV/433V, 3PH, 50Hz Copperwound)
   - "sample_name": Equipment or sample description
   - "serial_number": Serial number or sample ID (e.g. 1098 or HVD25S0847)
   - "tests_requested": Tests requested or test category
   - "format_no": Document format number
3. Reconstruct ALL measurement, calibration, and test data tables into clean, aligned Markdown tables with headers, units, and all numeric values preserved.
4. Output a clean, complete full transcription with the structured tables included.

Return a valid JSON object with EXACTLY this structure:
{{
  "document_type": "CUSTOMER_REQUEST_FORM", "LOGSHEET", "DATASHEET", "WORK_INSTRUCTION", or "GENERAL_DOCUMENT",
  "is_valid_crf": true or false,
  "format_no": "...",
  "customer_name": "...",
  "customer_address": "...",
  "sample_name": "...",
  "rating_raw": "...",
  "serial_number": "...",
  "tests_requested": "...",
  "structured_tables": "### Measurement Tables\\n\\n| Column 1 | Column 2 | ... |\\n|---|---|---|\\n| ... | ... | ... |",
  "full_transcription": "Complete text with structured tables included."
}}

CRITICAL: Return ONLY the valid JSON block without introductory or conversational prose."""

            payload = {
                "model": self.coder_model_id,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": 4096,
                    "temperature": 0.1,
                    "repeat_penalty": 1.2,
                    "num_predict": 1024
                }
            }
            
            resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=90)
            if resp.status_code == 200:
                raw_resp = resp.json().get("response", "").strip()
                data = self._parse_json_from_text(raw_resp)
                if data:
                    logger.info("Successfully received structured tables and fields from Qwen 2.5 Coder!")
                    return data
        except Exception as err:
            logger.warning(f"Local Coder LLM query skipped or error: {err}")
        return None

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

        # Step 2: Attempt VLM inference if model is ready or if document contains scanned pages/handwriting
        vlm_data: Optional[Dict[str, Any]] = None
        
        # Check if vision model should be run
        import torch
        has_cuda = torch.cuda.is_available()
        # All scanned documents without native embedded text benefit from high-accuracy VLM
        has_embedded = any(len(embedded_texts.get(i + 1, "").strip()) > 50 for i in range(len(page_image_paths))) if embedded_texts else False
        needs_vision = has_cuda or not has_embedded or os.getenv("VLM_AUTO_LOAD", "false").lower() in ("true", "1")

        if not self.is_loaded and needs_vision and not self.loading_in_progress:
            logger.info("Loading Vision Model (Qwen2.5-VL) on GPU for high-accuracy handwriting & table inspection...")
            self.load_model(async_load=False)

        if self.is_loaded and self.model is not None and self.processor is not None:
            try:
                vlm_data = self._infer_vlm(page_image_paths)
            except Exception as vlm_err:
                logger.error(f"VLM inference encountered error: {vlm_err}. Falling back to rule-based engine.")
            finally:
                # Force GPU VRAM unloading so other services have full GPU memory
                self.unload_from_gpu()

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

        # Structured tables from VLM
        structured_tables_md = vlm_data.get("structured_tables") if vlm_data else None

        # Document Classification & Validation
        combined_text = full_raw_text.lower()
        doc_type_src = (vlm_data or {}).get("document_type")
        if doc_type_src == "PROFORMA_FOR_TRANSFORMERS" or "proforma for transformers" in combined_text:
            doc_type = "PROFORMA_FOR_TRANSFORMERS"
            is_valid_crf = False
            val_msg = "Document identified as Proforma for Transformers. Technical specifications and test requirements extracted."
        elif doc_type_src == "CUSTOMER_REQUEST_FORM" or "customer request form" in combined_text or "cpri/qaf/01a" in combined_text:
            doc_type = "CUSTOMER_REQUEST_FORM"
            is_valid_crf = True
            val_msg = "Valid CPRI/QAF/01A Customer Request Form detected. Field identification active."
        elif doc_type_src == "WORK_INSTRUCTION" or "work instruction" in combined_text or "cpri/qaf/02" in combined_text:
            doc_type = "WORK_INSTRUCTION"
            is_valid_crf = False
            val_msg = "Document identified as Work Instruction (CPRI/QAF/02)."
        elif doc_type_src == "DATASHEET" or "datasheet" in combined_text or "losses calculation" in combined_text:
            doc_type = "DATASHEET"
            is_valid_crf = False
            val_msg = "Document identified as Laboratory Datasheet. Tabular calculation data extracted."
        elif doc_type_src == "LOGSHEET" or any(k in combined_text for k in ["log sheet", "log-sheet", "loss measurement", "routine test", "short circuit", "oil leakage", "temp. rise"]):
            doc_type = "LOGSHEET"
            is_valid_crf = False
            val_msg = "Document identified as Laboratory Test Logsheet. Tabular measurement data extracted."
        else:
            doc_type = "GENERAL_DOCUMENT"
            is_valid_crf = False
            val_msg = "Raw text and tables extracted below."

        # Step 4: Rule-based extraction from OCR
        rule_data = FormLayoutRuleParser.extract_from_ocr_pages(page_texts)

        # Step 5: Merge results intelligently
        final_payload = self._merge_extractions(vlm_data, rule_data)
        if structured_tables_md:
            final_payload["structured_tables"] = structured_tables_md

        # Only query Coder LLM if structured tables are missing and tabular keywords exist in text
        if not structured_tables_md and ("|" in full_raw_text or any(k in combined_text for k in ["sl.no", "voltage", "current", "loss", "temperature"])):
            coder_data = self._query_local_coder_llm(full_raw_text)
            if coder_data:
                if coder_data.get("structured_tables"):
                    structured_tables_md = str(coder_data["structured_tables"]).strip()
                    final_payload["structured_tables"] = structured_tables_md
                for field in ["customer_name", "rating_raw", "serial_number", "sample_name", "tests_requested"]:
                    c_val = coder_data.get(field)
                    if c_val and str(c_val).strip() and not str(c_val).strip().startswith("..."):
                        if not final_payload.get(field) or len(str(final_payload.get(field)).strip()) < 3:
                            final_payload[field] = str(c_val).strip()

        # Step 6: Ensure electrical ratings are rigorously disaggregated
        raw_rating_text = (
            f"{final_payload.get('rating_raw', '')} "
            f"{final_payload.get('sample_description', '')} "
            f"{final_payload.get('sample_type', '')}"
        )
        final_payload["ratings"] = ElectricalRatingParser.parse_ratings(raw_rating_text)

        # Prepend clean identified summary to Sheet 1 text
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
        elif doc_type == "PROFORMA_FOR_TRANSFORMERS" and final_payload.get("serial_number"):
            header_summary = (
                f"[IDENTIFIED TRANSFORMER PROFORMA FIELDS]\n"
                f"Serial Number: {final_payload.get('serial_number')}\n"
                f"Rating: {final_payload.get('rating_raw')}\n"
                f"Sample: {final_payload.get('sample_name') or 'Distribution Transformer'}\n"
                f"Tests Requested: {final_payload.get('tests_requested')}\n"
                f"{'=' * 45}\n\n"
            )
            if header_summary not in full_raw_text:
                full_raw_text = header_summary + full_raw_text
            if 1 in page_dict and header_summary not in page_dict[1]:
                page_dict[1] = header_summary + page_dict[1]

        # Attach raw text, tables, and document validation
        final_payload["document_type"] = doc_type
        final_payload["is_valid_crf"] = is_valid_crf
        final_payload["validation_message"] = val_msg
        final_payload["structured_tables"] = structured_tables_md
        final_payload["raw_extracted_text"] = full_raw_text
        final_payload["page_texts"] = page_dict

        # Build schema
        return FormExtractionData(**final_payload)

    def _infer_vlm_page(self, image_path: str, page_num: int, total_pages: int) -> Optional[Dict[str, Any]]:
        """Run single-page visual inference with Qwen2.5-VL in 4-bit NF4 quantization."""
        import torch

        try:
            img = Image.open(image_path).convert("RGB")
            # Downscale high-resolution scans to max dimension 1024 for VRAM stability & handwriting retention
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

            prompt = (
                f"You are an expert document OCR and technical specification analysis AI.\n"
                f"Analyze this electrical test / engineering document page (Page {page_num} of {total_pages}) with extreme accuracy.\n"
                f"Carefully extract all printed text, handwritten entries (names, ratings, numbers), checkboxes ([√] or [ ]), and tables.\n"
                f"CRITICAL: Do NOT invent placeholder dots ('...') or random bars ('|'). Output the exact text and numbers.\n\n"
                f"Return a valid JSON object with the following fields:\n"
                f"{{\n"
                f'  "document_type": "CUSTOMER_REQUEST_FORM", "PROFORMA_FOR_TRANSFORMERS", "LOGSHEET", "DATASHEET", "WORK_INSTRUCTION", or "GENERAL_DOCUMENT",\n'
                f'  "format_no": "Document format or issue number if visible, e.g. CPRI/QAF/01A or CPRI/QAF/12",\n'
                f'  "customer_name": "Customer or manufacturer company name if visible on this page, else empty string",\n'
                f'  "customer_address": "Customer address if visible, else empty string",\n'
                f'  "sample_name": "Equipment or sample description (e.g. Distribution Transformer)",\n'
                f'  "sample_description": "Additional sample description if visible",\n'
                f'  "serial_number": "Serial number or sample code (e.g. 1098 or APT/250-11/001)",\n'
                f'  "rating_raw": "Complete electrical rating string (e.g. 250 kVA, 11000/433V, 3Ph, 50Hz, Dyn11, ONAN)",\n'
                f'  "tests_requested": "Tests requested or test table summary",\n'
                f'  "tables_markdown": "Clean Markdown tables for any test tables, winding details, or parameter tables on this page, or empty string if none",\n'
                f'  "transcription": "Complete verbatim markdown transcription of all text, handwriting, checkboxes, and tables on this page in natural reading order without random bars"\n'
                f"}}\n"
                f"Return ONLY valid JSON."
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            prompt_text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            from qwen_vl_utils import process_vision_info
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[prompt_text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )

            target_device = self.model.device if hasattr(self.model, "device") else "cuda" if torch.cuda.is_available() else "cpu"
            inputs = inputs.to(target_device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=1800,
                    temperature=0.1,
                    do_sample=False,
                )

            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
            ]
            output_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            logger.info(f"Page {page_num} VLM inference completed ({len(output_text)} chars generated)")
            return self._parse_json_from_text(output_text)
        except Exception as err:
            logger.error(f"Error in VLM page {page_num} inference: {err}")
            return None

    def _infer_vlm(self, page_image_paths: List[str]) -> Optional[Dict[str, Any]]:
        """Run page-by-page visual inference with Qwen2.5-VL and merge results."""
        with self.inference_lock:
            total_pages = len(page_image_paths)
            page_results = []
            page_transcriptions = {}
            all_tables = []
            
            for idx, img_path in enumerate(page_image_paths):
                page_num = idx + 1
                logger.info(f"Processing Page {page_num}/{total_pages} with VLM...")
                res = self._infer_vlm_page(img_path, page_num, total_pages)
                if res:
                    page_results.append(res)
                    tx = res.get("transcription") or ""
                    if tx:
                        page_transcriptions[page_num] = tx
                    tbl = res.get("tables_markdown") or ""
                    if tbl and tbl.strip() and "|" in tbl:
                        all_tables.append(tbl.strip())
                else:
                    logger.warning(f"VLM returned no result for Page {page_num}")

            if not page_results:
                return None

            # Merge aggregated fields
            merged: Dict[str, Any] = {
                "page_transcriptions": page_transcriptions,
                "structured_tables": "\n\n".join(all_tables) if all_tables else None,
            }

            # Extract best metadata across pages
            for res in page_results:
                for k in ["document_type", "format_no", "customer_name", "customer_address", 
                          "sample_name", "sample_description", "serial_number", "rating_raw", "tests_requested"]:
                    val = res.get(k)
                    if isinstance(val, list):
                        val = ", ".join([str(v) for v in val])
                    if val and str(val).strip() and str(val).strip().lower() not in ("none", "n/a", "...", "-", ""):
                        if k not in merged or len(str(val)) > len(str(merged.get(k, ""))):
                            merged[k] = val

            # Build full transcription from page transcriptions
            if page_transcriptions:
                full_tx_parts = [
                    f"--- SHEET {p} ---\n{page_transcriptions[p]}"
                    for p in sorted(page_transcriptions.keys())
                ]
                merged["full_transcription"] = "\n\n=== SHEET BREAK ===\n\n".join(full_tx_parts)

            return merged

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
