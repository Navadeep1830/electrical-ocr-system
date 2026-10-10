import os
import re
import json
import shutil
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from sqlmodel import Session, select, func
from PIL import Image

import pypdfium2 as pdfium

from app.config import (
    UPLOAD_DIR, PAGES_DIR, STATIC_DIR, DB_PATH, PDF_RENDER_DPI,
    HOST, PORT, VLM_MODEL_ID, FORCE_LOCAL_OCR
)
from app.database import init_db, get_session
from app.models import FormRecord, FormPage
from app.schemas import (
    FormRecordResponse, FormRecordUpdate, PageResponse,
    ProcessExistingFileRequest, FormExtractionData
)
from app.parser import ElectricalRatingParser
from app.vlm_service import vlm_engine, auto_orient_image
from app.trocr_service import trocr_service
from app.gemini_service import gemini_service

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="PowerNext Electrical OCR & Verification System",
    description="Air-gapped OCR & VLM document processor for CPRI Customer Request Forms (CPRI/QAF/01A)",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads static directory
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.on_event("startup")
def on_startup():
    """Initialize database and trigger model background load."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully.")
    # Check if auto-load is requested
    if os.getenv("VLM_AUTO_LOAD", "false").lower() in ("true", "1"):
        logger.info("Triggering VLM model background loading...")
        vlm_engine.load_model(async_load=True)


def calculate_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def render_pdf_pages(pdf_path: Path, record_prefix: str) -> List[dict]:
    """Render PDF pages at 300 DPI to PNG images using pypdfium2 with pdftoppm fallback."""
    rendered_pages = []
    scale = PDF_RENDER_DPI / 72.0  # 300 DPI

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        page_count = len(pdf)
        for i in range(page_count):
            page_num = i + 1
            out_filename = f"{record_prefix}_page_{page_num}.png"
            out_path = PAGES_DIR / out_filename

            page = pdf[i]
            embedded_text = ""
            try:
                text_page = page.get_textpage()
                embedded_text = text_page.get_text_range()
            except Exception:
                embedded_text = ""

            rendered_image = page.render(scale=scale).to_pil()
            rendered_image = auto_orient_image(rendered_image)
            rendered_image.save(out_path, format="PNG", optimize=True)

            w, h = rendered_image.size
            rendered_pages.append({
                "page_number": page_num,
                "file_path": str(out_path),
                "image_url": f"/uploads/pages/{out_filename}",
                "width": w,
                "height": h,
                "embedded_text": embedded_text,
            })
    except Exception as exc:
        logger.warning(f"pypdfium2 failed: {exc}. Attempting pdftoppm fallback...")
        prefix = str(PAGES_DIR / f"{record_prefix}_fallback")
        import subprocess
        subprocess.run([
            "pdftoppm", "-png", "-r", str(PDF_RENDER_DPI), str(pdf_path), prefix
        ], check=True)

        # Collect generated fallback pages
        import glob
        matches = sorted(glob.glob(f"{prefix}-*.png"))
        for idx, match_path in enumerate(matches):
            page_num = idx + 1
            target_name = f"{record_prefix}_page_{page_num}.png"
            target_path = PAGES_DIR / target_name
            shutil.move(match_path, target_path)

            img = Image.open(target_path)
            w, h = img.size
            rendered_pages.append({
                "page_number": page_num,
                "file_path": str(target_path),
                "image_url": f"/uploads/pages/{target_name}",
                "width": w,
                "height": h,
                "embedded_text": "",
            })

    return rendered_pages


def process_and_save_document(
    file_path: Path,
    original_filename: str,
    session: Session,
    force_reprocess: bool = False
) -> FormRecord:
    """Core pipeline: renders pages, runs VLM/OCR extraction, creates DB record and pages."""
    file_hash = calculate_sha256(file_path)
    file_size = file_path.stat().st_size

    # Check for existing record with same hash
    existing = session.exec(select(FormRecord).where(FormRecord.file_hash == file_hash)).first()
    if existing and not force_reprocess and existing.raw_extracted_text:
        logger.info(f"Duplicate document detected (ID: {existing.id}, hash: {file_hash}). Returning existing record.")
        return existing
    elif existing and (force_reprocess or not existing.raw_extracted_text):
        logger.info(f"Refreshing/reprocessing record ID: {existing.id}")
        session.delete(existing)
        session.commit()

    record_prefix = f"rec_{int(datetime.now().timestamp())}_{file_hash[:8]}"

    # Render pages
    is_pdf = file_path.suffix.lower() == ".pdf"
    if is_pdf:
        rendered_pages = render_pdf_pages(file_path, record_prefix)
    else:
        # Direct image file
        img = auto_orient_image(Image.open(file_path))
        out_filename = f"{record_prefix}_page_1.png"
        out_path = PAGES_DIR / out_filename
        img.save(out_path, format="PNG")
        rendered_pages = [{
            "page_number": 1,
            "file_path": str(out_path),
            "image_url": f"/uploads/pages/{out_filename}",
            "width": img.width,
            "height": img.height,
            "embedded_text": "",
        }]

    # Run VLM / OCR extraction (Gemini 3.8 Flash primary with local Qwen2.5-VL / TrOCR fallback)
    page_img_paths = [p["file_path"] for p in rendered_pages]
    embedded_texts = {p["page_number"]: p.get("embedded_text", "") for p in rendered_pages}

    extraction: Optional[FormExtractionData] = None
    if not FORCE_LOCAL_OCR and gemini_service.is_available():
        try:
            logger.info("Executing Gemini 3.8 Flash high-precision document and table extraction...")
            extraction = gemini_service.extract_document(page_img_paths)
        except Exception as exc:
            logger.warning(f"Gemini service extraction failed: {exc}. Falling back to local VLM engine.")

    if not extraction:
        logger.info("Executing 100% Free & Local GPU Pipeline (Qwen2.5-VL + Ollama Qwen2.5-Coder)...")
        extraction = vlm_engine.extract_document(page_img_paths, embedded_texts=embedded_texts)

    # Disaggregate ratings
    disagg = extraction.ratings or ElectricalRatingParser.parse_ratings(
        f"{extraction.rating_raw or ''} {extraction.sample_description or ''} {extraction.sample_type or ''}"
    )

    # Create Database Record
    record = FormRecord(
        filename=original_filename,
        file_path=str(file_path),
        file_hash=file_hash,
        file_size_bytes=file_size,
        page_count=len(rendered_pages),
        format_no=extraction.format_no or "CPRI/QAF/01A",
        issue_no=extraction.issue_no or "02",
        revision_no=extraction.revision_no or "00",
        date_of_issue=extraction.date_of_issue or "22-06-2022",
        division_name=extraction.division_name or "SHORT CIRCUIT LABORATORY",
        customer_name=extraction.customer_name,
        customer_address=extraction.customer_address,
        sample_name=extraction.sample_name or "Distribution Transformer",
        sample_description=extraction.sample_description,
        sample_type=extraction.sample_type,
        serial_number=extraction.serial_number,
        manufacturer_details=extraction.manufacturer_details,
        drawing_number=extraction.drawing_number,
        customer_requirement=extraction.customer_requirement,
        evaluation_criteria=extraction.evaluation_criteria,
        number_of_samples=extraction.number_of_samples,
        sample_disposal=extraction.sample_disposal,
        tests_requested=extraction.tests_requested,
        specific_instructions=extraction.specific_instructions,
        customer_representative=extraction.customer_representative,
        witness_other=extraction.witness_other,
        report_dispatch_to=extraction.report_dispatch_to,
        report_dispatch_mode=extraction.report_dispatch_mode,
        additional_reports=extraction.additional_reports,
        msme_discount=extraction.msme_discount,
        conformity_required=extraction.conformity_required,
        conformity_rule=extraction.conformity_rule,
        physical_condition_sample=extraction.physical_condition_sample,
        lab_capability=extraction.lab_capability,
        external_service_details=extraction.external_service_details,
        test_engineer_name=extraction.test_engineer_name,
        deviations_noticed=extraction.deviations_noticed,
        rating_raw=extraction.rating_raw,
        power_rating_kva=disagg.power_rating_kva,
        voltage_hv_kv=disagg.voltage_hv_kv,
        voltage_lv_kv=disagg.voltage_lv_kv,
        phase_count=disagg.phase_count,
        frequency_hz=disagg.frequency_hz,
        cooling_type=disagg.cooling_type,
        vector_group=disagg.vector_group,
        winding_material=disagg.winding_material,
        status="PENDING_VERIFICATION",
        document_type=extraction.document_type,
        is_valid_crf=extraction.is_valid_crf,
        validation_message=extraction.validation_message,
        structured_tables=extraction.structured_tables,
        raw_extracted_text=extraction.raw_extracted_text,
        raw_extraction_json=json.dumps(extraction.model_dump(), default=str),
        confidence_scores_json=json.dumps(extraction.confidence_scores),
    )

    session.add(record)
    session.commit()
    session.refresh(record)

    # Add FormPage entities
    for p in rendered_pages:
        page_entity = FormPage(
            record_id=record.id,
            page_number=p["page_number"],
            image_path=p["file_path"],
            ocr_text=extraction.page_texts.get(p["page_number"], ""),
            width=p["width"],
            height=p["height"],
        )
        session.add(page_entity)

    session.commit()
    session.refresh(record)
    return record


def format_record_response(record: FormRecord) -> FormRecordResponse:
    """Format FormRecord into API response model."""
    scores = {}
    if record.confidence_scores_json:
        try:
            scores = json.loads(record.confidence_scores_json)
        except Exception:
            scores = {}

    page_responses = []
    if record.pages:
        for p in sorted(record.pages, key=lambda x: x.page_number):
            filename = Path(p.image_path).name
            page_responses.append(PageResponse(
                id=p.id,
                page_number=p.page_number,
                image_url=f"/uploads/pages/{filename}",
                ocr_text=p.ocr_text,
                width=p.width,
                height=p.height,
            ))

    return FormRecordResponse(
        id=record.id,
        filename=record.filename,
        file_path=record.file_path,
        file_hash=record.file_hash,
        file_size_bytes=record.file_size_bytes,
        page_count=record.page_count,
        format_no=record.format_no,
        issue_no=record.issue_no,
        revision_no=record.revision_no,
        date_of_issue=record.date_of_issue,
        division_name=record.division_name,
        customer_name=record.customer_name,
        customer_address=record.customer_address,
        sample_name=record.sample_name,
        sample_description=record.sample_description,
        sample_type=record.sample_type,
        serial_number=record.serial_number,
        manufacturer_details=record.manufacturer_details,
        drawing_number=record.drawing_number,
        customer_requirement=record.customer_requirement,
        evaluation_criteria=record.evaluation_criteria,
        number_of_samples=record.number_of_samples,
        sample_disposal=record.sample_disposal,
        tests_requested=record.tests_requested,
        specific_instructions=record.specific_instructions,
        customer_representative=record.customer_representative,
        witness_other=record.witness_other,
        report_dispatch_to=record.report_dispatch_to,
        report_dispatch_mode=record.report_dispatch_mode,
        additional_reports=record.additional_reports,
        msme_discount=record.msme_discount,
        conformity_required=record.conformity_required,
        conformity_rule=record.conformity_rule,
        physical_condition_sample=record.physical_condition_sample,
        lab_capability=record.lab_capability,
        external_service_details=record.external_service_details,
        test_engineer_name=record.test_engineer_name,
        deviations_noticed=record.deviations_noticed,
        rating_raw=record.rating_raw,
        power_rating_kva=record.power_rating_kva,
        voltage_hv_kv=record.voltage_hv_kv,
        voltage_lv_kv=record.voltage_lv_kv,
        phase_count=record.phase_count,
        frequency_hz=record.frequency_hz,
        cooling_type=record.cooling_type,
        vector_group=record.vector_group,
        winding_material=record.winding_material,
        status=record.status,
        document_type=record.document_type,
        is_valid_crf=record.is_valid_crf,
        validation_message=record.validation_message,
        structured_tables=record.structured_tables,
        raw_extracted_text=record.raw_extracted_text,
        verified_by=record.verified_by,
        verification_timestamp=record.verification_timestamp,
        verification_notes=record.verification_notes,
        confidence_scores=scores,
        created_at=record.created_at,
        updated_at=record.updated_at,
        pages=page_responses,
    )


# =========================================================================
# API ENDPOINTS
# =========================================================================

@app.get("/api/health")
def get_system_health():
    """Return system readiness, GPU metrics, VLM status, TrOCR status, Gemini status, and database info."""
    vlm_stat = vlm_engine.get_status()
    trocr_stat = trocr_service.get_status()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "path": str(DB_PATH),
            "exists": DB_PATH.exists(),
        },
        "vlm_engine": vlm_stat,
        "trocr_service": trocr_stat,
        "local_mode": FORCE_LOCAL_OCR,
        "gemini_service": {
            "available": gemini_service.is_available() and not FORCE_LOCAL_OCR,
            "model": gemini_service.model
        }
    }


@app.post("/api/vlm/load")
def trigger_vlm_load():
    """Trigger background loading of the local VLM model."""
    vlm_engine.load_model(async_load=True)
    return {"message": "VLM model loading initiated in background", "status": vlm_engine.get_status()}


@app.post("/api/trocr/recognize")
async def recognize_handwriting_crop(file: UploadFile = File(...)):
    """Recognize handwritten numbers, symbols, and words (e.g. Ohms, kVA) from a cropped image."""
    try:
        image = Image.open(file.file).convert("RGB")
        recognized_text = trocr_service.recognize_crop(image)
        return {
            "model": "microsoft/trocr-base-handwritten",
            "recognized_text": recognized_text
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"TrOCR recognition failed: {exc}")


@app.post("/api/trocr/extract-page")
async def extract_handwriting_from_page(file: UploadFile = File(...)):
    """Detect and transcribe all handwritten regions and numerical cells on a page using TrOCR."""
    try:
        image = Image.open(file.file).convert("RGB")
        regions = trocr_service.extract_handwritten_numbers_and_words(image)
        return {
            "model": "microsoft/trocr-base-handwritten",
            "total_regions": len(regions),
            "regions": regions
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Page extraction failed: {exc}")


@app.post("/api/upload", response_model=FormRecordResponse)
async def upload_document(
    file: UploadFile = File(...),
    reprocess: bool = Query(False),
    session: Session = Depends(get_session)
):
    """Upload PDF or image document for OCR scanning, VLM inference, and database ingestion."""
    valid_extensions = (".pdf", ".png", ".jpg", ".jpeg", ".tiff")
    ext = Path(file.filename).suffix.lower()
    if ext not in valid_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Supported formats: {', '.join(valid_extensions)}"
        )

    # Save uploaded file
    timestamp_prefix = int(datetime.now().timestamp())
    safe_name = f"{timestamp_prefix}_{file.filename}"
    saved_path = UPLOAD_DIR / safe_name

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    record = process_and_save_document(saved_path, file.filename, session, force_reprocess=reprocess)
    return format_record_response(record)


@app.post("/api/process-existing", response_model=FormRecordResponse)
def process_existing_file(
    payload: ProcessExistingFileRequest,
    reprocess: bool = Query(False),
    session: Session = Depends(get_session)
):
    """Scan and process an existing local file directly from disk."""
    target_path = Path(payload.file_path)
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found at path: {payload.file_path}"
        )

    # Copy to uploads directory to maintain immutable archive
    safe_name = f"local_{int(datetime.now().timestamp())}_{target_path.name}"
    archived_path = UPLOAD_DIR / safe_name
    shutil.copy2(target_path, archived_path)

    record = process_and_save_document(archived_path, target_path.name, session, force_reprocess=reprocess)
    return format_record_response(record)


@app.get("/api/records", response_model=List[FormRecordResponse])
def list_records(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session)
):
    """List electrical request form records with optional filtering and search."""
    stmt = select(FormRecord).order_by(FormRecord.id.desc())

    if status_filter and status_filter.upper() != "ALL":
        stmt = stmt.where(FormRecord.status == status_filter.upper())

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            (FormRecord.customer_name.like(term)) |
            (FormRecord.serial_number.like(term)) |
            (FormRecord.filename.like(term)) |
            (FormRecord.sample_name.like(term)) |
            (FormRecord.manufacturer_details.like(term))
        )

    stmt = stmt.offset(offset).limit(limit)
    records = session.exec(stmt).all()
    return [format_record_response(r) for r in records]


@app.get("/api/records/{record_id}", response_model=FormRecordResponse)
def get_record(record_id: int, session: Session = Depends(get_session)):
    """Fetch single document record by ID with its rendered page images."""
    record = session.get(FormRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return format_record_response(record)


@app.put("/api/records/{record_id}", response_model=FormRecordResponse)
def update_and_verify_record(
    record_id: int,
    payload: FormRecordUpdate,
    session: Session = Depends(get_session)
):
    """Update and verify extracted form data during interactive staging inspection."""
    record = session.get(FormRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    update_dict = payload.model_dump(exclude_unset=True)

    # If rating_raw was modified and numeric ratings not explicitly provided, re-parse
    if "rating_raw" in update_dict and update_dict["rating_raw"]:
        new_rating_str = update_dict["rating_raw"]
        disagg = ElectricalRatingParser.parse_ratings(new_rating_str)
        if "power_rating_kva" not in update_dict or update_dict["power_rating_kva"] is None:
            update_dict["power_rating_kva"] = disagg.power_rating_kva
        if "voltage_hv_kv" not in update_dict or update_dict["voltage_hv_kv"] is None:
            update_dict["voltage_hv_kv"] = disagg.voltage_hv_kv
        if "voltage_lv_kv" not in update_dict or update_dict["voltage_lv_kv"] is None:
            update_dict["voltage_lv_kv"] = disagg.voltage_lv_kv
        if "phase_count" not in update_dict or update_dict["phase_count"] is None:
            update_dict["phase_count"] = disagg.phase_count
        if "frequency_hz" not in update_dict or update_dict["frequency_hz"] is None:
            update_dict["frequency_hz"] = disagg.frequency_hz
        if "cooling_type" not in update_dict or update_dict["cooling_type"] is None:
            update_dict["cooling_type"] = disagg.cooling_type
        if "vector_group" not in update_dict or update_dict["vector_group"] is None:
            update_dict["vector_group"] = disagg.vector_group
        if "winding_material" not in update_dict or update_dict["winding_material"] is None:
            update_dict["winding_material"] = disagg.winding_material

    # Apply updates
    for field, val in update_dict.items():
        setattr(record, field, val)

    record.updated_at = datetime.now(timezone.utc).isoformat()
    if record.status in ("VERIFIED", "REJECTED") and not record.verification_timestamp:
        record.verification_timestamp = datetime.now(timezone.utc).isoformat()

    session.add(record)
    session.commit()
    session.refresh(record)
    return format_record_response(record)


@app.delete("/api/records/clear/all")
def clear_all_records(session: Session = Depends(get_session)):
    """Clear all records from database and purge uploaded page cache."""
    from sqlmodel import delete
    session.exec(delete(FormPage))
    session.exec(delete(FormRecord))
    session.commit()
    for f in PAGES_DIR.glob("*.*"):
        try:
            f.unlink()
        except Exception:
            pass
    return {"message": "All records and cache files successfully cleared"}


@app.delete("/api/records/{record_id}")
def delete_record(record_id: int, session: Session = Depends(get_session)):
    """Delete a record and its corresponding database entries."""
    record = session.get(FormRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    session.delete(record)
    session.commit()
    return {"message": f"Record {record_id} successfully deleted"}


@app.get("/api/records/{record_id}/export")
def export_record_data(record_id: int, format: str = Query("json"), session: Session = Depends(get_session)):
    """Export verified record as structured JSON or CSV."""
    record = session.get(FormRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    resp_data = format_record_response(record).model_dump()

    if format.lower() == "csv":
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        for k, v in resp_data.items():
            if k not in ("pages", "confidence_scores"):
                writer.writerow([k, str(v) if v is not None else ""])
        output.seek(0)
        from fastapi.responses import Response
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=cpri_record_{record_id}.csv"}
        )

    return resp_data


@app.post("/api/batch-scan")
def batch_scan_folder(folder_path: str = Query(...), session: Session = Depends(get_session)):
    """Scan a directory for PDF test request forms and process each into the database."""
    target_dir = Path(folder_path)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory '{folder_path}' does not exist")

    pdf_files = list(target_dir.glob("*.pdf")) + list(target_dir.glob("*.PDF"))
    processed = []
    errors = []

    for pdf in pdf_files:
        try:
            safe_name = f"scan_{int(datetime.now().timestamp())}_{pdf.name}"
            archived = UPLOAD_DIR / safe_name
            shutil.copy2(pdf, archived)
            record = process_and_save_document(archived, pdf.name, session)
            processed.append({"id": record.id, "filename": record.filename, "status": record.status})
        except Exception as err:
            logger.error(f"Error processing {pdf.name}: {err}")
            errors.append({"filename": pdf.name, "error": str(err)})

    return {
        "folder": folder_path,
        "total_found": len(pdf_files),
        "processed_count": len(processed),
        "processed": processed,
        "errors": errors,
    }


# Route aliases for alternative client compatibility
@app.post("/api/documents/upload", response_model=FormRecordResponse)
async def upload_document_alias(
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    return await upload_document(file, session)


@app.get("/api/documents", response_model=List[FormRecordResponse])
def list_documents_alias(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session)
):
    return list_records(status_filter, search, limit, offset, session)


@app.get("/api/documents/{document_id}", response_model=FormRecordResponse)
def get_document_alias(document_id: int, session: Session = Depends(get_session)):
    return get_record(document_id, session)


@app.post("/api/documents/{document_id}/verify", response_model=FormRecordResponse)
@app.put("/api/documents/{document_id}/verify", response_model=FormRecordResponse)
def verify_document_alias(
    document_id: int,
    payload: FormRecordUpdate,
    session: Session = Depends(get_session)
):
    return update_and_verify_record(document_id, payload, session)


# Mount built frontend if available
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")

