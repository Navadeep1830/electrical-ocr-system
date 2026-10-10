import logging
import torch
from typing import List, Optional, Dict, Any
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

logger = logging.getLogger("trocr_service")
logging.basicConfig(level=logging.INFO)


class TrOCRService:
    """Manages microsoft/trocr-base-handwritten model for high-precision recognition
    of handwritten numbers, symbols, resistances (Ohms, milli-Ohms), and annotations.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.model_id = "microsoft/trocr-base-handwritten"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor: Optional[TrOCRProcessor] = None
        self.model: Optional[VisionEncoderDecoderModel] = None
        self.is_loaded = False
        self._initialized = True

    def load_model(self):
        if self.is_loaded:
            return
        logger.info(f"Loading TrOCR model ({self.model_id}) on {self.device}...")
        try:
            self.processor = TrOCRProcessor.from_pretrained(self.model_id)
            self.model = VisionEncoderDecoderModel.from_pretrained(self.model_id)
            if self.device == "cuda":
                self.model = self.model.half().to("cuda")
            else:
                self.model = self.model.to("cpu")
            self.model.eval()
            self.is_loaded = True
            logger.info("TrOCR model loaded successfully into memory!")
        except Exception as e:
            logger.error(f"Failed to load TrOCR model: {e}")

    def unload(self):
        """Unload TrOCR model from GPU memory."""
        if self.model is not None:
            import gc
            logger.info("Unloading TrOCR model to free GPU VRAM...")
            del self.model
            del self.processor
            self.model = None
            self.processor = None
            self.is_loaded = False
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def recognize_crop(self, crop: Image.Image) -> str:
        """Transcribe a single cropped region containing handwriting, numbers, or symbols."""
        if not self.is_loaded:
            self.load_model()
        if not self.model or not self.processor:
            return ""

        try:
            rgb_crop = crop.convert("RGB")
            pixel_values = self.processor(rgb_crop, return_tensors="pt").pixel_values.to(self.device)
            if self.device == "cuda":
                pixel_values = pixel_values.half()

            with torch.no_grad():
                generated_ids = self.model.generate(pixel_values, max_new_tokens=48)
            text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            return text.strip()
        except Exception as e:
            logger.warning(f"TrOCR inference error: {e}")
            return ""

    def recognize_crops(self, crops: List[Image.Image]) -> List[str]:
        """Transcribe multiple crops in batches for high throughput."""
        if not crops:
            return []
        if not self.is_loaded:
            self.load_model()
        if not self.model or not self.processor:
            return ["" for _ in crops]

        results = []
        batch_size = 8
        for i in range(0, len(crops), batch_size):
            batch = [c.convert("RGB") for c in crops[i:i + batch_size]]
            try:
                pixel_values = self.processor(batch, return_tensors="pt").pixel_values.to(self.device)
                if self.device == "cuda":
                    pixel_values = pixel_values.half()
                with torch.no_grad():
                    generated_ids = self.model.generate(pixel_values, max_new_tokens=48)
                decoded = self.processor.batch_decode(generated_ids, skip_special_tokens=True)
                results.extend([t.strip() for t in decoded])
            except Exception as e:
                logger.warning(f"TrOCR batch inference error: {e}")
                results.extend(["" for _ in batch])

        return results

    def extract_handwritten_numbers_and_words(self, image: Image.Image) -> List[Dict[str, Any]]:
        """Detect and transcribe handwritten regions and numerical cells on the given page."""
        import pytesseract
        w, h = image.size
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        candidate_crops = []
        boxes_info = []

        for i in range(len(data.get("text", []))):
            txt = data["text"][i].strip()
            conf = int(data["conf"][i]) if str(data["conf"][i]).isdigit() or isinstance(data["conf"][i], (int, float)) else 0
            
            # Identify candidate regions: numbers, decimals, symbols, resistance terms, or low confidence words
            is_numerical_or_symbolic = any(c.isdigit() or c in "¢%¥*@.+-/Ω" for c in txt)
            is_low_conf = len(txt) >= 2 and conf < 70
            is_electrical_term = any(term in txt.lower() for term in ["ohm", "milli", "micro", "volt", "watt", "amp"])

            if is_numerical_or_symbolic or is_low_conf or is_electrical_term:
                left, top, width, height = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                if width > 12 and height > 8:
                    pad = 4
                    x1 = max(0, left - pad)
                    y1 = max(0, top - pad)
                    x2 = min(w, left + width + pad)
                    y2 = min(h, top + height + pad)
                    crop = image.crop((x1, y1, x2, y2))
                    candidate_crops.append(crop)
                    boxes_info.append({
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                        "tesseract_text": txt,
                        "confidence": conf
                    })

        if not candidate_crops:
            return []

        # Run batched TrOCR recognition on candidate crops
        trocr_texts = self.recognize_crops(candidate_crops)
        
        extracted_results = []
        for info, trocr_txt in zip(boxes_info, trocr_texts):
            if trocr_txt:
                extracted_results.append({
                    **info,
                    "trocr_text": trocr_txt
                })

        return extracted_results

    def get_status(self) -> Dict[str, Any]:
        """Return runtime status of the TrOCR engine."""
        return {
            "model_id": self.model_id,
            "device": self.device,
            "is_loaded": self.is_loaded,
        }


# Global singleton instance
trocr_service = TrOCRService()
