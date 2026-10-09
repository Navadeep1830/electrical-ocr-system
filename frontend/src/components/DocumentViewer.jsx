import React, { useState, useRef, useEffect } from 'react';
import { 
  ZoomIn, ZoomOut, RotateCw, Maximize2, Minimize2, 
  ChevronLeft, ChevronRight, Eye, Contrast, Download, Layers
} from 'lucide-react';

export default function DocumentViewer({ record, activePageIndex = 0, onPageChange }) {
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [contrastMode, setContrastMode] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  const pages = record?.pages || [];
  const currentPage = pages[activePageIndex] || pages[0];

  useEffect(() => {
    // Reset pan and zoom on page change
    setPanOffset({ x: 0, y: 0 });
    setZoom(1);
  }, [activePageIndex]);

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.25, 3.5));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.25, 0.4));
  const handleResetZoom = () => {
    setZoom(1);
    setPanOffset({ x: 0, y: 0 });
    setRotation(0);
  };
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);

  const handleMouseDown = (e) => {
    if (zoom > 1) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging && zoom > 1) {
      setPanOffset({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      if (e.deltaY < 0) {
        handleZoomIn();
      } else {
        handleZoomOut();
      }
    }
  };

  if (!currentPage) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-slate-900 border border-slate-800 rounded-xl p-8 text-slate-400">
        <Layers className="w-12 h-12 mb-3 text-slate-600" />
        <p className="text-base font-medium">No document pages available</p>
        <p className="text-xs text-slate-500 mt-1">Select or upload a request form to inspect</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-900/95 border border-slate-800 rounded-xl overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-800/80 border-b border-slate-700/60 text-xs">
        {/* Page Switcher */}
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-slate-300">Sheet:</span>
          <div className="flex items-center bg-slate-900/90 rounded-lg p-0.5 border border-slate-700">
            <button
              onClick={() => onPageChange && onPageChange(Math.max(0, activePageIndex - 1))}
              disabled={activePageIndex <= 0}
              className="p-1 rounded text-slate-300 hover:text-white disabled:opacity-30 disabled:hover:text-slate-500"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 font-mono text-xs font-semibold text-sky-400">
              {currentPage.page_number} / {pages.length}
            </span>
            <button
              onClick={() => onPageChange && onPageChange(Math.min(pages.length - 1, activePageIndex + 1))}
              disabled={activePageIndex >= pages.length - 1}
              className="p-1 rounded text-slate-300 hover:text-white disabled:opacity-30 disabled:hover:text-slate-500"
              title="Next Page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <span className="hidden sm:inline-block px-2 py-0.5 bg-sky-950/70 text-sky-300 border border-sky-800/50 rounded text-[11px] font-mono">
            300 DPI Scan
          </span>
        </div>

        {/* Zoom & Canvas Controls */}
        <div className="flex items-center space-x-1.5">
          <button
            onClick={handleZoomOut}
            className="p-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white transition"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="w-12 text-center font-mono text-xs font-medium text-slate-300">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={handleZoomIn}
            className="p-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white transition"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={handleResetZoom}
            className="px-2 py-1 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white text-[11px] font-medium transition"
            title="Fit / Reset"
          >
            Reset
          </button>
          <button
            onClick={handleRotate}
            className="p-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white transition"
            title="Rotate 90°"
          >
            <RotateCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setContrastMode(!contrastMode)}
            className={`p-1.5 rounded-lg transition ${
              contrastMode 
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50' 
                : 'bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white'
            }`}
            title="Toggle Forensic High Contrast"
          >
            <Contrast className="w-4 h-4" />
          </button>
          <a
            href={currentPage.image_url}
            download={`sheet_${currentPage.page_number}.png`}
            target="_blank"
            rel="noreferrer"
            className="p-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 hover:text-white transition"
            title="Download Full Resolution"
          >
            <Download className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* Main Canvas Viewport */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className={`flex-1 overflow-auto relative p-4 flex items-center justify-center bg-slate-950 select-none ${
          zoom > 1 ? (isDragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-default'
        }`}
      >
        <div
          style={{
            transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoom}) rotate(${rotation}deg)`,
            transformOrigin: 'center center',
            transition: isDragging ? 'none' : 'transform 0.15s ease-out',
            filter: contrastMode ? 'contrast(1.6) brightness(1.05) grayscale(0.2)' : 'none',
          }}
          className="relative max-w-full shadow-2xl transition-all duration-200 rounded-sm overflow-hidden"
        >
          <img
            src={currentPage.image_url}
            alt={`Page ${currentPage.page_number}`}
            className="max-h-[78vh] w-auto object-contain block pointer-events-none rounded border border-slate-700/50"
            draggable={false}
          />
        </div>
      </div>

      {/* Bottom Thumbnail Strip */}
      {pages.length > 1 && (
        <div className="flex items-center space-x-3 px-4 py-2 bg-slate-900/90 border-t border-slate-800 overflow-x-auto">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider shrink-0">
            Sheets:
          </span>
          {pages.map((p, idx) => (
            <button
              key={p.id || idx}
              onClick={() => onPageChange && onPageChange(idx)}
              className={`flex items-center space-x-2 px-2.5 py-1 rounded-lg text-xs transition shrink-0 ${
                activePageIndex === idx
                  ? 'bg-sky-600 text-white font-medium shadow-md shadow-sky-600/30'
                  : 'bg-slate-800/80 text-slate-400 hover:bg-slate-700/80 hover:text-slate-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>Sheet {p.page_number}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
