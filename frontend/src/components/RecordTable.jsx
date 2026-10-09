import React, { useState } from 'react';
import { 
  Search, Filter, Trash2, Eye, FileText, CheckCircle2, 
  Clock, AlertTriangle, ArrowRight, Zap 
} from 'lucide-react';

export default function RecordTable({ 
  records = [], 
  selectedRecordId, 
  onSelectRecord, 
  onDeleteRecord,
  statusFilter,
  onStatusFilterChange,
  searchTerm,
  onSearchChange,
  loading 
}) {
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  const getStatusBadge = (status) => {
    switch (status) {
      case 'VERIFIED':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-950/70 text-emerald-400 border border-emerald-800/60">
            <CheckCircle2 className="w-3 h-3" />
            <span>Verified</span>
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-950/70 text-rose-400 border border-rose-800/60">
            <AlertTriangle className="w-3 h-3" />
            <span>Rejected</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-950/70 text-amber-300 border border-amber-800/60">
            <Clock className="w-3 h-3" />
            <span>Pending</span>
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col bg-slate-900/95 border border-slate-800 rounded-xl overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Search and Filters Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between p-4 bg-slate-800/80 border-b border-slate-700/60 gap-3">
        {/* Filter Pills */}
        <div className="flex items-center space-x-1 bg-slate-900/90 p-1 rounded-xl border border-slate-700/80 text-xs">
          {['ALL', 'PENDING_VERIFICATION', 'VERIFIED', 'REJECTED'].map((filter) => {
            const label = filter === 'ALL' ? 'All Records' : filter === 'PENDING_VERIFICATION' ? 'Pending' : filter === 'VERIFIED' ? 'Verified' : 'Rejected';
            const active = statusFilter === filter;
            return (
              <button
                key={filter}
                onClick={() => onStatusFilterChange(filter)}
                className={`px-3 py-1.5 rounded-lg font-medium transition ${
                  active 
                    ? 'bg-sky-600 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Live Search */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search customer, serial, rating..."
            className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </div>
      </div>

      {/* Table Body */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950/60 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800">
            <tr>
              <th className="px-4 py-3">ID / Status</th>
              <th className="px-4 py-3">Customer & Sample</th>
              <th className="px-4 py-3">Disaggregated Ratings</th>
              <th className="px-4 py-3">Serial No</th>
              <th className="px-4 py-3">Sheets</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {records.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <FileText className="w-8 h-8 text-slate-600" />
                    <p className="text-sm font-medium">No records found matching criteria</p>
                    <p className="text-xs text-slate-500">Upload a request form or change filter parameters</p>
                  </div>
                </td>
              </tr>
            ) : (
              records.map((r) => {
                const isSelected = selectedRecordId === r.id;
                return (
                  <tr
                    key={r.id}
                    className={`transition cursor-pointer ${
                      isSelected
                        ? 'bg-sky-950/40 border-l-4 border-sky-500'
                        : 'hover:bg-slate-800/40'
                    }`}
                    onClick={() => onSelectRecord(r)}
                  >
                    {/* ID & Status */}
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <div className="flex flex-col space-y-1">
                        <div className="flex items-center space-x-1.5">
                          <span className="font-mono text-sky-400 font-semibold">#{r.id}</span>
                          {r.is_valid_crf === false && (
                            <span className="text-[9px] px-1.5 py-0.5 bg-amber-950/80 text-amber-400 border border-amber-800/80 rounded font-semibold" title="Non-CRF Document">
                              NON-CRF
                            </span>
                          )}
                        </div>
                        {getStatusBadge(r.status)}
                      </div>
                    </td>

                    {/* Customer & Sample */}
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col max-w-xs">
                        <span className="font-medium text-slate-100 truncate" title={r.customer_name || 'N/A'}>
                          {r.customer_name || <span className="text-slate-500 italic">Unknown Customer</span>}
                        </span>
                        <span className="text-[11px] text-slate-400 truncate mt-0.5">
                          {r.sample_name || r.sample_description || 'CPRI Test Sample'}
                        </span>
                      </div>
                    </td>

                    {/* Ratings */}
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col">
                        <div className="flex items-center space-x-1.5">
                          <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          <span className="font-mono text-slate-200 font-medium">
                            {r.power_rating_kva ? `${r.power_rating_kva} kVA` : r.rating_raw?.slice(0, 20) || 'N/A'}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5 font-mono">
                          {r.voltage_hv_kv ? `${r.voltage_hv_kv} / ${r.voltage_lv_kv || 0.433} kV` : ''} 
                          {r.phase_count ? ` • ${r.phase_count}-Ph` : ''}
                          {r.cooling_type ? ` • ${r.cooling_type}` : ''}
                        </div>
                      </div>
                    </td>

                    {/* Serial No */}
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <span className="font-mono text-slate-300">
                        {r.serial_number || '—'}
                      </span>
                    </td>

                    {/* Sheets */}
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[11px]">
                        {r.page_count} {r.page_count === 1 ? 'Sheet' : 'Sheets'}
                      </span>
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3.5 whitespace-nowrap text-[11px] text-slate-400 font-mono">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3.5 whitespace-nowrap text-right">
                      <div className="flex items-center justify-end space-x-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => onSelectRecord(r)}
                          className="flex items-center space-x-1 px-2.5 py-1 bg-sky-600/80 hover:bg-sky-600 text-white rounded-lg transition"
                          title="Open Staging Inspector"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Inspect</span>
                        </button>
                        <button
                          onClick={() => {
                            if (deleteConfirmId === r.id) {
                              onDeleteRecord(r.id);
                              setDeleteConfirmId(null);
                            } else {
                              setDeleteConfirmId(r.id);
                            }
                          }}
                          className={`p-1.5 rounded-lg transition ${
                            deleteConfirmId === r.id 
                              ? 'bg-rose-600 text-white' 
                              : 'hover:bg-slate-800 text-slate-400 hover:text-rose-400'
                          }`}
                          title={deleteConfirmId === r.id ? 'Click again to confirm delete' : 'Delete Record'}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
