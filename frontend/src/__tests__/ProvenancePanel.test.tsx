import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ProvenancePanel } from '../components/ProvenancePanel';
import { apiClient } from '../api/client';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  apiClient: {
    getPaperChunks: vi.fn(),
  }
}));

describe('ProvenancePanel Component', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders null if chunkId is null', () => {
    const { container } = render(
      <ProvenancePanel paperId="p1" chunkId={null} onClose={mockOnClose} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('fetches and displays chunk data', async () => {
    vi.mocked(apiClient.getPaperChunks).mockResolvedValue({
      status: 'success',
      data: {
        paper_id: 'p1', total: 1, page: 1, page_size: 20,
        chunks: [
          { 
            chunk_id: 'c1', 
            text: 'This is the source text.',
            page_number: 5,
            section_title: 'Introduction',
            contains_math: true,
            has_figure: false,
            block_index: 0,
            figure_caption: null
          }
        ]
      }
    });

    render(<ProvenancePanel paperId="p1" chunkId="c1" onClose={mockOnClose} />);
    
    // Initially shows loading
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();

    // Wait for data to load
    await waitFor(() => {
      expect(screen.queryByTestId('loading-state')).not.toBeInTheDocument();
    });

    expect(screen.getByText('This is the source text.')).toBeInTheDocument();
    expect(screen.getByText('Introduction • Page 5')).toBeInTheDocument();
    expect(screen.getByText('Math-heavy')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', async () => {
    vi.mocked(apiClient.getPaperChunks).mockResolvedValue({
      status: 'success',
      data: { paper_id: 'p1', total: 0, page: 1, page_size: 20, chunks: [] }
    });

    render(<ProvenancePanel paperId="p1" chunkId="c1" onClose={mockOnClose} />);
    
    const closeBtn = screen.getByTestId('close-btn');
    fireEvent.click(closeBtn);
    expect(mockOnClose).toHaveBeenCalled();
  });
});
