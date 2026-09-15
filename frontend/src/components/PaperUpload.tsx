import React, { useState, useRef } from 'react';
import type { ChangeEvent } from 'react';
import { apiClient } from '../api/client';
import type { PaperStatusResponse } from '../api/client';

interface PaperUploadProps {
  onPaperReady: (paperId: string) => void;
}

export const PaperUpload: React.FC<PaperUploadProps> = ({ onPaperReady }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<string>('idle'); // idle, uploading, processing, ready, error
  const [errorMessage, setErrorMessage] = useState('');
  const [paperName, setPaperName] = useState('');
  const [stats, setStats] = useState<{chunks: number, math: number, figs: number} | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const validateAndUpload = async (file: File) => {
    if (file.size > 50 * 1024 * 1024) {
      setStatus('error');
      setErrorMessage('File size exceeds 50MB limit.');
      return;
    }
    
    if (file.type !== 'application/pdf' && !file.name.endsWith('.tex')) {
      setStatus('error');
      setErrorMessage('Unsupported file format. Please upload PDF or .tex.');
      return;
    }

    setPaperName(file.name);
    setStatus('uploading');
    setErrorMessage('');
    
    try {
      const paperId = await apiClient.uploadPaper(file);
      setStatus('processing');
      pollStatus(paperId);
    } catch (err: any) {
      setStatus('error');
      setErrorMessage(err.message || 'Upload failed');
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndUpload(e.target.files[0]);
    }
  };

  const pollStatus = async (paperId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await apiClient.getPaperStatus(paperId);
        if (res.data.status === 'ready') {
          clearInterval(interval);
          
          // Fetch chunk stats
          try {
            const chunksRes = await apiClient.getPaperChunks(paperId);
            const chunks = chunksRes.data.chunks;
            setStats({
              chunks: chunks.length,
              math: chunks.filter(c => c.contains_math).length,
              figs: chunks.filter(c => c.has_figure).length
            });
          } catch(e) {}
          
          setStatus('ready');
          onPaperReady(paperId);
        } else if (res.data.status === 'failed') {
          clearInterval(interval);
          setStatus('error');
          setErrorMessage(res.data.error || 'Ingestion failed');
        }
      } catch (err) {
        // Just retry on network errors during polling
      }
    }, 2000);
  };

  return (
    <div className="paper-upload-container p-6 bg-white rounded shadow-sm">
      <h2 className="text-xl font-bold mb-4">Upload Paper</h2>
      
      {status === 'idle' || status === 'error' ? (
        <div 
          data-testid="drop-zone"
          className={`border-2 border-dashed rounded p-12 text-center cursor-pointer transition-colors ${
            isDragging ? 'border-teal-500 bg-teal-50' : 'border-gray-300 hover:border-teal-400'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <p className="text-gray-600">Drag & drop your PDF or .tex file here</p>
          <p className="text-sm text-gray-400 mt-2">Max size: 50MB</p>
          <input 
            data-testid="file-input"
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            className="hidden" 
            accept=".pdf,.tex"
          />
        </div>
      ) : (
        <div className="status-display p-6 border rounded bg-gray-50">
          <h3 className="font-medium text-lg">{paperName}</h3>
          
          {status === 'uploading' && <p className="text-blue-600 mt-2">Uploading...</p>}
          
          {status === 'processing' && <p data-testid="processing-status" className="text-orange-500 mt-2">Processing (Extracting text & math)...</p>}
          
          {status === 'ready' && (
            <div data-testid="ready-status" className="mt-4">
              <p className="text-green-600 font-medium mb-2">✓ Ready</p>
              {stats && (
                <ul className="text-sm text-gray-600 space-y-1">
                  <li>✓ {stats.chunks} chunks ready</li>
                  <li>✓ {stats.math} math blocks detected</li>
                  <li>⚠ {stats.figs} figures detected (captions extracted)</li>
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {status === 'error' && (
        <div data-testid="error-message" className="mt-4 p-3 bg-red-50 text-red-700 rounded border border-red-200">
          {errorMessage}
        </div>
      )}
    </div>
  );
};
