# backend/app/table_detection.py
"""OpenCV morphology-based table and cell grid detection for ruled and boxed tables.
Adapted from handwritten-tabular-ocr to detect table grid cells, rows, and columns.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional
import cv2
import numpy as np

logger = logging.getLogger("table_detection")


@dataclass
class BoundingBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def height(self) -> int:
        return max(0, self.y1 - self.y0)


@dataclass
class TableCellBox:
    row: int
    col: int
    bbox: BoundingBox


@dataclass
class DetectedTableGrid:
    region: BoundingBox
    rows: int
    cols: int
    cells: List[TableCellBox]


def binarize_inv(gray: np.ndarray) -> np.ndarray:
    """Otsu inverse binarization: ink pixels white (255), background black (0)."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def extract_line_masks(binary_inv: np.ndarray, h_len: int, v_len: int) -> Tuple[np.ndarray, np.ndarray]:
    """Extract horizontal and vertical line masks using morphological kernels."""
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))

    h_mask = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, h_kernel)
    v_mask = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, v_kernel)
    return h_mask, v_mask


def _cluster(coords: List[int], tolerance: int = 12) -> List[int]:
    """Cluster 1D coordinates within tolerance and return cluster centers."""
    if not coords:
        return []
    coords_sorted = sorted(coords)
    clusters: List[List[int]] = []
    current = [coords_sorted[0]]

    for c in coords_sorted[1:]:
        if c - current[-1] <= tolerance:
            current.append(c)
        else:
            clusters.append(current)
            current = [c]
    if current:
        clusters.append(current)

    return [int(round(sum(grp) / len(grp))) for grp in clusters]


def detect_ruled_tables(
    image: np.ndarray,
    min_table_area: int = 50000,
    line_cluster_tolerance: int = 15,
    min_cell_width: int = 40,
    min_cell_height: int = 20,
    cell_inset: int = 3,
) -> List[DetectedTableGrid]:
    """Detect ruled tables in an image and compute grid cell coordinates."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    binary_inv = binarize_inv(gray)

    h_len = max(40, gray.shape[1] // 30)
    v_len = max(40, gray.shape[0] // 40)
    h_mask, v_mask = extract_line_masks(binary_inv, h_len, v_len)

    combined = cv2.dilate(cv2.bitwise_or(h_mask, v_mask), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tables: List[DetectedTableGrid] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < min_table_area:
            continue

        region = BoundingBox(x0=int(x), y0=int(y), x1=int(x + w), y1=int(y + h))

        # Sample lines within region
        roi_h = h_mask[region.y0:region.y1, region.x0:region.x1]
        roi_v = v_mask[region.y0:region.y1, region.x0:region.x1]

        h_proj = np.sum(roi_h > 0, axis=1)
        v_proj = np.sum(roi_v > 0, axis=0)

        h_indices = np.where(h_proj > (region.width * 0.25))[0] + region.y0
        v_indices = np.where(v_proj > (region.height * 0.25))[0] + region.x0

        row_ys = _cluster(h_indices.tolist(), line_cluster_tolerance)
        col_xs = _cluster(v_indices.tolist(), line_cluster_tolerance)

        if len(row_ys) < 2 or len(col_xs) < 2:
            continue

        cells: List[TableCellBox] = []
        for r_idx in range(len(row_ys) - 1):
            for c_idx in range(len(col_xs) - 1):
                x0 = col_xs[c_idx] + cell_inset
                x1 = col_xs[c_idx + 1] - cell_inset
                y0 = row_ys[r_idx] + cell_inset
                y1 = row_ys[r_idx + 1] - cell_inset

                if (x1 - x0) >= min_cell_width and (y1 - y0) >= min_cell_height:
                    cells.append(
                        TableCellBox(
                            row=r_idx,
                            col=c_idx,
                            bbox=BoundingBox(x0=int(x0), y0=int(y0), x1=int(x1), y1=int(y1))
                        )
                    )

        if len(cells) >= 4:
            tables.append(
                DetectedTableGrid(
                    region=region,
                    rows=len(row_ys) - 1,
                    cols=len(col_xs) - 1,
                    cells=cells,
                )
            )

    return sorted(tables, key=lambda t: t.region.y0)
