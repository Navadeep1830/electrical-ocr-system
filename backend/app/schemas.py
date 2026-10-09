from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ElectricalRatingDisaggregated(BaseModel):
    power_rating_kva: Optional[float] = Field(None, description="Power rating in kVA")
    voltage_hv_kv: Optional[float] = Field(None, description="HV voltage in kV")
    voltage_lv_kv: Optional[float] = Field(None, description="LV voltage in kV")
    phase_count: Optional[int] = Field(None, description="Number of phases, e.g. 3")
    frequency_hz: Optional[float] = Field(None, description="Rated frequency in Hz, e.g. 50.0")
    cooling_type: Optional[str] = Field(None, description="Cooling class, e.g. ONAN")
    vector_group: Optional[str] = Field(None, description="Vector group, e.g. Dyn11")
    winding_material: Optional[str] = Field(None, description="Winding conductor, e.g. Copper / Aluminium")


class FormExtractionData(BaseModel):
    # Header metadata
    format_no: Optional[str] = "CPRI/QAF/01A"
    issue_no: Optional[str] = "02"
    revision_no: Optional[str] = "00"
    date_of_issue: Optional[str] = "22-06-2022"
    division_name: Optional[str] = "SHORT CIRCUIT LABORATORY"

    # Sheet 1: Customer & Equipment Details
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
    conformity_rule: Optional[str] = None

    # Sheet 3: Lab Assessment
    physical_condition_sample: Optional[str] = None
    lab_capability: Optional[str] = None
    external_service_details: Optional[str] = None
    test_engineer_name: Optional[str] = None
    deviations_noticed: Optional[str] = None

    # Raw and disaggregated electrical ratings
    rating_raw: Optional[str] = None
    ratings: Optional[ElectricalRatingDisaggregated] = None

    # Document Classification & Raw Text
    document_type: str = "CUSTOMER_REQUEST_FORM"
    is_valid_crf: bool = True
    validation_message: Optional[str] = None
    raw_extracted_text: Optional[str] = None
    page_texts: Dict[int, str] = Field(default_factory=dict)

    # Field-level extraction confidence (0.0 to 1.0)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)


class FormRecordUpdate(BaseModel):
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

    msme_discount: Optional[str] = None
    conformity_required: Optional[bool] = None
    conformity_rule: Optional[str] = None

    physical_condition_sample: Optional[str] = None
    lab_capability: Optional[str] = None
    external_service_details: Optional[str] = None
    test_engineer_name: Optional[str] = None
    deviations_noticed: Optional[str] = None

    rating_raw: Optional[str] = None
    power_rating_kva: Optional[float] = None
    voltage_hv_kv: Optional[float] = None
    voltage_lv_kv: Optional[float] = None
    phase_count: Optional[int] = None
    frequency_hz: Optional[float] = None
    cooling_type: Optional[str] = None
    vector_group: Optional[str] = None
    winding_material: Optional[str] = None

    status: Optional[str] = None
    verified_by: Optional[str] = None
    verification_notes: Optional[str] = None


class PageResponse(BaseModel):
    id: int
    page_number: int
    image_url: str
    ocr_text: Optional[str] = None
    width: int
    height: int


class FormRecordResponse(BaseModel):
    id: int
    filename: str
    file_path: str
    file_hash: str
    file_size_bytes: int
    page_count: int
    format_no: Optional[str]
    issue_no: Optional[str]
    revision_no: Optional[str]
    date_of_issue: Optional[str]
    division_name: Optional[str]
    customer_name: Optional[str]
    customer_address: Optional[str]
    sample_name: Optional[str]
    sample_description: Optional[str]
    sample_type: Optional[str]
    serial_number: Optional[str]
    manufacturer_details: Optional[str]
    drawing_number: Optional[str]
    customer_requirement: Optional[str]
    evaluation_criteria: Optional[str]
    number_of_samples: Optional[str]
    sample_disposal: Optional[str]
    tests_requested: Optional[str]
    specific_instructions: Optional[str]
    customer_representative: Optional[str]
    witness_other: Optional[str]
    report_dispatch_to: Optional[str]
    report_dispatch_mode: Optional[str]
    additional_reports: Optional[str]
    msme_discount: Optional[str]
    conformity_required: Optional[bool]
    conformity_rule: Optional[str]
    physical_condition_sample: Optional[str]
    lab_capability: Optional[str]
    external_service_details: Optional[str]
    test_engineer_name: Optional[str]
    deviations_noticed: Optional[str]
    rating_raw: Optional[str]
    power_rating_kva: Optional[float]
    voltage_hv_kv: Optional[float]
    voltage_lv_kv: Optional[float]
    phase_count: Optional[int]
    frequency_hz: Optional[float]
    cooling_type: Optional[str]
    vector_group: Optional[str]
    winding_material: Optional[str]
    status: str
    document_type: Optional[str] = "CUSTOMER_REQUEST_FORM"
    is_valid_crf: Optional[bool] = True
    validation_message: Optional[str] = None
    raw_extracted_text: Optional[str] = None
    verified_by: Optional[str]
    verification_timestamp: Optional[str]
    verification_notes: Optional[str]
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    pages: List[PageResponse] = Field(default_factory=list)


class ProcessExistingFileRequest(BaseModel):
    file_path: str
