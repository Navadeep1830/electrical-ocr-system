# backend/app/electronics.py
"""Electronics and Electrical normalization & error correction module.
Adapted and enhanced from handwritten-tabular-ocr for electrical test reports,
transformers, resistance measurements, voltages, currents, and ratings.
"""
from __future__ import annotations

import re
import logging
from typing import Optional, Tuple
from rapidfuzz import fuzz, process

logger = logging.getLogger("electronics")

MICRO = "µ"
OHM = "Ω"

# Unit canonicalization dictionaries
_PREFIX_MAP = {
    "p": "p", "n": "n", "u": MICRO, MICRO: MICRO, "µ": MICRO,
    "m": "m", "k": "k", "K": "k", "M": "M", "G": "G"
}

_UNIT_MAP = {
    OHM: OHM, "O": OHM, "R": OHM, "Ohm": OHM, "OHM": OHM, "ohm": OHM, "Q": OHM, "q": OHM,
    "F": "F", "H": "H", "V": "V", "A": "A", "W": "W",
    "Hz": "Hz", "HZ": "Hz", "hz": "Hz",
    "kVA": "kVA", "KVA": "kVA", "kva": "kVA", "MVA": "MVA", "mva": "MVA"
}

# OCR confusion map for digits in numerical measurement cells
_DIGIT_OCR_FIX = str.maketrans({
    "O": "0", "o": "0",
    "I": "1", "l": "1", "i": "1", "|": "1",
    "S": "5", "s": "5",
    "Z": "2", "z": "2",
    "B": "8"
})


def repair_numeric_measurement(text: str) -> str:
    """Repair OCR confusion inside numeric measurement entries.
    E.g. '3,9736' -> '3.9736', '4.2O28' -> '4.2028', 'l.689' -> '1.689'
    """
    clean = text.strip()
    if not clean:
        return ""

    # Fix decimal comma (e.g. 3,9736 -> 3.9736)
    clean = re.sub(r'(\d),(\d)', r'\1.\2', clean)

    # Fix OCR letters in primarily numeric tokens (e.g. 3.9O74 -> 3.9074)
    tokens = clean.split()
    fixed_tokens = []
    for token in tokens:
        # Check if token is largely digits with decimal
        digit_count = sum(c.isdigit() for c in token)
        if digit_count >= 2 and any(c in "OolISsZz" for c in token):
            # Translate confused letters to digits if followed or preceded by digits
            fixed = re.sub(r'(?<=\d)[OoSsZzIl](?=\d)', lambda m: m.group(0).translate(_DIGIT_OCR_FIX), token)
            fixed_tokens.append(fixed)
        else:
            fixed_tokens.append(token)

    return " ".join(fixed_tokens)


def normalize_resistance(raw: str) -> str:
    """Normalize resistance values to standard Ohm notation.
    E.g. '3.9736 Ohms' -> '3.9736 Ω', '3.8716 mOhm' -> '3.8716 mΩ', '4R7' -> '4.7 Ω'
    """
    clean = repair_numeric_measurement(raw)
    clean = clean.replace(" ", "")

    # Handle EIA 4R7 format -> 4.7 Ω
    m_eia = re.match(r'^(\d+)R(\d+)$', clean, re.IGNORECASE)
    if m_eia:
        return f"{m_eia.group(1)}.{m_eia.group(2)} {OHM}"

    # Handle milli-Ohms / micro-Ohms
    clean = re.sub(r'(?i)(milli[- ]?ohms?|mohm|mQ)\b', f" m{OHM}", clean)
    clean = re.sub(r'(?i)(micro[- ]?ohms?|uohm|uQ|µohm)\b', f" {MICRO}{OHM}", clean)
    clean = re.sub(r'(?i)(ohms?|Q|O)\b', f" {OHM}", clean)

    return clean.strip()


def normalize_voltage(raw: str) -> str:
    """Normalize voltage strings.
    E.g. '11000/433' -> '11000/433 V', '11/.433 kV' -> '11/0.433 kV', '12kv' -> '12 kV'
    """
    clean = repair_numeric_measurement(raw)
    # Fix .433 -> 0.433
    clean = re.sub(r'(\s*[\/\\]\s*)\.([0-9]+)', r'\g<1>0.\2', clean)
    # Standardize kV / V capitalization
    clean = re.sub(r'(?i)\bkv\b', 'kV', clean)
    clean = re.sub(r'(?i)\bv\b', 'V', clean)
    return clean


def normalize_power_rating(raw: str) -> str:
    """Normalize power rating strings.
    E.g. '250kva' -> '250 kVA', '1.5mva' -> '1.5 MVA'
    """
    clean = repair_numeric_measurement(raw)
    clean = re.sub(r'(?i)\bkva\b', 'kVA', clean)
    clean = re.sub(r'(?i)\bmva\b', 'MVA', clean)
    return clean
