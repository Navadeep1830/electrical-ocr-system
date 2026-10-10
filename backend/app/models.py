from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class FormPage(SQLModel, table=True):
    __tablename__ = "form_pages"

    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="form_records.id", index=True)
    page_number: int
    image_path: str
    ocr_text: Optional[str] = None
    width: int = 0
    height: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    record: Optional["FormRecord"] = Relationship(back_populates="pages")


class FormRecord(SQLModel, table=True):
    __tablename__ = "form_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    file_path: str
    file_hash: str = Field(index=True)
    file_size_bytes: int = 0
    page_count: int = 0

    # Header / Meta
    format_no: Optional[str] = "CPRI/QAF/01A"
    issue_no: Optional[str] = "02"
    revision_no: Optional[str] = "00"
    date_of_issue: Optional[str] = "22-06-2022"
    division_name: Optional[str] = "SHORT CIRCUIT LABORATORY"

    # Customer & Sample Information (Sheet 1)
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    sample_name: Optional[str] = None
    sample_description: Optional[str] = None
    sample_type: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer_details: Optional[str] = None
    drawing_number: Optional[str] = None
    customer_requirement: Optional[str] = None
    evaluation_criteria: Optional[str] = None
    number_of_samples: Optional[str] = None
    sample_disposal: Optional[str] = None
    tests_requested: Optional[str] = None
    specific_instructions: Optional[str] = None
    customer_representative: Optional[str] = None
    witness_other: Optional[str] = None
    report_dispatch_to: Optional[str] = None
    report_dispatch_mode: Optional[str] = None
    additional_reports: Optional[str] = None

    # Sheet 2: Conformity & MSME
    msme_discount: Optional[str] = None
    conformity_required: Optional[bool] = None
    conformity_rule: Optional[str] = None  # (i), (ii), or (iii)

    # Sheet 3: Laboratory Assessment
    physical_condition_sample: Optional[str] = None
    lab_capability: Optional[str] = None
    external_service_details: Optional[str] = None
    test_engineer_name: Optional[str] = None
    deviations_noticed: Optional[str] = None

    # Disaggregated Electrical Ratings
    rating_raw: Optional[str] = None
    power_rating_kva: Optional[float] = None
    voltage_hv_kv: Optional[float] = None
    voltage_lv_kv: Optional[float] = None
    phase_count: Optional[int] = None
    frequency_hz: Optional[float] = None
    cooling_type: Optional[str] = None
    vector_group: Optional[str] = None
    winding_material: Optional[str] = None

    # Verification Workflow
    # Statuses: PENDING_VERIFICATION, VERIFIED, REJECTED
    status: str = Field(default="PENDING_VERIFICATION", index=True)
    verified_by: Optional[str] = None
    verification_timestamp: Optional[str] = None
    verification_notes: Optional[str] = None

    # Document Classification & Validation
    document_type: str = Field(default="CUSTOMER_REQUEST_FORM", index=True)
    is_valid_crf: bool = Field(default=True)
    validation_message: Optional[str] = None
    structured_tables: Optional[str] = None
    raw_extracted_text: Optional[str] = None

    # Extraction Payloads (JSON strings)
    raw_extraction_json: Optional[str] = None
    confidence_scores_json: Optional[str] = None

    # Audit Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    pages: List[FormPage] = Relationship(back_populates="record", cascade_delete=True)
