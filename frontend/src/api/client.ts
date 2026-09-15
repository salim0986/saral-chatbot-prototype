export interface Chunk {
  chunk_id: string;
  page_number: number;
  section_title: string;
  block_index: number;
  text: string;
  contains_math: boolean;
  has_figure: boolean;
  figure_caption: string | null;
}

export interface PaperStatusResponse {
  status: string;
  data: {
    paper_id: string;
    filename: string;
    status: 'processing' | 'ready' | 'failed';
    error: string | null;
  };
}

export interface PaperChunksResponse {
  status: string;
  data: {
    paper_id: string;
    total: number;
    page: number;
    page_size: number;
    chunks: Chunk[];
  };
}

export interface GenerationOutput {
  output_type: string;
  audience: string;
  length: string;
  slides: any[];
  citation_coverage: number;
  low_confidence: boolean;
}

export const apiClient = {
  async uploadPaper(file: File): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch('/api/papers', {
      method: 'POST',
      body: formData
    });
    
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }
    const data = await res.json();
    return data.data.paper_id;
  },

  async getPaperStatus(paperId: string): Promise<PaperStatusResponse> {
    const res = await fetch(`/api/papers/${paperId}`);
    if (!res.ok) throw new Error('Status fetch failed');
    return res.json();
  },

  async getPaperChunks(paperId: string): Promise<PaperChunksResponse> {
    const res = await fetch(`/api/papers/${paperId}/chunks`);
    if (!res.ok) throw new Error('Chunks fetch failed');
    return res.json();
  }
};
