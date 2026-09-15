import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import type { Chunk } from '../api/client';

interface ProvenancePanelProps {
  paperId: string;
  chunkId: string | null;
  onClose: () => void;
}

export const ProvenancePanel: React.FC<ProvenancePanelProps> = ({ paperId, chunkId, onClose }) => {
  const [chunk, setChunk] = useState<Chunk | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!chunkId || !paperId) return;

    const fetchChunk = async () => {
      setIsLoading(true);
      setError('');
      try {
        const res = await apiClient.getPaperChunks(paperId);
        const found = res.data.chunks.find((c: Chunk) => c.chunk_id === chunkId);
        if (found) {
          setChunk(found);
        } else {
          setError('Chunk not found');
        }
      } catch (err: any) {
        setError('Failed to load chunk');
      } finally {
        setIsLoading(false);
      }
    };

    fetchChunk();
  }, [chunkId, paperId]);

  if (!chunkId) return null;

  return (
    <div 
      className="fixed inset-y-0 right-0 w-96 bg-white shadow-xl border-l flex flex-col z-50 transform transition-transform"
      data-testid="provenance-panel"
    >
      <div className="flex justify-between items-center p-4 border-b">
        <h3 className="font-bold text-gray-800">Source Highlight</h3>
        <button 
          onClick={onClose}
          className="text-gray-500 hover:text-gray-700 p-1"
          data-testid="close-btn"
        >
          ✕
        </button>
      </div>

      <div className="p-4 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="text-gray-500 animate-pulse" data-testid="loading-state">Loading...</div>
        ) : error ? (
          <div className="text-red-500">{error}</div>
        ) : chunk ? (
          <div className="space-y-4">
            <div className="text-xs text-gray-500 uppercase font-bold tracking-wider">
              {chunk.section_title || 'Unknown Section'} • Page {chunk.page_number}
            </div>
            
            <div className="bg-yellow-50 border border-yellow-200 p-4 rounded text-sm text-gray-800 leading-relaxed font-serif whitespace-pre-wrap">
              {chunk.text}
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-gray-100 text-gray-600">
                ID: {chunk.chunk_id}
              </span>
              {chunk.contains_math && (
                <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-purple-100 text-purple-700">
                  Math-heavy
                </span>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
