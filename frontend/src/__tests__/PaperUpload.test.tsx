import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PaperUpload } from '../components/PaperUpload';
import { apiClient } from '../api/client';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  apiClient: {
    uploadPaper: vi.fn(),
    getPaperStatus: vi.fn(),
    getPaperChunks: vi.fn(),
  }
}));

describe('PaperUpload Component', () => {
  const mockOnReady = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders drop zone initially', () => {
    render(<PaperUpload onPaperReady={mockOnReady} />);
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument();
  });

  it('shows error for unsupported file type', async () => {
    render(<PaperUpload onPaperReady={mockOnReady} />);
    const file = new File(['hello'], 'hello.png', { type: 'image/png' });
    const input = screen.getByTestId('file-input');
    
    fireEvent.change(input, { target: { files: [file] } });
    
    expect(screen.getByTestId('error-message')).toHaveTextContent('Unsupported file format. Please upload PDF or .tex.');
  });

  it('shows error for file > 50MB', async () => {
    render(<PaperUpload onPaperReady={mockOnReady} />);
    // Create a dummy file with large size
    const file = new File([''], 'big.pdf', { type: 'application/pdf' });
    Object.defineProperty(file, 'size', { value: 51 * 1024 * 1024 }); // 51MB
    
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });
    
    expect(screen.getByTestId('error-message')).toHaveTextContent('File size exceeds 50MB limit.');
  });

  it('uploads valid PDF and goes to processing status', async () => {
    vi.mocked(apiClient.uploadPaper).mockResolvedValue('paper_123');
    vi.mocked(apiClient.getPaperStatus).mockResolvedValue({ status: 'success', data: { paper_id: '123', filename: 't', status: 'processing', error: null } });

    render(<PaperUpload onPaperReady={mockOnReady} />);
    
    const file = new File(['dummy content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('processing-status')).toBeInTheDocument();
    });
  });
});
