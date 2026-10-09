import React, { useState, useEffect, useRef } from 'react';
import { 
  FileText, Upload, FolderUp, CheckCircle, AlertTriangle, 
  Cpu, ArrowLeft, RefreshCw, Zap, Shield, Search, Database, HardDrive, Check
} from 'lucide-react';
import { 
  getHealth, getRecords, getRecord, uploadDocument, 
  processExistingFile, deleteRecord, batchScan, triggerVlmLoad 
} from './api';
import DocumentViewer from './components/DocumentViewer';
import FormEditor from './components/FormEditor';
import RecordTable from './components/RecordTable';

export default function App() {
  const [health, setHealth] = useState(null);
  const [records, setRecords] = useState([]);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [activePageIndex, setActivePageIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  
  // Modals & Upload state
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [showScanModal, setShowScanModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [localFilePath, setLocalFilePath] = useState('/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf');
  const [localFolderPath, setLocalFolderPath] = useState('/home/navadeep/Downloads/Track 3 - AT RG');
  const [modalMessage, setModalMessage] = useState({ text: '', type: '' });

  const fileInputRef = useRef(null);

  // Poll health and load records on mount
  useEffect(() => {
    fetchHealth();
    fetchRecords();

    const interval = setInterval(() => {
      fetchHealth();
    }, 15000);
    return () => clearInterval(interval);
  }, [statusFilter, searchTerm]);

  const fetchHealth = async () => {
    try {
      const data = await getHealth();
      setHealth(data);
    } catch (err) {
      console.error('Failed to get system health:', err);
    }
  };

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const data = await getRecords(statusFilter, searchTerm);
      setRecords(data);
    } catch (err) {
      console.error('Failed to fetch records:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectRecord = async (rec) => {
    try {
      setLoading(true);
      const fullRecord = await getRecord(rec.id);
      setSelectedRecord(fullRecord);
      setActivePageIndex(0);
    } catch (err) {
      console.error('Failed to get full record details:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRecord = async (id) => {
    try {
      await deleteRecord(id);
      if (selectedRecord?.id === id) {
        setSelectedRecord(null);
      }
      fetchRecords();
    } catch (err) {
      alert('Failed to delete record: ' + (err.message || 'error'));
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploading(true);
      setUploadProgress(10);
      const record = await uploadDocument(file, (progressEvent) => {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(percent);
      });
      fetchRecords();
      handleSelectRecord(record);
    } catch (err) {
      alert('Upload failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleProcessLocalFile = async () => {
    if (!localFilePath.trim()) return;
    try {
      setLoading(true);
      setModalMessage({ text: 'Processing document with OCR / VLM...', type: 'info' });
      const record = await processExistingFile(localFilePath.trim());
      setModalMessage({ text: 'Extracted successfully!', type: 'success' });
      fetchRecords();
      setTimeout(() => {
        setShowScanModal(false);
        setModalMessage({ text: '', type: '' });
        handleSelectRecord(record);
      }, 700);
    } catch (err) {
      setModalMessage({ text: err.response?.data?.detail || 'Extraction failed', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleBatchScan = async () => {
    if (!localFolderPath.trim()) return;
    try {
      setLoading(true);
      setModalMessage({ text: 'Scanning directory and processing forms...', type: 'info' });
      const res = await batchScan(localFolderPath.trim());
      setModalMessage({ 
        text: `Batch scan complete! Processed ${res.processed_count} of ${res.total_found} PDFs.`, 
        type: 'success' 
      });
      fetchRecords();
      setTimeout(() => {
        setShowBatchModal(false);
        setModalMessage({ text: '', type: '' });
      }, 1500);
    } catch (err) {
      setModalMessage({ text: err.response?.data?.detail || 'Batch scan failed', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  // KPI Calculations
  const totalCount = records.length;
  const pendingCount = records.filter(r => r.status === 'PENDING_VERIFICATION').length;
  const verifiedCount = records.filter(r => r.status === 'VERIFIED').length;

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      {/* Top Header */}
      <header className="sticky top-0 z-30 bg-slate-900/95 border-b border-slate-800 backdrop-blur-md px-4 sm:px-8 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-cyan-400 flex items-center justify-center shadow-lg shadow-sky-600/30">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-bold text-slate-100 text-base tracking-tight">PowerNext OCR</h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-950 text-sky-400 border border-sky-800/60 font-mono">
                CPRI/QAF/01A
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Air-Gapped Electrical Customer Request Form Extraction & Staging System
            </p>
          </div>
        </div>

        {/* System & Hardware Health Status */}
        <div className="flex items-center space-x-3 text-xs">
          <div className="hidden md:flex items-center space-x-2 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700/80">
            <Cpu className="w-4 h-4 text-sky-400" />
            <div className="flex flex-col text-[11px]">
              <span className="font-medium text-slate-200">
                {health?.vlm_engine?.gpu?.available ? health.vlm_engine.gpu.device_name : 'CPU Host Mode'}
              </span>
              <span className="text-[10px] text-slate-400">
                VLM: {health?.vlm_engine?.is_loaded ? 'Qwen2.5-VL Ready' : 'OCR Fallback Ready'}
              </span>
            </div>
          </div>

          {/* Quick Actions */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".pdf,.png,.jpg,.jpeg"
            className="hidden"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-xl font-medium transition shadow-md shadow-sky-600/30"
          >
            <Upload className="w-4 h-4" />
            <span className="hidden sm:inline">{isUploading ? `Uploading ${uploadProgress}%` : 'Upload PDF'}</span>
          </button>

          <button
            onClick={() => setShowScanModal(true)}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-xl font-medium transition"
          >
            <HardDrive className="w-4 h-4 text-emerald-400" />
            <span className="hidden sm:inline">Scan Local File</span>
          </button>

          <button
            onClick={() => setShowBatchModal(true)}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white rounded-xl font-medium transition"
          >
            <FolderUp className="w-4 h-4 text-amber-400" />
            <span className="hidden sm:inline">Batch Folder</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-4 sm:p-6 max-w-7xl mx-auto w-full">
        {selectedRecord ? (
          /* Side-by-Side Document Inspection & Staging View */
          <div className="flex flex-col h-[calc(100vh-6.5rem)] space-y-3">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setSelectedRecord(null)}
                className="flex items-center space-x-2 text-xs font-semibold text-slate-400 hover:text-slate-100 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 hover:border-slate-700 transition"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Return to Records Table</span>
              </button>
              <div className="text-xs text-slate-400 font-mono">
                Record #{selectedRecord.id} • SHA-256: {selectedRecord.file_hash?.slice(0, 12)}...
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1 overflow-hidden">
              {/* Left Pane: Zoomable Multi-Page Document Inspector */}
              <div className="h-full overflow-hidden">
                <DocumentViewer
                  record={selectedRecord}
                  activePageIndex={activePageIndex}
                  onPageChange={setActivePageIndex}
                />
              </div>

              {/* Right Pane: Field Staging & Confidence Editor */}
              <div className="h-full overflow-hidden">
                <FormEditor
                  record={selectedRecord}
                  onRecordUpdated={(updated) => {
                    setSelectedRecord(updated);
                    fetchRecords();
                  }}
                />
              </div>
            </div>
          </div>
        ) : (
          /* Records Dashboard View */
          <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-slate-900/80 border border-slate-800/80 p-4 rounded-xl backdrop-blur-md shadow-lg flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 font-medium">Total Test Request Forms</p>
                  <p className="text-2xl font-bold text-slate-100 mt-1">{totalCount}</p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-sky-950/70 border border-sky-800/50 flex items-center justify-center text-sky-400">
                  <Database className="w-5 h-5" />
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800/80 p-4 rounded-xl backdrop-blur-md shadow-lg flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 font-medium">Pending Human Verification</p>
                  <p className="text-2xl font-bold text-amber-400 mt-1">{pendingCount}</p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-amber-950/70 border border-amber-800/50 flex items-center justify-center text-amber-400">
                  <AlertTriangle className="w-5 h-5" />
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800/80 p-4 rounded-xl backdrop-blur-md shadow-lg flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 font-medium">Verified & Stored Records</p>
                  <p className="text-2xl font-bold text-emerald-400 mt-1">{verifiedCount}</p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-emerald-950/70 border border-emerald-800/50 flex items-center justify-center text-emerald-400">
                  <CheckCircle className="w-5 h-5" />
                </div>
              </div>
            </div>

            {/* Quick Ingestion Action Banner */}
            <div className="p-4 bg-gradient-to-r from-sky-950/50 via-slate-900 to-indigo-950/50 border border-sky-800/30 rounded-xl flex flex-col md:flex-row items-center justify-between gap-4">
              <div>
                <h3 className="font-semibold text-sm text-slate-100 flex items-center space-x-2">
                  <span>⚡ Quick Ingest: Track 3 Customer Request Form</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Directly load and extract the PowerNext dataset file: <code className="text-sky-300 font-mono text-[11px]">/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf</code>
                </p>
              </div>
              <button
                onClick={() => {
                  setLocalFilePath('/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf');
                  setShowScanModal(true);
                }}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-md transition shrink-0"
              >
                Scan Target Document
              </button>
            </div>

            {/* Records Data Table */}
            <RecordTable
              records={records}
              selectedRecordId={selectedRecord?.id}
              onSelectRecord={handleSelectRecord}
              onDeleteRecord={handleDeleteRecord}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              searchTerm={searchTerm}
              onSearchChange={setSearchTerm}
              loading={loading}
            />
          </div>
        )}
      </main>

      {/* SCAN SINGLE FILE MODAL */}
      {showScanModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-semibold text-slate-100 flex items-center space-x-2">
              <HardDrive className="w-5 h-5 text-emerald-400" />
              <span>Scan Local Document Directly</span>
            </h3>
            <p className="text-xs text-slate-400">
              Enter the absolute path of a PDF or image test request form on your local machine:
            </p>

            <input
              type="text"
              value={localFilePath}
              onChange={(e) => setLocalFilePath(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder="/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf"
            />

            {modalMessage.text && (
              <div className={`p-3 rounded-lg text-xs flex items-center space-x-2 ${
                modalMessage.type === 'error' ? 'bg-rose-950 text-rose-300 border border-rose-800' :
                modalMessage.type === 'success' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' :
                'bg-sky-950 text-sky-300 border border-sky-800'
              }`}>
                <span>{modalMessage.text}</span>
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                onClick={() => { setShowScanModal(false); setModalMessage({ text: '', type: '' }); }}
                disabled={loading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
              >
                Cancel
              </button>
              <button
                onClick={handleProcessLocalFile}
                disabled={loading}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold shadow-md transition"
              >
                {loading ? 'Extracting...' : 'Scan & Ingest'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* BATCH FOLDER SCAN MODAL */}
      {showBatchModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-semibold text-slate-100 flex items-center space-x-2">
              <FolderUp className="w-5 h-5 text-amber-400" />
              <span>Batch Directory Ingestion</span>
            </h3>
            <p className="text-xs text-slate-400">
              Provide the directory path containing electrical test forms. All PDFs will be scanned, rendered at 300 DPI, and ingested:
            </p>

            <input
              type="text"
              value={localFolderPath}
              onChange={(e) => setLocalFolderPath(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
              placeholder="/home/navadeep/Downloads/Track 3 - AT RG"
            />

            {modalMessage.text && (
              <div className={`p-3 rounded-lg text-xs flex items-center space-x-2 ${
                modalMessage.type === 'error' ? 'bg-rose-950 text-rose-300 border border-rose-800' :
                modalMessage.type === 'success' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' :
                'bg-sky-950 text-sky-300 border border-sky-800'
              }`}>
                <span>{modalMessage.text}</span>
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                onClick={() => { setShowBatchModal(false); setModalMessage({ text: '', type: '' }); }}
                disabled={loading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
              >
                Cancel
              </button>
              <button
                onClick={handleBatchScan}
                disabled={loading}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-semibold shadow-md transition"
              >
                {loading ? 'Batch Scanning...' : 'Start Batch Ingest'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
