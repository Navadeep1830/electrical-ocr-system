import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getHealth = async () => {
  const resp = await client.get('/api/health');
  return resp.data;
};

export const triggerVlmLoad = async () => {
  const resp = await client.post('/api/vlm/load');
  return resp.data;
};

export const getRecords = async (status = 'ALL', search = '', limit = 50, offset = 0) => {
  const params = { limit, offset };
  if (status && status !== 'ALL') {
    params.status = status;
  }
  if (search) {
    params.search = search;
  }
  const resp = await client.get('/api/records', { params });
  return resp.data;
};

export const getRecord = async (id) => {
  const resp = await client.get(`/api/records/${id}`);
  return resp.data;
};

export const uploadDocument = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await client.post('/api/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });
  return resp.data;
};

export const processExistingFile = async (filePath) => {
  const resp = await client.post('/api/process-existing', { file_path: filePath });
  return resp.data;
};

export const updateRecord = async (id, data) => {
  const resp = await client.put(`/api/records/${id}`, data);
  return resp.data;
};

export const deleteRecord = async (id) => {
  const resp = await client.delete(`/api/records/${id}`);
  return resp.data;
};

export const clearAllRecords = async () => {
  const resp = await client.delete('/api/records/clear/all');
  return resp.data;
};

export const exportRecord = async (id, format = 'json') => {
  const resp = await client.get(`/api/records/${id}/export`, {
    params: { format },
    responseType: format === 'csv' ? 'blob' : 'json',
  });
  return resp.data;
};

export const batchScan = async (folderPath) => {
  const resp = await client.post(`/api/batch-scan?folder_path=${encodeURIComponent(folderPath)}`);
  return resp.data;
};

export const recognizeHandwritingCrop = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await client.post('/api/trocr/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return resp.data;
};

export const extractHandwritingPage = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await client.post('/api/trocr/extract-page', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return resp.data;
};

export default client;
