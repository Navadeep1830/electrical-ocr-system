import React, { useState, useEffect } from 'react';
import { 
  CheckCircle, AlertCircle, Save, Download, FileText, Zap, 
  RefreshCw, Check, X, Building, ShieldCheck, Cpu, SlidersHorizontal,
  AlertTriangle, Copy, CheckCheck
} from 'lucide-react';
import { updateRecord, exportRecord } from '../api';

function ConfidenceBadge({ score }) {
  if (score === undefined || score === null) return null;
  const pct = Math.round(score * 100);

  let colorClass = 'bg-emerald-950/70 text-emerald-400 border-emerald-800/60';
  let label = 'High';

  if (score < 0.65) {
    colorClass = 'bg-rose-950/70 text-rose-400 border-rose-800/60';
    label = 'Low';
  } else if (score < 0.85) {
    colorClass = 'bg-amber-950/70 text-amber-400 border-amber-800/60';
    label = 'Med';
  }

  return (
    <span 
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border ${colorClass} ml-2`}
      title={`VLM/OCR Confidence: ${pct}%`}
    >
      {pct}% {label}
    </span>
  );
}

function MarkdownTableRenderer({ markdown }) {
  if (!markdown) return null;
  const lines = markdown.split('\n');
  const elements = [];
  let inTable = false;
  let tableHeader = [];
  let tableRows = [];

  const flushTable = (key) => {
    if (tableHeader.length > 0) {
      elements.push(
        <div key={`tbl-${key}`} className="overflow-x-auto my-3 border border-slate-700/80 rounded-xl bg-slate-950/70 shadow-md">
          <table className="w-full text-left text-xs text-slate-200 border-collapse">
            <thead>
              <tr className="bg-slate-800/90 text-sky-300 font-semibold border-b border-slate-700">
                {tableHeader.map((h, i) => (
                  <th key={i} className="px-3 py-2 border-r border-slate-700/60 last:border-r-0 whitespace-nowrap">
                    {h.trim()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {tableRows.map((r, ri) => (
                <tr key={ri} className="hover:bg-slate-800/40 font-mono text-[11px] transition">
                  {r.map((c, ci) => (
                    <td key={ci} className="px-3 py-1.5 border-r border-slate-800/60 last:border-r-0 text-slate-300 whitespace-nowrap">
                      {c.trim()}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeader = [];
      tableRows = [];
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.slice(1, -1).split('|');
      if (cells.every((c) => c.trim().match(/^:?-+:?$/))) {
        // separator line
      } else if (!inTable) {
        inTable = true;
        tableHeader = cells;
      } else {
        tableRows.push(cells);
      }
    } else {
      if (inTable) {
        flushTable(idx);
        inTable = false;
      }
      if (trimmed.startsWith('### ')) {
        elements.push(<h4 key={idx} className="text-sm font-bold text-sky-400 mt-4 mb-2 flex items-center gap-1.5">{trimmed.slice(4)}</h4>);
      } else if (trimmed.startsWith('## ')) {
        elements.push(<h3 key={idx} className="text-base font-bold text-sky-300 mt-5 mb-2">{trimmed.slice(3)}</h3>);
      } else if (trimmed.startsWith('- ')) {
        elements.push(<li key={idx} className="text-xs text-slate-300 ml-4 list-disc">{trimmed.slice(2)}</li>);
      } else if (trimmed) {
        elements.push(<p key={idx} className="text-xs text-slate-300 my-1">{trimmed}</p>);
      }
    }
  });

  if (inTable) {
    flushTable('last');
  }

  return <div className="space-y-1">{elements}</div>;
}

export default function FormEditor({ record, onRecordUpdated }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [activeTab, setActiveTab] = useState('raw_text');
  const [copiedText, setCopiedText] = useState(false);
  const [copiedTable, setCopiedTable] = useState(false);
  const [selectedPageForText, setSelectedPageForText] = useState('all');

  useEffect(() => {
    if (record) {
      setFormData({
        ...record,
        verified_by: record.verified_by || 'Quality Test Engineer',
        verification_notes: record.verification_notes || '',
      });
      setSuccessMessage('');
      setErrorMessage('');
      if (record.structured_tables) {
        setActiveTab('tables');
      } else if (record.is_valid_crf === false) {
        setActiveTab('raw_text');
      }
    }
  }, [record]);

  if (!record) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-slate-900 border border-slate-800 rounded-xl p-8 text-slate-400">
        <FileText className="w-12 h-12 mb-3 text-slate-600" />
        <p className="text-base font-medium">No record selected</p>
        <p className="text-xs text-slate-500 mt-1">Select a request form from the records table to review</p>
      </div>
    );
  }

  const confidence = record.confidence_scores || {};

  const handleInputChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (overrideStatus) => {
    try {
      setSaving(true);
      setSuccessMessage('');
      setErrorMessage('');

      const payload = { ...formData };
      if (overrideStatus) {
        payload.status = overrideStatus;
      }

      const updated = await updateRecord(record.id, payload);
      setFormData(updated);
      setSuccessMessage(`Record successfully ${payload.status === 'VERIFIED' ? 'verified & approved' : 'saved'}!`);
      if (onRecordUpdated) onRecordUpdated(updated);
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async (format) => {
    try {
      if (format === 'csv') {
        const blobData = await exportRecord(record.id, 'csv');
        const url = window.URL.createObjectURL(new Blob([blobData]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `CPRI_${record.id}_${record.serial_number || 'record'}.csv`);
        document.body.appendChild(link);
        link.click();
        link.parentNode.removeChild(link);
      } else {
        const jsonData = await exportRecord(record.id, 'json');
        const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `CPRI_${record.id}_${record.serial_number || 'record'}.json`;
        document.body.appendChild(link);
        link.click();
        link.parentNode.removeChild(link);
      }
    } catch (err) {
      setErrorMessage('Export failed: ' + (err.message || 'unknown error'));
    }
  };

  const currentDisplayedText = React.useMemo(() => {
    if (selectedPageForText === 'all') {
      return formData.raw_extracted_text || '';
    }
    const page = record.pages?.find((p) => p.page_number === selectedPageForText);
    return page?.ocr_text || `(No text recorded for Sheet ${selectedPageForText})`;
  }, [selectedPageForText, formData.raw_extracted_text, record.pages]);

  const handleCopyText = () => {
    if (!currentDisplayedText) return;
    navigator.clipboard.writeText(currentDisplayedText);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const handleDownloadText = () => {
    if (!currentDisplayedText) return;
    const blob = new Blob([currentDisplayedText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const baseName = (formData.filename || 'extracted_text').replace(/\.[^/.]+$/, '');
    link.download = `${baseName}_extracted_text.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleCopyTable = () => {
    if (!formData.structured_tables) return;
    navigator.clipboard.writeText(formData.structured_tables);
    setCopiedTable(true);
    setTimeout(() => setCopiedTable(false), 2000);
  };

  const handleDownloadTable = () => {
    if (!formData.structured_tables) return;
    const blob = new Blob([formData.structured_tables], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const baseName = (formData.filename || 'measurement_tables').replace(/\.[^/.]+$/, '');
    link.download = `${baseName}_tables.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/95 border border-slate-800 rounded-xl overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between px-5 py-3 bg-slate-800/80 border-b border-slate-700/60">
        <div>
          <div className="flex items-center space-x-2.5">
            <h2 className="font-semibold text-slate-100 text-sm tracking-wide">
              {formData.filename || 'Request Form'}
            </h2>
            <span
              className={`px-2 py-0.5 rounded-full text-[11px] font-semibold tracking-wide border ${
                formData.status === 'VERIFIED'
                  ? 'bg-emerald-950/70 text-emerald-400 border-emerald-700/60'
                  : formData.status === 'REJECTED'
                  ? 'bg-rose-950/70 text-rose-400 border-rose-700/60'
                  : 'bg-amber-950/70 text-amber-300 border-amber-700/60'
              }`}
            >
              {formData.status?.replace('_', ' ') || 'PENDING'}
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5 font-mono">
            Format: {formData.format_no || 'CPRI/QAF/01A'} • Div: {formData.division_name || 'SHORT CIRCUIT'}
          </p>
        </div>

        {/* Quick Export Actions */}
        <div className="flex items-center space-x-2 mt-2 sm:mt-0">
          <button
            onClick={() => handleExport('json')}
            className="flex items-center space-x-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-medium text-slate-300 hover:text-white transition"
            title="Export JSON payload"
          >
            <Download className="w-3.5 h-3.5 text-sky-400" />
            <span>JSON</span>
          </button>
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center space-x-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-medium text-slate-300 hover:text-white transition"
            title="Export CSV audit sheet"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* CRF Validation Status Banner */}
      {formData.is_valid_crf === false ? (
        <div className="mx-4 mt-3 p-3 bg-amber-950/60 border border-amber-600/60 rounded-xl text-amber-200 shadow-md">
          <div className="flex items-start space-x-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-xs text-amber-300">Non-CRF Document Detected</span>
                <span className="text-[10px] bg-amber-900/80 px-2 py-0.5 rounded text-amber-200 font-mono border border-amber-700/60">
                  {formData.document_type || 'NON_CRF'}
                </span>
              </div>
              <p className="text-[11px] text-amber-200/90 mt-1">
                {formData.validation_message || 'This document is not a standard CPRI Customer Request Form (CPRI/QAF/01A). Structured electrical fields are not required.'}
              </p>
              <p className="text-[11px] text-amber-300 font-medium mt-1">
                Complete raw text was successfully extracted and is displayed in the <strong>Extracted Text</strong> tab below.
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="mx-4 mt-2.5 px-3 py-1.5 bg-emerald-950/40 border border-emerald-700/50 rounded-lg text-emerald-300 text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-[11px] font-medium">Valid CPRI Customer Request Form (CPRI/QAF/01A)</span>
          </div>
          <span className="text-[10px] bg-emerald-900/60 text-emerald-300 px-2 py-0.5 rounded border border-emerald-700 font-mono">
            {formData.page_count} Pages Extracted
          </span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center px-4 bg-slate-900 border-b border-slate-800 space-x-1 overflow-x-auto text-xs">
        <button
          onClick={() => setActiveTab('tables')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'tables'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>📊 Measurement Tables</span>
          {formData.structured_tables && (
            <span className="ml-1 text-[10px] px-1.5 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded font-medium">
              Ready
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('raw_text')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'raw_text'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>📄 Extracted Text</span>
          {formData.raw_extracted_text && (
            <span className="ml-1 text-[10px] px-1.5 py-0.2 bg-slate-800 text-slate-300 rounded font-mono">
              {formData.raw_extracted_text.length} chars
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('ratings')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'ratings'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Zap className="w-4 h-4" />
          <span>Electrical Ratings</span>
        </button>
        <button
          onClick={() => setActiveTab('customer')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'customer'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Building className="w-4 h-4" />
          <span>Customer & Sample</span>
        </button>
        <button
          onClick={() => setActiveTab('tests')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'tests'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Cpu className="w-4 h-4" />
          <span>Tests & Conformity</span>
        </button>
        <button
          onClick={() => setActiveTab('lab')}
          className={`flex items-center space-x-1.5 px-3 py-2.5 border-b-2 font-medium transition shrink-0 ${
            activeTab === 'lab'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Lab Assessment</span>
        </button>
      </div>

      {/* Feedback Messages */}
      {successMessage && (
        <div className="mx-4 mt-3 p-2.5 bg-emerald-950/80 border border-emerald-800 rounded-lg text-emerald-300 text-xs flex items-center space-x-2">
          <CheckCircle className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>{successMessage}</span>
        </div>
      )}
      {errorMessage && (
        <div className="mx-4 mt-3 p-2.5 bg-rose-950/80 border border-rose-800 rounded-lg text-rose-300 text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Form Content Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs">
        {/* TAB: MEASUREMENT TABLES */}
        {activeTab === 'tables' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-slate-200 text-xs">
                  Reconstructed Measurement Tables
                </span>
                <span className="text-[10px] px-2 py-0.5 bg-emerald-950/70 text-emerald-400 border border-emerald-800 rounded font-mono">
                  Qwen 2.5 Coder GPU Engine
                </span>
              </div>

              {formData.structured_tables && (
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={handleCopyTable}
                    className="flex items-center space-x-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-medium transition shadow-sm"
                  >
                    {copiedTable ? (
                      <>
                        <CheckCheck className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400 font-medium">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-sky-400" />
                        <span>Copy Markdown</span>
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={handleDownloadTable}
                    className="flex items-center space-x-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-medium transition shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Download .md</span>
                  </button>
                </div>
              )}
            </div>

            {formData.structured_tables ? (
              <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-5 shadow-inner">
                <MarkdownTableRenderer markdown={formData.structured_tables} />
              </div>
            ) : (
              <div className="p-8 text-center bg-slate-950/60 border border-slate-800 rounded-xl text-slate-400">
                <p className="text-sm font-medium text-slate-300">No measurement tables extracted for this document</p>
                <p className="text-xs text-slate-500 mt-1">
                  Upload a test datasheet or logsheet (e.g. Loss Measurement, Pressure Test) to extract tabular grids.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 0: RAW EXTRACTED TEXT */}
        {activeTab === 'raw_text' && (
          <div className="space-y-4">
            {/* Sheet Selector & Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
              <div className="flex items-center space-x-1.5 overflow-x-auto">
                <span className="text-slate-400 font-medium text-[11px] mr-1">View Sheet:</span>
                <button
                  type="button"
                  onClick={() => setSelectedPageForText('all')}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                    selectedPageForText === 'all'
                      ? 'bg-sky-600 text-white shadow-sm'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  All Sheets Combined
                </button>
                {record.pages && record.pages.map((p) => (
                  <button
                    key={p.page_number}
                    type="button"
                    onClick={() => setSelectedPageForText(p.page_number)}
                    className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                      selectedPageForText === p.page_number
                        ? 'bg-sky-600 text-white shadow-sm'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    Sheet {p.page_number}
                  </button>
                ))}
              </div>

              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={handleCopyText}
                  className="flex items-center space-x-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-medium transition shadow-sm"
                  title="Copy extracted text to clipboard"
                >
                  {copiedText ? (
                    <>
                      <CheckCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 font-medium">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-sky-400" />
                      <span>Copy Text</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleDownloadText}
                  className="flex items-center space-x-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-lg text-xs font-medium transition shadow-sm"
                  title="Download extracted text as a .txt file"
                >
                  <Download className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Download .txt</span>
                </button>
              </div>
            </div>

            {/* Monospace Text Area */}
            <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-4 space-y-2.5 shadow-inner">
              <div className="flex items-center justify-between text-[11px] text-slate-400 border-b border-slate-800 pb-2">
                <span className="font-medium text-slate-300 flex items-center space-x-1.5">
                  <FileText className="w-3.5 h-3.5 text-sky-400" />
                  <span>
                    {selectedPageForText === 'all' ? 'Combined Extracted Text' : `Sheet ${selectedPageForText} Extracted Text`}
                  </span>
                </span>
                <span className="font-mono text-slate-400">
                  {currentDisplayedText.length} characters • {currentDisplayedText.trim().split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
              <textarea
                rows={16}
                value={currentDisplayedText}
                onChange={(e) => {
                  if (selectedPageForText === 'all') {
                    handleInputChange('raw_extracted_text', e.target.value);
                  }
                }}
                readOnly={selectedPageForText !== 'all'}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3.5 text-slate-200 font-mono text-xs leading-relaxed focus:ring-1 focus:ring-sky-500 focus:outline-none resize-y selection:bg-sky-900 selection:text-white"
                placeholder="No text extracted for this document."
              />
              <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                <span>
                  {selectedPageForText === 'all' 
                    ? '💡 You can edit or fine-tune the extracted text directly before saving.'
                    : `Viewing Sheet ${selectedPageForText}. Switch to "All Sheets Combined" to edit.`}
                </span>
                {!formData.is_valid_crf && (
                  <span className="text-amber-400 font-medium">
                    Non-CRF document: Content retained in raw format
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
        {/* TAB 1: ELECTRICAL RATINGS */}
        {activeTab === 'ratings' && (
          <div className="space-y-4">
            <div className="p-3.5 bg-sky-950/30 border border-sky-800/40 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <label className="font-semibold text-slate-200 flex items-center">
                  Raw Rating Specification
                  <ConfidenceBadge score={confidence.rating_raw} />
                </label>
              </div>
              <textarea
                rows={2}
                value={formData.rating_raw || ''}
                onChange={(e) => handleInputChange('rating_raw', e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="e.g. 250 kVA, 11/.433 kV, 3 Phase, 50 Hz, Copper..."
              />
              <p className="text-[11px] text-sky-400/80 flex items-center space-x-1">
                <span>💡 Tip: Saving this form automatically re-runs deterministic regex disaggregation.</span>
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              {/* Power Rating */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Rated Power (kVA)
                </label>
                <input
                  type="number"
                  step="any"
                  value={formData.power_rating_kva ?? ''}
                  onChange={(e) => handleInputChange('power_rating_kva', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="e.g. 250"
                />
              </div>

              {/* HV Voltage */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  High Voltage - HV (kV)
                </label>
                <input
                  type="number"
                  step="any"
                  value={formData.voltage_hv_kv ?? ''}
                  onChange={(e) => handleInputChange('voltage_hv_kv', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="e.g. 11.0"
                />
              </div>

              {/* LV Voltage */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Low Voltage - LV (kV)
                </label>
                <input
                  type="number"
                  step="any"
                  value={formData.voltage_lv_kv ?? ''}
                  onChange={(e) => handleInputChange('voltage_lv_kv', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="e.g. 0.433"
                />
              </div>

              {/* Phases */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Phase Count
                </label>
                <input
                  type="number"
                  value={formData.phase_count ?? ''}
                  onChange={(e) => handleInputChange('phase_count', e.target.value ? parseInt(e.target.value, 10) : null)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="3"
                />
              </div>

              {/* Frequency */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Rated Frequency (Hz)
                </label>
                <input
                  type="number"
                  step="any"
                  value={formData.frequency_hz ?? ''}
                  onChange={(e) => handleInputChange('frequency_hz', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="50"
                />
              </div>

              {/* Cooling Class */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Cooling Type
                </label>
                <input
                  type="text"
                  value={formData.cooling_type || ''}
                  onChange={(e) => handleInputChange('cooling_type', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="ONAN"
                />
              </div>

              {/* Vector Group */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Vector Group
                </label>
                <input
                  type="text"
                  value={formData.vector_group || ''}
                  onChange={(e) => handleInputChange('vector_group', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="Dyn11"
                />
              </div>

              {/* Winding Material */}
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <label className="text-slate-400 block mb-1">
                  Winding Conductor
                </label>
                <input
                  type="text"
                  value={formData.winding_material || ''}
                  onChange={(e) => handleInputChange('winding_material', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 font-mono text-sky-300 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="Copper"
                />
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: CUSTOMER & SAMPLE DETAILS */}
        {activeTab === 'customer' && (
          <div className="space-y-3.5">
            <div>
              <label className="text-slate-300 font-medium block mb-1 flex items-center">
                Customer Name
                <ConfidenceBadge score={confidence.customer_name} />
              </label>
              <input
                type="text"
                value={formData.customer_name || ''}
                onChange={(e) => handleInputChange('customer_name', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="Enter customer entity name"
              />
            </div>

            <div>
              <label className="text-slate-300 font-medium block mb-1 flex items-center">
                Customer Address
                <ConfidenceBadge score={confidence.customer_address} />
              </label>
              <textarea
                rows={2}
                value={formData.customer_address || ''}
                onChange={(e) => handleInputChange('customer_address', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="Plant address, city, state"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-medium block mb-1 flex items-center">
                  Sample Name
                  <ConfidenceBadge score={confidence.sample_name} />
                </label>
                <input
                  type="text"
                  value={formData.sample_name || ''}
                  onChange={(e) => handleInputChange('sample_name', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-slate-300 font-medium block mb-1 flex items-center">
                  Sample Type
                  <ConfidenceBadge score={confidence.sample_type} />
                </label>
                <input
                  type="text"
                  value={formData.sample_type || ''}
                  onChange={(e) => handleInputChange('sample_type', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-medium block mb-1 flex items-center">
                  Serial Number(s)
                  <ConfidenceBadge score={confidence.serial_number} />
                </label>
                <input
                  type="text"
                  value={formData.serial_number || ''}
                  onChange={(e) => handleInputChange('serial_number', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs font-mono focus:ring-1 focus:ring-sky-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-slate-300 font-medium block mb-1 flex items-center">
                  Drawing Number(s)
                  <ConfidenceBadge score={confidence.drawing_number} />
                </label>
                <input
                  type="text"
                  value={formData.drawing_number || ''}
                  onChange={(e) => handleInputChange('drawing_number', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs font-mono focus:ring-1 focus:ring-sky-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="text-slate-300 font-medium block mb-1 flex items-center">
                Manufacturer's Details
                <ConfidenceBadge score={confidence.manufacturer_details} />
              </label>
              <textarea
                rows={2}
                value={formData.manufacturer_details || ''}
                onChange={(e) => handleInputChange('manufacturer_details', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
              />
            </div>
          </div>
        )}

        {/* TAB 3: TESTS & CONFORMITY */}
        {activeTab === 'tests' && (
          <div className="space-y-3.5">
            <div>
              <label className="text-slate-300 font-medium block mb-1 flex items-center">
                Details of Test(s) Requested
                <ConfidenceBadge score={confidence.tests_requested} />
              </label>
              <textarea
                rows={2}
                value={formData.tests_requested || ''}
                onChange={(e) => handleInputChange('tests_requested', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="Type Test, Short Circuit, Temp Rise..."
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-medium block mb-1 flex items-center">
                  Criteria for Evaluation (Standard)
                  <ConfidenceBadge score={confidence.evaluation_criteria} />
                </label>
                <input
                  type="text"
                  value={formData.evaluation_criteria || ''}
                  onChange={(e) => handleInputChange('evaluation_criteria', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="e.g. IS 1180 / IS 2026"
                />
              </div>
              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  Number of Samples
                </label>
                <input
                  type="text"
                  value={formData.number_of_samples || ''}
                  onChange={(e) => handleInputChange('number_of_samples', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                  placeholder="1"
                />
              </div>
            </div>

            <div>
              <label className="text-slate-300 font-medium block mb-1">
                Conformity Statement Decision Rule (Sheet 2)
              </label>
              <textarea
                rows={2}
                value={formData.conformity_rule || ''}
                onChange={(e) => handleInputChange('conformity_rule', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="(i) Decision based on standard requirement..."
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  MSME Discount Status
                </label>
                <select
                  value={formData.msme_discount || 'Not Applicable'}
                  onChange={(e) => handleInputChange('msme_discount', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                >
                  <option value="Applicable">Applicable</option>
                  <option value="Not Applicable">Not Applicable</option>
                </select>
              </div>
              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  Sample Disposal Preference
                </label>
                <select
                  value={formData.sample_disposal || 'Taking back the sample after testing'}
                  onChange={(e) => handleInputChange('sample_disposal', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                >
                  <option value="Taking back the sample after testing">Taking back the sample after testing</option>
                  <option value="CPRI can scrap and dispose it off">CPRI can scrap and dispose it off</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: LABORATORY ASSESSMENT */}
        {activeTab === 'lab' && (
          <div className="space-y-3.5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  Physical Condition of Sample
                </label>
                <select
                  value={formData.physical_condition_sample || 'Suitable for Testing'}
                  onChange={(e) => handleInputChange('physical_condition_sample', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                >
                  <option value="Suitable for Testing">Suitable for Testing</option>
                  <option value="Not suitable for Testing">Not suitable for Testing</option>
                </select>
              </div>
              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  Laboratory Work Capability
                </label>
                <select
                  value={formData.lab_capability || 'Yes'}
                  onChange={(e) => handleInputChange('lab_capability', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                >
                  <option value="Yes">Yes</option>
                  <option value="No">No</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-slate-300 font-medium block mb-1">
                Accepting Test Engineer Name / Signatory
              </label>
              <input
                type="text"
                value={formData.test_engineer_name || ''}
                onChange={(e) => handleInputChange('test_engineer_name', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="Test In charge"
              />
            </div>

            <div>
              <label className="text-slate-300 font-medium block mb-1">
                Deviations / Discrepancies Noticed
              </label>
              <textarea
                rows={2}
                value={formData.deviations_noticed || ''}
                onChange={(e) => handleInputChange('deviations_noticed', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                placeholder="Any deviations recorded during laboratory inspection"
              />
            </div>
          </div>
        )}
      </div>

      {/* Verification Sign-Off Footer */}
      <div className="p-4 bg-slate-800/90 border-t border-slate-700/80 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1">Reviewing Operator / Engineer</label>
            <input
              type="text"
              value={formData.verified_by || ''}
              onChange={(e) => handleInputChange('verified_by', e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder="Your name"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Verification Remarks</label>
            <input
              type="text"
              value={formData.verification_notes || ''}
              onChange={(e) => handleInputChange('verification_notes', e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder="e.g. Verified with drawing specifications"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <button
            onClick={() => handleSave('REJECTED')}
            disabled={saving}
            className="flex items-center space-x-1 px-3 py-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 hover:text-white rounded-lg text-xs font-semibold transition"
          >
            <X className="w-3.5 h-3.5" />
            <span>Reject Form</span>
          </button>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => handleSave(null)}
              disabled={saving}
              className="flex items-center space-x-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 hover:text-white rounded-lg text-xs font-semibold transition"
            >
              <Save className="w-3.5 h-3.5" />
              <span>Save Draft</span>
            </button>

            <button
              onClick={() => handleSave('VERIFIED')}
              disabled={saving}
              className="flex items-center space-x-1.5 px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-lg shadow-sky-600/30 transition"
            >
              <Check className="w-4 h-4" />
              <span>{saving ? 'Processing...' : 'Verify & Approve'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
