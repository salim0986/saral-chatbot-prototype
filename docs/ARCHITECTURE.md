# Architecture & Systems Design

At its heart, SARAL is a multi-tenant-ready web system designed to handle asynchronous workflows, complex data modeling, and high-trust user interactions.

```mermaid
graph TD
    A[React/Vite Frontend] -->|Upload & Config| B[FastAPI Backend Core]
    B -->|Async Ingestion| C[PyMuPDF4LLM Parser]
    C -->|Semantic Chunks| D[BGE-M3 Embeddings]
    D --> E[(Qdrant Vector DB)]
    
    A -->|Generate/Refine requests| B
    B -->|Dynamic threshold RAG| E
    E -->|Context + Provenance| B
    B -->|Strict Schema Prompting| F[Groq API / LLM]
    F -->|Validated JSON| B
    
    B -->|Algorithmic Diffing| G[difflib tracking]
    G --> H[(SQLite / Persistence Layer)]
    B -->|Responses & Grounding| A
```

## Key Engineering Pillars

*   **Robust Service Boundaries**: The backend is decoupled into distinct services (`IngestionService`, `RAGService`, `GenerationService`, `ChangeTrackingService`). This makes it trivial to swap out underlying technologies (like swapping Docling for PyMuPDF4LLM, or moving from SQLite to PostgreSQL) as the platform scales.
*   **Trust & Provenance (Grounding)**: In the public sector, hallucinations are unacceptable. The `GenerationService` strictly enforces citation grounding. The frontend maps these `source_ids` to clickable badges, allowing users to verify every single generated claim directly against the original paper's chunks.
*   **Algorithmic Change Tracking**: Instead of relying on LLMs to self-report diffs (which is highly prone to hallucination), our `ChangeTrackingService` strictly manages slide revisions by computing exact word-level diffs on the server-side using standard algorithmic tools. The LLM only handles the text transformation.
*   **Scalable API Design**: Built with Python & **FastAPI**, featuring async workflows for document ingestion and generation, preparing the ground for queue-based processing (e.g., Celery) in production.
*   **Modern Frontend Experience**: A responsive, fast UI built in **React** and **Vite**, tailored for multiple personas (researchers, reviewers, public) to effortlessly explore output and seamlessly manage iterative refinements.
