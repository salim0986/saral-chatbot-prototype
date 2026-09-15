import React from 'react';

export interface DiffHunk {
  operation: 'insert' | 'delete' | 'equal';
  text: string;
}

interface DeltaViewProps {
  diffHunks: DiffHunk[];
  reason: string;
  onAccept: () => void;
  onReject?: () => void;
}

export const DeltaView: React.FC<DeltaViewProps> = ({ diffHunks, reason, onAccept, onReject }) => {
  return (
    <div className="w-full mb-4 border border-teal-200 rounded-lg overflow-hidden shadow-sm" data-testid="delta-view">
      <div className="bg-teal-50 px-4 py-2 border-b border-teal-200 flex justify-between items-center">
        <h4 className="font-semibold text-teal-800 text-sm">Suggested Revision</h4>
        <div className="space-x-2">
          {onReject && (
            <button 
              onClick={onReject}
              className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800 bg-white border rounded shadow-sm"
              data-testid="reject-btn"
            >
              Reject
            </button>
          )}
          <button 
            onClick={onAccept}
            className="px-3 py-1 text-xs text-white bg-teal-600 hover:bg-teal-700 rounded shadow-sm"
            data-testid="accept-btn"
          >
            Accept
          </button>
        </div>
      </div>
      
      <div className="p-4 bg-white font-serif text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
        {diffHunks.map((hunk, idx) => {
          if (hunk.operation === 'insert') {
            return (
              <span key={idx} className="bg-green-100 text-green-800 font-medium px-1 rounded mx-0.5" data-testid="diff-insert">
                {hunk.text}
              </span>
            );
          } else if (hunk.operation === 'delete') {
            return (
              <span key={idx} className="bg-red-100 text-red-800 line-through px-1 rounded mx-0.5 opacity-60" data-testid="diff-delete">
                {hunk.text}
              </span>
            );
          }
          return <span key={idx} data-testid="diff-equal">{hunk.text}</span>;
        })}
      </div>
      
      <div className="px-4 py-2 bg-gray-50 text-xs text-gray-500 italic border-t border-gray-100">
        Reason: {reason}
      </div>
    </div>
  );
};
