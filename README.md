# SENTRA — Intelligent Document Processing & PO Generation

## Overview

SENTRA is a production-ready async FastAPI service that handles the complete pipeline:  
**PDF Upload → Image Conversion → Vision LLM Extraction → Embedding Creation → Weaviate Storage**

The service runs on **port 7861** and is designed for Ubuntu.

---

## Setup

### 1. Prerequisites

- Ubuntu 20.04+
- Python 3.10+
- AWS account with Bedrock access (Claude 3.7 Sonnet enabled)
- OpenAI API key (for `text-embedding-3-small`)

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your AWS credentials
```

### 3. Run Setup Script

```bash
bash setup.sh
```

This will:
- Install `poppler-utils` (PDF rendering)
- Create a Python virtual environment
- Install all Python dependencies

### 4. Start the Server

```bash
bash run.sh
```

The API will be available at `http://localhost:7861`

---

## API Endpoints

### `POST /upload`

Upload one or multiple PDFs for processing.

**Form fields:**
- `files` — one or more PDF files (multipart)
- `pdf_type` — `selection_sheet` or `take_off`

**Example:**
```bash
curl -X POST http://localhost:7861/upload \
  -F "files=@selection_sheet.pdf" \
  -F "pdf_type=selection_sheet"
```

**Response:**
```json
{
  "job_id": "uuid-...",
  "status": "processing",
  "files": ["selection_sheet.pdf"],
  "message": "Processing started"
}
```

### `GET /status/{job_id}`

Check the processing status of an upload job.

### `GET /health`

Health check endpoint.

### `GET /collections/stats`

Returns the number of objects in each Weaviate collection.

---

## Folder Structure

```
SENTRA/
├── .env                         # Environment variables (AWS keys, model config)
├── .env.example                 # Example env file (no secrets)
├── .gitignore
├── requirements.txt
├── setup.sh                     # Ubuntu setup script
├── run.sh                       # Start the FastAPI server
├── README.md
├── app/
│   ├── main.py                  # FastAPI app, port 7861
│   ├── config.py                # Settings from .env
│   ├── routers/
│   │   └── upload.py            # Upload & status endpoints
│   ├── services/
│   │   ├── pdf_processor.py     # pdf2image conversion (async)
│   │   ├── extractor.py         # Claude 3.7 Vision extraction (async parallel)
│   │   ├── embedder.py          # text-embedding-3-small via LiteLLM (async parallel)
│   │   └── weaviate_store.py    # Embedded Weaviate client & storage
│   └── utils/
│       └── helpers.py           # JSON flattening, lot/community detection
└── sentra-demo/                 # Created at runtime
    ├── uploads/
    ├── output_images/
    └── extracted_data/
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION_NAME` | AWS region (default: `us-east-1`) |
| `BEDROCK_MODEL` | Claude model ID via Bedrock |
| `OPENAI_API_KEY` | OpenAI API key (for `text-embedding-3-small`) |
| `EMBED_MODEL` | Embedding model ID (default: `text-embedding-3-small`) |
| `EMBED_DIMENSIONS` | Embedding dimensions (default: `1536`) |
| `MAX_CONCURRENT_EXTRACTIONS` | Max parallel LLM extraction calls |
| `MAX_CONCURRENT_EMBEDDINGS` | Max parallel embedding calls |
| `SERVER_PORT` | Server port (default: `7861`) |

---

## PDF Types

- **`selection_sheet`** — extracts lot info, purchaser details, sale info, selected options, categories
- **`take_off`** — extracts keys/legends, column headers, all rows with measurements, REPLACES logic, color coding
