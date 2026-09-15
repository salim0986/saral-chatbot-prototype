import React, { useState, useRef, useEffect, useCallback } from 'react';
import './index.css';

// ── Types ──────────────────────────────────────────────────────────────────────
interface Chunk {
  chunk_id: string;
  page_number: number;
  section_title: string;
  block_index: number;
  text: string;
  contains_math: boolean;
  has_figure: boolean;
  figure_caption: string | null;
}

interface Sentence {
  text: string;
  source_ids: string[];
  source_pages: number[];
}

interface Slide {
  slide_number: number;
  title: string;
  script: string;
  sentences: Sentence[];
  bullet_points?: string[];
}

interface Generation {
  slides: Slide[];
  citation_coverage: number;
  low_confidence: boolean;
  audience: string;
  length: string;
}

interface DiffHunk {
  operation: 'insert' | 'delete' | 'equal';
  text: string;
}

interface Delta {
  slide_number: number;
  diff_hunks: DiffHunk[];
  reason: string;
  old_text: string;
  new_text: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  generation?: Generation;
  delta?: Delta;
  accepted?: boolean;
  rejected?: boolean;
}

// ── API Client ────────────────────────────────────────────────────────────────
const api = {
  async uploadPaper(file: File): Promise<string> {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/papers', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    return (await res.json()).data.paper_id;
  },

  async getPaperStatus(paperId: string): Promise<{ status: string; chunk_count: number; error_msg: string | null }> {
    const res = await fetch(`/api/papers/${paperId}`);
    if (!res.ok) throw new Error('Status fetch failed');
    return (await res.json()).data;
  },

  async getChunks(paperId: string): Promise<Chunk[]> {
    const res = await fetch(`/api/papers/${paperId}/chunks?page_size=200`);
    if (!res.ok) return [];
    return (await res.json()).data.chunks;
  },

  async createSession(paperId: string): Promise<string> {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_id: paperId }),
    });
    if (!res.ok) throw new Error('Session creation failed');
    return (await res.json()).data.session_id;
  },

  async generate(sessionId: string, paperId: string, audience: string, length: string): Promise<{ generation_id: string; generation: Generation }> {
    // Map display strings to backend enums
    const audienceMap: Record<string, string> = {
      'Policymakers': 'policymakers',
      'High School Students': 'students',
      'General Public': 'general_public',
      'Domain Experts': 'researchers'
    };

    const lengthMap: Record<string, string> = {
      '30 seconds': '30s',
      '60 seconds': '90s', // Backend supports 30s, 90s, 5m. Mapping 60s to 90s.
      '90 seconds': '90s',
      '5 minutes': '5m'
    };

    const res = await fetch(`/api/sessions/${sessionId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_id: paperId,
        audience: audienceMap[audience] || 'policymakers',
        length: lengthMap[length] || '90s',
        style: 'plain_english',
        output_type: 'speaker_script',
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Generation failed (${res.status})`);
    }
    return (await res.json()).data;
  },

  async refine(sessionId: string, instruction: string, targetSlide: number): Promise<{ delta: Delta; new_generation: Generation }> {
    const res = await fetch(`/api/sessions/${sessionId}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ change_instruction: instruction, target_slide: targetSlide }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Refinement failed (${res.status})`);
    }
    return (await res.json()).data;
  },
};

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  // Paper state
  const [paperId, setPaperId] = useState<string | null>(null);
  const [paperName, setPaperName] = useState('');
  const [paperStatus, setPaperStatus] = useState<'idle' | 'uploading' | 'processing' | 'ready' | 'error'>('idle');
  const [paperError, setPaperError] = useState('');
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [isPresentation, setIsPresentation] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentGeneration, setCurrentGeneration] = useState<Generation | null>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Controls
  const [audience, setAudience] = useState('Policymakers');
  const [length, setLength] = useState('90 seconds');

  // Provenance panel
  const [openChunkId, setOpenChunkId] = useState<string | null>(null);
  const openChunk = chunks.find(c => c.chunk_id === openChunkId) ?? null;

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // ── File upload ─────────────────────────────────────────────────────────────
  const handleFile = useCallback(async (file: File) => {
    if (file.size > 50 * 1024 * 1024) {
      setPaperStatus('error');
      setPaperError('File size exceeds 50 MB limit.');
      return;
    }
    if (file.type !== 'application/pdf' && !file.name.match(/\.(tex|latex)$/i)) {
      setPaperStatus('error');
      setPaperError('Unsupported format. Please upload a PDF or .tex file.');
      return;
    }
    setPaperName(file.name);
    setPaperStatus('uploading');
    setPaperError('');
    setChunks([]);
    setMessages([]);
    setCurrentGeneration(null);
    setSessionId(null);
    setPaperId(null);
    setIsPresentation(false);

    try {
      const pid = await api.uploadPaper(file);
      setPaperId(pid);
      setPaperStatus('processing');
      pollStatus(pid);
    } catch (err: any) {
      setPaperStatus('error');
      setPaperError(err.message);
    }
  }, []);

  const pollStatus = (pid: string) => {
    const interval = setInterval(async () => {
      try {
        const data = await api.getPaperStatus(pid);
        if (data.status === 'ready') {
          clearInterval(interval);
          setPaperStatus('ready');
          setIsPresentation(data.is_presentation || false);
          const c = await api.getChunks(pid);
          setChunks(c);
          // Auto-create session
          const sid = await api.createSession(pid);
          setSessionId(sid);
        } else if (data.status === 'failed') {
          clearInterval(interval);
          setPaperStatus('error');
          setPaperError(data.error_msg || 'Ingestion failed');
        }
      } catch { /* retry on transient network error */ }
    }, 2500);
  };

  // ── Generate ────────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!sessionId || !paperId) return;
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: `Generate a ${length} script for ${audience}` };
    setMessages(m => [...m, userMsg]);
    setIsLoading(true);
    setChatError('');
    try {
      const { generation } = await api.generate(sessionId, paperId, audience, length);
      setCurrentGeneration(generation);
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        generation,
      };
      setMessages(m => [...m, assistantMsg]);
    } catch (err: any) {
      setChatError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Refine ──────────────────────────────────────────────────────────────────
  const handleSend = async () => {
    if (!input.trim() || isLoading || !sessionId) return;
    const instruction = input.trim();

    // Parse target slide from instruction, default to 1
    const slideMatch = instruction.match(/slide\s+(\d+)/i);
    const targetSlide = slideMatch ? parseInt(slideMatch[1]) : 1;

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: instruction };
    setMessages(m => [...m, userMsg]);
    setInput('');
    setIsLoading(true);
    setChatError('');

    try {
      const { delta, new_generation } = await api.refine(sessionId, instruction, targetSlide);
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Here's my suggested revision for Slide ${targetSlide}:`,
        delta,
        generation: new_generation,
      };
      setMessages(m => [...m, assistantMsg]);
    } catch (err: any) {
      setChatError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcceptDelta = (msgId: string, gen: Generation) => {
    setCurrentGeneration(gen);
    setMessages(m => [
      ...m.map(msg => msg.id === msgId ? { ...msg, accepted: true } : msg),
      { id: crypto.randomUUID(), role: 'assistant', generation: gen }
    ]);
  };

  const handleRejectDelta = (msgId: string) => {
    setMessages(m => m.map(msg => msg.id === msgId ? { ...msg, rejected: true } : msg));
  };

  const handleCopySlide = (slide: Slide) => {
    let text = slide.title ? `${slide.title}\n\n` : '';
    if (slide.sentences) {
      text += slide.sentences.map(s => s.text).join(' ');
    } else if (slide.script) {
      text += slide.script;
    }
    navigator.clipboard.writeText(text.trim());
  };

  const mathCount = chunks.filter(c => c.contains_math).length;
  const figCount = chunks.filter(c => c.has_figure).length;

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="app-shell">
      {/* Top Bar */}
      <header className="topbar">
        <div className="topbar-brand">
          <img src="/favicon.png" alt="SARAL Logo" className="brand-logo" />
          <div className="brand-text">SARAL <span>Chatbot</span></div>
        </div>
        <div className="topbar-meta">
          {paperStatus === 'ready' && paperId && (
            <div className="paper-badge">
              <span className="ready-dot" />
              {paperName}
            </div>
          )}
          <span>Science Accessible for All</span>
        </div>
      </header>

      <div className="main-content">
        {/* Left Sidebar */}
        <aside className="sidebar">
          {/* Upload */}
          <div className="sidebar-section">
            <h3>1. Upload Paper</h3>
            {paperStatus === 'idle' || paperStatus === 'error' ? (
              <>
                <div
                  className={`upload-zone${isDragging ? ' dragging' : ''}`}
                  onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={e => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); }}
                  onClick={() => fileInputRef.current?.click()}
                  data-testid="drop-zone"
                >
                  <div className="upload-icon">📎</div>
                  <p>Drop your <span>PDF</span> or <span>.tex</span> here<br />or click to browse</p>
                  <p style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>Max 50 MB</p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.tex,.latex"
                  className="sr-only"
                  data-testid="file-input"
                  onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
                {paperStatus === 'error' && <div className="error-banner" data-testid="error-message">{paperError}</div>}
              </>
            ) : (
              <div className="status-card">
                <div className="filename" title={paperName}>{paperName}</div>
                <div className="status-row">
                  <div className={`status-dot ${paperStatus}`} />
                  <span>
                    {paperStatus === 'uploading' && 'Uploading...'}
                    {paperStatus === 'processing' && 'Extracting text & math...'}
                    {paperStatus === 'ready' && `Ready - ${chunks.length} chunks`}
                  </span>
                </div>
                {paperStatus === 'ready' && (
                  <div className="chunk-stats">
                    <span className="chunk-stat">{chunks.length} chunks</span>
                    <span className="chunk-stat">{mathCount} math</span>
                    {!isPresentation && <span className="chunk-stat">{figCount} figs</span>}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Generate Controls */}
          <div className="sidebar-section">
            <h3>2. Configure Output</h3>
            <div className="control-group">
              <label>Audience</label>
              <select
                className="control-select"
                value={audience}
                onChange={e => setAudience(e.target.value)}
                disabled={paperStatus !== 'ready'}
              >
                <option>Policymakers</option>
                <option>High School Students</option>
                <option>General Public</option>
                <option>Domain Experts</option>
              </select>
            </div>
            <div className="control-group">
              <label>Length</label>
              <select
                className="control-select"
                value={length}
                onChange={e => setLength(e.target.value)}
                disabled={paperStatus !== 'ready'}
              >
                <option>30 seconds</option>
                <option>60 seconds</option>
                <option>90 seconds</option>
                <option>5 minutes</option>
              </select>
            </div>
            <button
              className="btn-generate"
              disabled={paperStatus !== 'ready' || isLoading}
              onClick={handleGenerate}
            >
              {isLoading ? 'Generating...' : 'Generate Script'}
            </button>
          </div>

          {/* Current Script Summary */}
          {currentGeneration && (
            <div className="sidebar-section">
              <h3>Current Version</h3>
              <div className="status-card">
                <div className="status-row" style={{ marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {currentGeneration.slides.length} slides · {currentGeneration.audience}
                  </span>
                </div>
                <div className="cov-bar">
                  <span title="Percentage of generated sentences backed by citations. This measures how 'hallucination-free' the script is, not how much of the original document was covered.">Grounding Score ⓘ</span>
                  <div className="cov-track">
                    <div className="cov-fill" style={{ width: `${Math.round(currentGeneration.citation_coverage * 100)}%` }} />
                  </div>
                  <span>{Math.round(currentGeneration.citation_coverage * 100)}%</span>
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* Chat Area */}
        <main className="chat-area">
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🧠</div>
                <h2>SARAL Chatbot</h2>
                <p>Transform complex research papers into clear, audience-targeted scripts with verifiable citations.</p>
                <div className="step-list">
                  <div className="step-item"><div className="step-num">1</div>Upload a PDF or LaTeX paper on the left</div>
                  <div className="step-item"><div className="step-num">2</div>Choose your audience and length</div>
                  <div className="step-item"><div className="step-num">3</div>Click Generate Script</div>
                  <div className="step-item"><div className="step-num">4</div>Refine with natural language instructions</div>
                </div>
              </div>
            ) : (
              messages.map(msg => (
                <div key={msg.id} className={`message-row ${msg.role}`}>
                  {msg.role === 'user' ? (
                    <div className="bubble user">{msg.content}</div>
                  ) : (
                    <div className="bubble assistant">
                      {/* Delta view */}
                      {msg.delta && !msg.accepted && !msg.rejected && (
                        <>
                          {msg.content && <p style={{ marginBottom: 10, color: 'var(--text-secondary)', fontSize: 13 }}>{msg.content}</p>}
                          <div className="delta-card">
                            <div className="delta-header">
                              <h4>Suggested revision - Slide {msg.delta.slide_number}</h4>
                              <div className="delta-actions">
                                <button className="btn-reject" onClick={() => handleRejectDelta(msg.id)}>Reject</button>
                                <button className="btn-accept" onClick={() => handleAcceptDelta(msg.id, msg.generation!)}>Accept</button>
                              </div>
                            </div>
                            <div className="delta-body">
                              {msg.delta.diff_hunks.map((h, i) => {
                                if (h.operation === 'insert') return <span key={i} className="diff-insert">{h.text} </span>;
                                if (h.operation === 'delete') return <span key={i} className="diff-delete">{h.text} </span>;
                                return <span key={i}>{h.text} </span>;
                              })}
                            </div>
                            <div className="delta-reason">💡 {msg.delta.reason}</div>
                          </div>
                        </>
                      )}

                      {/* Accepted/Rejected state */}
                      {msg.delta && msg.accepted && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--accent)' }}>
                          Revision accepted and applied to version history.
                        </div>
                      )}
                      {msg.delta && msg.rejected && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)' }}>
                          Revision rejected. Current version unchanged.
                        </div>
                      )}

                      {/* Generated slides */}
                      {msg.generation && !msg.delta && (
                        <>
                          {msg.generation.low_confidence && (
                            <div className="low-confidence-badge">
                              ⚠️ Low citation confidence - some claims may not be grounded in the paper
                            </div>
                          )}
                          <div className="cov-bar">
                            <span title="Percentage of generated sentences backed by citations. This measures how 'hallucination-free' the script is, not how much of the original document was covered.">Grounding Score ⓘ</span>
                            <div className="cov-track">
                              <div className="cov-fill" style={{ width: `${Math.round(msg.generation.citation_coverage * 100)}%` }} />
                            </div>
                            <span style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(msg.generation.citation_coverage * 100)}%</span>
                          </div>
                          {msg.generation.slides.map(slide => (
                            <div key={slide.slide_number} className="slide-card">
                              <div className="slide-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span>Slide {slide.slide_number}</span>
                                <button
                                  className="btn-copy"
                                  onClick={() => handleCopySlide(slide)}
                                  title="Copy slide script"
                                >
                                  📋 Copy
                                </button>
                              </div>
                              {slide.title && <div className="slide-title">{slide.title}</div>}
                              <div className="slide-script">
                                {slide.sentences && slide.sentences.length > 0 ? slide.sentences.map((s, si) => (
                                  <React.Fragment key={si}>
                                    {s.text}
                                    {s.source_ids?.map((cid, ci) => (
                                      <button
                                        key={ci}
                                        className="cite-badge"
                                        onClick={() => setOpenChunkId(cid)}
                                        title={`Source chunk: ${cid}`}
                                        data-testid={`badge-${cid}`}
                                      >
                                        {ci + 1}
                                      </button>
                                    ))}
                                    {' '}
                                  </React.Fragment>
                                )) : slide.script}
                              </div>
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}

            {isLoading && (
              <div className="message-row assistant">
                <div className="thinking-bubble">
                  <div className="dots">
                    <span /><span /><span />
                  </div>
                  Thinking...
                </div>
              </div>
            )}

            {chatError && (
              <div className="error-banner" style={{ margin: '0 0 12px 0' }}>⚠️ {chatError}</div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="chat-input-bar">
            <div className="chat-input-row">
              <textarea
                className="chat-input"
                rows={1}
                placeholder={
                  !sessionId
                    ? 'Upload a paper to get started…'
                    : !currentGeneration
                      ? 'Click "Generate Script" to begin, then refine here…'
                      : 'Refine: "Make slide 2 less technical" or "Add an analogy about cars to slide 1"…'
                }
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                disabled={isLoading || !currentGeneration}
                data-testid="chat-input"
              />
              <button
                className="btn-send"
                onClick={handleSend}
                disabled={!input.trim() || isLoading || !currentGeneration}
                title="Send"
              >
                ↑
              </button>
            </div>
            <p className="chat-hint">Press Enter to send · Shift+Enter for newline · Click ¹ badges to see source chunks</p>
          </div>
        </main>
      </div>

      {/* Provenance Panel */}
      <div className="provenance-overlay">
        <div className={`provenance-panel${openChunk ? ' open' : ''}`} data-testid="provenance-panel">
          <div className="provenance-header">
            <h3>📍 Source Highlight</h3>
            <button className="btn-close" onClick={() => setOpenChunkId(null)} data-testid="close-btn">✕</button>
          </div>
          {openChunk && (
            <>
              <div className="provenance-meta">
                <span>Page {openChunk.page_number}</span>
                {openChunk.section_title && <span>§ {openChunk.section_title}</span>}
              </div>
              <div className="provenance-body">
                <div className="chunk-text-box">{openChunk.text}</div>
                {openChunk.contains_math && (
                  <div className="math-badge">∑ Contains mathematical notation</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
