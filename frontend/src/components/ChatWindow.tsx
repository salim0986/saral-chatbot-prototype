import React, { useState, useRef, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import type { MessageProps } from './MessageBubble';

interface ChatWindowProps {
  messages: MessageProps[];
  isLoading: boolean;
  onSendMessage: (text: string) => void;
  onBadgeClick: (chunkId: string) => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages, isLoading, onSendMessage, onBadgeClick }) => {
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 border rounded-lg shadow-inner overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-400 mt-10">
            <p>Ready to generate content. Try asking for a 90s policy script.</p>
          </div>
        ) : (
          messages.map((m, i) => (
            <MessageBubble 
              key={i} 
              role={m.role} 
              content={m.content} 
              sentences={m.sentences} 
              onBadgeClick={onBadgeClick} 
            />
          ))
        )}
        
        {isLoading && (
          <div className="flex justify-start mb-4">
            <div className="bg-white border border-gray-200 text-gray-500 rounded-lg p-4 shadow-sm" data-testid="loading-indicator">
              <span className="animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="bg-white border-t p-4">
        <form onSubmit={handleSubmit} className="flex space-x-2">
          <input
            type="text"
            className="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
            placeholder="Type instructions (e.g. Make slide 2 less technical)..."
            value={input}
            onChange={e => setInput(e.target.value)}
            disabled={isLoading}
            data-testid="chat-input"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-teal-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
};
