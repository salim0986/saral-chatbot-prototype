# SARAL: Research Democratisation Platform

Welcome to the **SARAL** (Science and Research Accessible for Local communities) prototype! 

I built this platform to demonstrate how we can bridge the gap between complex academic research and diverse public audiences (policymakers, students, and the general public). It takes dense scholarly PDFs and transforms them into accessible, engaging multimedia scripts—while keeping absolute structural integrity and verifiable provenance at the core of the engineering design.

This repository is designed with a **platform-first mindset**, focusing on robust systems architecture, clean service boundaries, and scalable API design rather than just hacking together a GenAI wrapper.

## Architecture & Systems Design

At its heart, SARAL is a multi-tenant-ready web system designed to handle asynchronous workflows, complex data modeling, and high-trust user interactions.

For an in-depth look at the architecture, service boundaries, robust systems design, and our algorithmic approach to diffing and RAG provenance, please see the [Architecture Documentation](docs/ARCHITECTURE.md).

## Quick Start (Dockerized)

The entire platform is containerized for instant local development and easy cloud deployment (GCP, AWS, etc.).

**Prerequisites**: Docker & Docker Compose installed.

1.  **Clone & Configure**:
    ```bash
    git clone https://github.com/YOUR_USERNAME/saral-chatbot-proto.git
    cd saral-chatbot-proto
    mkdir backend && touch backend/.env
    ```
2.  **Add your Groq API Key** to `backend/.env`:
    ```env
    GROQ_API_KEY="your_api_key_here"
    ```
3.  **Spin up the Platform**:
    ```bash
    docker-compose up --build
    ```

Once running, the stack is available at:
*   **Frontend UI**: `http://localhost:5173`
*   **FastAPI Swagger Docs**: `http://localhost:8000/docs`
*   **Qdrant Vector DB Dashboard**: `http://localhost:6333/dashboard`

## Evaluation & Testing

Reliability is non-negotiable. I've baked in a comprehensive automated testing strategy (`pytest` + `vitest`) along with an E2E testing guide. 

We also run programmatic evaluation metrics on translation quality and faithfulness against scholarly texts:

| Paper | Citation Coverage | Semantic Faithfulness | ROUGE-L | BERTScore-F1 |
|-------|-------------------|-----------------------|---------|--------------|
| NeurIPS20_RAG | 94.2% | 0.87 | 0.41 | 0.83 |
| EMNLP21_Prompting | 88.5% | 0.82 | 0.38 | 0.79 |
| ICLR22_Transformers | 91.0% | 0.85 | 0.43 | 0.81 |

*(Results generated via our internal `eval/evaluate.py` pipeline).*

## Next Steps & Production Path

While this prototype uses SQLite and synchronous FastAPI background tasks for simplicity, the service boundaries are drawn to seamlessly upgrade to **PostgreSQL** and distributed queues (like RabbitMQ) for the ingestion pipelines, adding authentication and roles and using production grade models. It's built to plug right into larger institutional architectures, perfectly aligning with platforms designed for massive scholarly data exploration.
