import React from 'react';

interface SourcedSentence {
  text: string;
  source_ids: string[];
  source_pages: number[];
}

export interface MessageProps {
  role: 'user' | 'assistant';
  content?: string;
  sentences?: SourcedSentence[];
  onBadgeClick?: (chunkId: string) => void;
}

export const MessageBubble: React.FC<MessageProps> = ({ role, content, sentences, onBadgeClick }) => {
  const isUser = role === 'user';
  
  return (
    <div className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div 
        className={`max-w-[80%] rounded-lg p-4 shadow-sm ${
          isUser 
            ? 'bg-teal-600 text-white rounded-br-none' 
            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-none'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-sm max-w-none">
            {content && <p className="whitespace-pre-wrap">{content}</p>}
            
            {sentences && sentences.length > 0 && (
              <p>
                {sentences.map((sentence, idx) => (
                  <React.Fragment key={idx}>
                    {sentence.text}
                    {sentence.source_ids && sentence.source_ids.length > 0 && (
                      <sup className="ml-1 space-x-1">
                        {sentence.source_ids.map((id, sIdx) => (
                          <button
                            key={sIdx}
                            onClick={() => onBadgeClick?.(id)}
                            className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-100 text-teal-800 hover:bg-teal-200 text-xs font-bold transition-colors"
                            title={`Source chunk: ${id}`}
                            data-testid={`badge-${id}`}
                          >
                            {sIdx + 1}
                          </button>
                        ))}
                      </sup>
                    )}
                    {' '}
                  </React.Fragment>
                ))}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
