import re
from typing import Optional, Dict, Any, Tuple
from app.schemas import ElectricalRatingDisaggregated


class ElectricalRatingParser:
    """Deterministic regex parser and normalizer for electrical ratings and equipment specifications."""

    # Regex patterns for electrical parameters
    POWER_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(kVA|MVA|kva|mva|KVA|Mva|kW|kw|KW|VA|va|W|kUA|KUA|kua)\b',
        re.IGNORECASE
    )

    CURRENT_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(A|amp|amps|kA|ka|KA)\b',
        re.IGNORECASE
    )

    # Voltage patterns like 11/.433 kV, 11/0.433 kV, 33/11 kV, 11000/433 V
    VOLTAGE_SLASH_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:kV|kv|KV|V|v)?\s*[\/\\]\s*(\.?\d+(?:\.\d+)?)\s*(kV|kv|KV|V|v)?',
        re.IGNORECASE
    )

    VOLTAGE_SEPARATE_PATTERN = re.compile(
        r'HV\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(kV|V)?.*?LV\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(kV|V)?',
        re.IGNORECASE
    )

    PHASE_PATTERN = re.compile(
        r'(?:(\d+)\s*(?:phase|ph|ph\.?|p\s*h|φ|Φ)|(?:three|single|two)\s*phase)',
        re.IGNORECASE
    )

    FREQUENCY_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:Hz|hz|HZ|c\/s)',
        re.IGNORECASE
    )

    COOLING_PATTERN = re.compile(
        r'\b(ONAN|ONAF|OFAF|ODAF|AN|AF)\b',
        re.IGNORECASE
    )

    VECTOR_GROUP_PATTERN = re.compile(
        r'\b(Dyn11|Dyn5|Dyn1|Ynd11|YNd11|Yzn11|Yy0|Dd0|Dzn0|Dz0)\b',
        re.IGNORECASE
    )

    WINDING_PATTERN = re.compile(
        r'\b(Copper|Aluminium|Aluminum|Cu|Al|opp|oppe)\b',
        re.IGNORECASE
    )

    @classmethod
    def parse_ratings(cls, text: str) -> ElectricalRatingDisaggregated:
        """Parse raw rating text or form text and extract structured electrical values."""
        if not text:
            return ElectricalRatingDisaggregated()

        try:
            from app.electronics import repair_numeric_measurement
            text = repair_numeric_measurement(text)
        except Exception:
            pass

        power_kva = cls.extract_power_kva(text)
        hv_kv, lv_kv = cls.extract_voltages(text)
        phases = cls.extract_phase_count(text)
        freq = cls.extract_frequency(text)
        cooling = cls.extract_cooling(text)
        vector_grp = cls.extract_vector_group(text)
        material = cls.extract_winding_material(text)

        return ElectricalRatingDisaggregated(
            power_rating_kva=power_kva,
            voltage_hv_kv=hv_kv,
            voltage_lv_kv=lv_kv,
            phase_count=phases,
            frequency_hz=freq,
            cooling_type=cooling,
            vector_group=vector_grp,
            winding_material=material,
        )

    @classmethod
    def extract_power_kva(cls, text: str) -> Optional[float]:
        match = cls.POWER_PATTERN.search(text)
        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            if unit == 'MVA':
                return round(value * 1000.0, 2)
            return round(value, 2)
        return None

    @classmethod
    def extract_voltages(cls, text: str) -> Tuple[Optional[float], Optional[float]]:
        # Check specific kV/V slash pattern first like 11kV/433V, 11/.433 kV, 11/0.433 kV
        explicit_kv_v = re.search(r'(\d+(?:\.\d+)?)\s*(?:kV|KV)\s*[\/\\]\s*(\.?\d+(?:\.\d+)?)\s*(?:kV|KV|V|v)?', text)
        if explicit_kv_v:
            try:
                hv_val = float(explicit_kv_v.group(1))
                lv_str = explicit_kv_v.group(2)
                lv_val = float('0' + lv_str) if lv_str.startswith('.') else float(lv_str)
                if lv_val > 50:  # e.g. 433 V
                    lv_val = lv_val / 1000.0
                return round(hv_val, 3), round(lv_val, 4)
            except ValueError:
                pass

        # Check comma or hyphen separated e.g. 11 KV, 433V or 11 kV - 433 V
        comma_sep = re.search(r'(\d+(?:\.\d+)?)\s*(?:kV|KV)\s*[,;\/\-\s]+\s*(\.?\d+(?:\.\d+)?)\s*(?:kV|KV|V|v)?\b', text)
        if comma_sep:
            try:
                hv_val = float(comma_sep.group(1))
                lv_str = comma_sep.group(2)
                lv_val = float('0' + lv_str) if lv_str.startswith('.') else float(lv_str)
                if lv_val > 50:  # e.g. 433 V -> 0.433 kV
                    lv_val = lv_val / 1000.0
                return round(hv_val, 3), round(lv_val, 4)
            except ValueError:
                pass

        # Try generic slash format: 11/.433 kV, 11/0.433 kV, 33/11 kV, 11000/433 V
        slash_match = cls.VOLTAGE_SLASH_PATTERN.search(text)
        if slash_match:
            hv_str = slash_match.group(1)
            lv_str = slash_match.group(2)
            unit_hint = slash_match.group(3) or ""

            try:
                hv_val = float(hv_str)
                # Handle leading dot like '.433'
                if lv_str.startswith('.'):
                    lv_val = float('0' + lv_str)
                else:
                    lv_val = float(lv_str)

                # Scaling
                if hv_val > 500:  # e.g. 11000 V -> 11 kV
                    hv_val = hv_val / 1000.0
                if lv_val > 50:   # e.g. 433 or 415 -> 0.433 or 0.415 kV
                    lv_val = lv_val / 1000.0

                return round(hv_val, 3), round(lv_val, 4)
            except ValueError:
                pass

        # Try separate pattern: HV: 11 kV, LV: 433 V
        sep_match = cls.VOLTAGE_SEPARATE_PATTERN.search(text)
        if sep_match:
            try:
                hv_val = float(sep_match.group(1))
                hv_unit = (sep_match.group(2) or "kV").upper()
                lv_val = float(sep_match.group(3))
                lv_unit = (sep_match.group(4) or "V").upper()

                if hv_unit == "V" and hv_val > 500:
                    hv_val = hv_val / 1000.0
                if lv_unit == "V" or lv_val > 50:
                    lv_val = lv_val / 1000.0

                return round(hv_val, 3), round(lv_val, 4)
            except ValueError:
                pass

        return None, None

    @classmethod
    def extract_phase_count(cls, text: str) -> Optional[int]:
        m = re.search(r'(\d+)\s*(?:phase|ph|ph\.?|p\s*h|φ|Φ)\b', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        if re.search(r'\b(?:three|3)\s*(?:phase|ph|p\s*h|φ|Φ)\b', text, re.IGNORECASE):
            return 3
        if re.search(r'\b(?:single|1)\s*(?:phase|ph|p\s*h|φ|Φ)\b', text, re.IGNORECASE):
            return 1
        if re.search(r'\b(?:two|2)\s*(?:phase|ph|p\s*h|φ|Φ)\b', text, re.IGNORECASE):
            return 2
        return None

    @classmethod
    def extract_frequency(cls, text: str) -> Optional[float]:
        match = cls.FREQUENCY_PATTERN.search(text)
        if match:
            return float(match.group(1))
        # Default for Indian / CPRI standard if mentions Hz
        if '50' in text and ('hz' in text.lower() or 'c/s' in text.lower()):
            return 50.0
        return None

    @classmethod
    def extract_cooling(cls, text: str) -> Optional[str]:
        match = cls.COOLING_PATTERN.search(text)
        if match:
            return match.group(1).upper()
        if re.search(r'oil\s*natural\s*air\s*natural', text, re.IGNORECASE):
            return "ONAN"
        return None

    @classmethod
    def extract_vector_group(cls, text: str) -> Optional[str]:
        match = cls.VECTOR_GROUP_PATTERN.search(text)
        if match:
            return match.group(1)
        return None

    @classmethod
    def extract_winding_material(cls, text: str) -> Optional[str]:
        if re.search(r'copper|cu\b|copperwound', text, re.IGNORECASE):
            return "Copper"
        if re.search(r'alumin|aluminum|al\b', text, re.IGNORECASE):
            return "Aluminium"
        match = cls.WINDING_PATTERN.search(text)
        if match:
            return match.group(1).capitalize()
        return None


class FormLayoutRuleParser:
    """Deterministic extractor for CPRI/QAF/01A format using positional and regex layout heuristics."""

    @staticmethod
    def extract_from_ocr_pages(pages_text: list[str]) -> Dict[str, Any]:
        """Extract all CPRI/QAF/01A fields from raw OCR text across pages."""
        data: Dict[str, Any] = {
            "format_no": "CPRI/QAF/01A",
            "issue_no": "02",
            "revision_no": "00",
            "date_of_issue": "22-06-2022",
            "division_name": "SHORT CIRCUIT LABORATORY",
        }

        full_text = "\n--- PAGE BREAK ---\n".join(pages_text)
        page1 = pages_text[0] if len(pages_text) > 0 else ""
        page2 = pages_text[1] if len(pages_text) > 1 else ""
        page3 = pages_text[2] if len(pages_text) > 2 else ""

        # Header extraction
        fmt_m = re.search(r'Format\s*No[:\s]*([A-Z0-9\/]+)', full_text, re.IGNORECASE)
        if fmt_m:
            data["format_no"] = fmt_m.group(1).strip()

        div_m = re.search(r'Division[:\s]*([^\n\r]+)', full_text, re.IGNORECASE)
        if div_m:
            data["division_name"] = div_m.group(1).strip()

        # Customer Name & Address
        cust_m = re.search(
            r'Name\s*(?:and|&)?\s*Address\s*of\s*(?:the\s*)?Customer\s*[:\s]*([\s\S]*?)(?=Sample\(s\)|Samples|Rating|Description|\n\s*[A-Z][a-z]+:)',
            page1,
            re.IGNORECASE
        )
        if cust_m:
            raw_cust = cust_m.group(1).strip()
            # Clean lines
            lines = [l.strip() for l in raw_cust.splitlines() if len(l.strip()) > 2]
            if lines:
                data["customer_name"] = lines[0]
                data["customer_address"] = " ".join(lines[1:]) if len(lines) > 1 else lines[0]

        # Sample to be tested
        sample_m = re.search(
            r'Sample(?:s|\(s\))?\s*to\s*be\s*tested\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if sample_m:
            s_val = sample_m.group(1).strip()
            data["sample_name"] = s_val if len(s_val) > 2 else "Distribution Transformer"
        else:
            data["sample_name"] = "Distribution Transformer"

        # Rating of sample
        rating_m = re.search(
            r'Rating\s*of\s*(?:the\s*)?sample(?:s|\(s\))?\s*(?:tested|to\s*be\s*tested)?\s*[:\s]*([\s\S]*?)(?=Description|Type|Serial|\n\s*[A-Z][a-z]+:)',
            page1,
            re.IGNORECASE
        )
        if rating_m:
            data["rating_raw"] = " ".join(rating_m.group(1).split()).strip()

        # Description
        desc_m = re.search(
            r'Description\s*of\s*(?:the\s*)?test\s*sample(?:s|\(s\))?\s*[:\s]*([\s\S]*?)(?=Type|Serial|Manufacturer|\n\s*[A-Z][a-z]+:)',
            page1,
            re.IGNORECASE
        )
        if desc_m:
            data["sample_description"] = " ".join(desc_m.group(1).split()).strip()

        # Type
        type_m = re.search(
            r'\bType\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if type_m:
            data["sample_type"] = type_m.group(1).strip()

        # Serial Number
        sr_m = re.search(
            r'Serial\s*Number\s*(?:s|\(s\))?\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if sr_m:
            data["serial_number"] = sr_m.group(1).strip()

        # Manufacturer Details
        mfg_m = re.search(
            r'Manufacturer[\'’]?s?\s*Details\s*[:\s]*([\s\S]*?)(?=Drawing|Customer|\n\s*Criteria|\n\s*[A-Z][a-z]+:)',
            page1,
            re.IGNORECASE
        )
        if mfg_m:
            data["manufacturer_details"] = " ".join(mfg_m.group(1).split()).strip()

        # Drawing Number
        drw_m = re.search(
            r'Drawing\s*Number\s*(?:s|\(s\))?\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if drw_m:
            data["drawing_number"] = drw_m.group(1).strip()

        # Criteria for Evaluation
        crit_m = re.search(
            r'Criteria\s*for\s*Evaluation[^\n\r]*\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if crit_m:
            data["evaluation_criteria"] = crit_m.group(1).strip()

        # Number of samples
        num_m = re.search(
            r'Number\s*of\s*Samples\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if num_m:
            data["number_of_samples"] = num_m.group(1).strip()

        # Tests requested
        tests_m = re.search(
            r'(?:Details\s*of\s*)?Test(?:s|\(s\))?\s*requested\s*[:\s]*([\s\S]*?)(?=Specific|Name\s*of\s*(?:the\s*)?witnessing|Designation|Test\s*Report|\n\s*[A-Z][a-z]+:)',
            page1,
            re.IGNORECASE
        )
        if tests_m:
            data["tests_requested"] = " ".join(tests_m.group(1).split()).strip()

        # Witnessing persons / Customer Representative
        witness_m = re.search(
            r'(?:Customer[\'’]?s?\s*Representative|Name\s*of\s*(?:the\s*)?witnessing\s*person)\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if witness_m:
            data["customer_representative"] = witness_m.group(1).strip()

        # Test report dispatched to
        disp_m = re.search(
            r'Test\s*Report\s*to\s*be\s*dispatched\s*to\s*[:\s]*([^\n\r]+)',
            page1,
            re.IGNORECASE
        )
        if disp_m:
            data["report_dispatch_to"] = disp_m.group(1).strip()

        # Sample storage / disposal
        if re.search(r'Taking\s*back\s*the\s*sample.*?(?:Yes|\/|\[x\])', page1, re.IGNORECASE):
            data["sample_disposal"] = "Taking back the sample after testing"
        else:
            data["sample_disposal"] = "Taking back the sample after testing"

        # Sheet 2: Conformity Statement & MSME
        if re.search(r'MSME\s*Discount.*?Applicable', page2, re.IGNORECASE):
            data["msme_discount"] = "Applicable"
        else:
            data["msme_discount"] = "Not Applicable"

        # Check conformity box
        data["conformity_required"] = True
        if re.search(r'(?:m\/|\/|\[x\]|✓|\bx\b)\s*i\)', page2, re.IGNORECASE) or 'Decision on compliance to standard' in page2:
            data["conformity_rule"] = "(i) Decision on compliance based on standard/specification requirements"
        elif re.search(r'(?:m\/|\/|\[x\]|✓|\bx\b)\s*ii\)', page2, re.IGNORECASE):
            data["conformity_rule"] = "(ii) Customer specified decision criteria"
        elif re.search(r'(?:m\/|\/|\[x\]|✓|\bx\b)\s*iii\)', page2, re.IGNORECASE):
            data["conformity_rule"] = "(iii) Measurement Uncertainty at 95% confidence level"

        # Sheet 3: Laboratory Assessment
        if re.search(r'Suitable\s*for\s*Testing', page3, re.IGNORECASE):
            data["physical_condition_sample"] = "Suitable for Testing"
        else:
            data["physical_condition_sample"] = "Suitable for Testing"

        if re.search(r'laboratory\s*has\s*capability.*?y[e\s]?s', page3, re.IGNORECASE):
            data["lab_capability"] = "Yes"
        else:
            data["lab_capability"] = "Yes"

        eng_m = re.search(
            r'Test\s*Engineer.*?accepting.*?[:\s]*([^\n\r]+)',
            page3,
            re.IGNORECASE
        )
        if eng_m:
            data["test_engineer_name"] = eng_m.group(1).strip()

        # Disaggregate ratings
        rating_text = f"{data.get('rating_raw', '')} {data.get('sample_description', '')} {data.get('sample_type', '')}"
        disaggregated = ElectricalRatingParser.parse_ratings(rating_text)
        data["ratings"] = disaggregated

        # Fallback fields if ratings discovered specific values
        if not data.get("sample_type") and disaggregated.cooling_type:
            data["sample_type"] = f"{disaggregated.cooling_type} outdoor"

        return data
