# 🏗️ Complete System Architecture — PDF to Purchase Order Generation

## End-to-End Intelligent Document Processing & PO Generation System

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Tech Stack](#tech-stack)
3. [Phase 1: PDF Upload & Image Conversion](#phase-1-pdf-upload--image-conversion)
4. [Phase 2: Data Extraction using Vision LLM](#phase-2-data-extraction-using-vision-llm)
5. [Phase 3: Text Embedding Creation](#phase-3-text-embedding-creation)
6. [Phase 4: Storing in Weaviate](#phase-4-storing-in-weaviate)
7. [Phase 5: Chat & Query Service](#phase-5-chat--query-service)
8. [Phase 6: Purchase Order Generation Workflow](#phase-6-purchase-order-generation-workflow)
9. [Phase 7: SAP Code Lookup from PostgreSQL](#phase-7-sap-code-lookup-from-postgresql)
10. [Phase 8: LLM Gateway — LiteLLM Proxy](#phase-8-llm-gateway--litellm-proxy)
11. [Phase 9: Observability](#phase-9-observability)
12. [Complete Architecture Diagram](#complete-architecture-diagram)
13. [Data Flow Summary](#data-flow-summary)
14. [Python Libraries Required](#python-libraries-required)
15. [Cost Estimation](#cost-estimation)

---

## System Overview

This system enables users to:

- **Upload two PDFs** simultaneously — a **Selection Sheet** and a **Take Off Sheet**
- **Chat with the PDFs** — ask any question about lot information, purchaser details, selected options, materials, quantities, etc.
- **Generate Purchase Orders** — cross-reference both PDFs with SAP master data in PostgreSQL to produce a structured PO with SAP material codes, quantities, UOM, and material types

### Input PDFs

| PDF | What It Contains | Purpose |
|-----|-----------------|---------|
| **Selection Sheet** | Lot info, purchaser, sale info, selected options (FSA, ELA, MAS, etc.) | Tells the system **WHAT was selected** for the lot |
| **Take Off Sheet** | Trades, rooms, material measurements, quantities, replacement logic | Tells the system **WHAT MATERIALS and HOW MUCH** is needed |

### Output

| Output Type | Format |
|------------|--------|
| **Chat Answers** | Natural language responses about PDF content |
| **Purchase Order** | Structured table with Trade, SAP Material, Qty, UOM, Material Description, Type of Material |

---

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| **LLM (Vision + Chat + PO)** | Claude 3.7 Sonnet | Vision extraction, chat Q&A, replacement logic, PO generation |
| **Text Embedding Model** | text-embedding-3-small (OpenAI) | Converts extracted text into 1536-dimensional vectors |
| **Vector + BM25 Database** | Weaviate | Stores embeddings + text + metadata, supports hybrid search |
| **SAP Code Database** | PostgreSQL | Stores SAP master data (material codes, vendors, prices, types) |
| **Workflow Orchestration** | LangGraph + LangChain | Multi-step PO generation workflow + tool management |
| **LLM Gateway** | LiteLLM Proxy (Separate Service) | Model routing, cost tracking, API key management |
| **PDF to Image** | pdf2image (poppler) | Converts PDF pages to high-resolution images |
| **Observability** | Langfuse / LangSmith | Tracing, debugging, evaluation, monitoring |
| **Frontend** | Streamlit / React | Chat interface, PDF upload, PO display |

---

## Phase 1: PDF Upload & Image Conversion

### What Happens

User uploads two PDFs through the frontend. The system converts each page of each PDF into a high-resolution image for Vision LLM processing.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Library** | `pdf2image` | Python library that wraps `poppler-utils` |
| **Backend** | Poppler | Open-source PDF rendering engine |
| **DPI** | 300 | Sweet spot — clear enough for tables, not wasteful on tokens |
| **Output Format** | PNG | Lossless, preserves text clarity in tables |

### Flow

```
User uploads 2 PDFs
    │
    ├── Selection Sheet PDF (8 pages)
    │     → pdf2image (300 DPI)
    │     → 8 PNG images (page_1.png ... page_8.png)
    │
    └── Take Off Sheet PDF (10-12 pages)
          → pdf2image (300 DPI)
          → 10-12 PNG images (page_1.png ... page_12.png)

System assigns:
    → lot_code (e.g., "E003")
    → upload_batch_id (e.g., "batch_001")
    → Links both PDFs together via these identifiers
```

### Why pdf2image?

- Simple, reliable, well-maintained
- 300 DPI produces clear images that Vision LLMs can read accurately
- Handles multi-page PDFs natively
- Each page becomes a separate image — perfect for page-wise processing

---

## Phase 2: Data Extraction using Vision LLM

### What Happens

Each page image is sent to Claude 3.7 Sonnet's Vision capability. The LLM "reads" the image and extracts all structured data into JSON format.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **LLM** | Claude 3.7 Sonnet (Vision) | Excellent at reading complex tables with colors, merged cells |
| **Called via** | LiteLLM Proxy | All LLM calls go through the proxy for cost tracking |
| **Detail Level** | High | Necessary for table-heavy PDFs with small text |
| **Temperature** | 0 | Deterministic output for consistent extraction |
| **Output Format** | Structured JSON | Forced via prompt engineering |

### What Gets Extracted

#### From Selection Sheet (per page):

```json
{
  "sections": [
    {
      "section_name": "LOT INFORMATION",
      "type": "key_value",
      "data": {
        "Community": "MEADOWS AT MANSFIELD",
        "Code": "MA",
        "Lot": "E003",
        "Address": "7 REDWOOD RUN, PORT MURRAY, NJ 07865"
      }
    },
    {
      "section_name": "SALE INFORMATION",
      "type": "table",
      "data": [
        {
          "Purchaser Name": "Justina Sutherland",
          "CDS #": "ND0193",
          "Sale Status": "Contingent",
          "Contract Date": "2/20/2023",
          "Sales Rep": "Patricia Ernst",
          "Project Manager": "Nicholas Wilbur"
        }
      ]
    },
    {
      "section_name": "SELECTED OPTIONS | SLAB FOUNDATION",
      "type": "table",
      "data": [
        {
          "Option": "FSA",
          "Description": "SLAB FOUNDATION",
          "Category": "E"
        }
      ]
    }
  ]
}
```

#### From Take Off Sheet (per page):

```json
{
  "keys": {
    "subfloor_key": "Slab-Concrete=S / Plywood=W",
    "base_house_key": "Base=B / Elevation or Optional Room=O"
  },
  "section": "base_house",
  "rows": [
    {
      "id": 315,
      "base_house_info": "Has Angles",
      "option_code": null,
      "area_room_name": "GREAT ROOM",
      "std_material": "C",
      "base_opt_elev": "B",
      "subfloor": "W",
      "floor_level": 1,
      "material_width": 12.00,
      "cut_length": 30.75,
      "sq_yds": 41.00,
      "pad_sq_yds": 37,
      "wood_tile_sq_ft": 338,
      "shoe_base_lf": 57,
      "notes": null
    },
    {
      "id": 316,
      "base_house_info": "Has Angles",
      "option_code": "MAS",
      "area_room_name": "GREAT ROOM WITH STUDY (MAS) OPT",
      "std_material": "C",
      "base_opt_elev": "O",
      "subfloor": "W",
      "floor_level": 1,
      "material_width": 12.00,
      "cut_length": 30.75,
      "sq_yds": 41.00,
      "pad_sq_yds": 37,
      "wood_tile_sq_ft": 338,
      "shoe_base_lf": 55,
      "notes": "REPLACES GREAT ROOM"
    }
  ]
}
```

### Why Claude 3.7 Sonnet for Vision?

- Handles complex multi-section tables with colored headers
- Reads merged cells accurately
- Understands conditional notes like "REPLACES GREAT ROOM"
- Preserves column-to-value alignment in dense tables
- Supports high-detail image processing

---

## Phase 3: Text Embedding Creation

### What Happens

The extracted text from each page is converted into a 1536-dimensional numerical vector (embedding) that captures the semantic meaning of the content.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Embedding Model** | text-embedding-3-small (OpenAI) | 1536 dimensions, 8191 token context |
| **Called via** | LiteLLM Proxy | Cost tracked alongside all other LLM calls |
| **Embedding Level** | Page-wise | One embedding per page |

### What Are Dimensions?

When text is passed through the embedding model, it returns a list of 1536 numbers:

```
"SLAB FOUNDATION, FSA, Category E" → [0.0123, -0.0456, 0.0789, ... 1536 numbers]
```

These numbers represent the **semantic meaning** of the text in mathematical space. Similar texts produce similar vectors, enabling semantic search.

### Why text-embedding-3-small?

- Best price-to-performance ratio
- 1536 dimensions — rich enough for structured table data
- 8191 token context — handles full page content easily
- Claude does not have its own embedding model — OpenAI's is the industry standard

### Why Not Claude for Embeddings?

Anthropic (Claude) does not offer a text embedding model. For embeddings, OpenAI's `text-embedding-3-small` is the best choice. Both Claude (for LLM) and OpenAI (for embeddings) are routed through the same LiteLLM Proxy.

---

## Phase 4: Storing in Weaviate

### What Happens

The extracted text, embedding vectors, and rich metadata are stored in Weaviate. Two separate collections are created — one for selection sheets and one for take off sheets.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Database** | Weaviate | Vector + BM25 hybrid database |
| **Library (Ingestion)** | `weaviate-python-client` (Direct SDK) | Full control over schema, batch insert, metadata |
| **Library (Retrieval)** | `langchain-weaviate` (LangChain Retriever) | Clean integration with LangGraph workflow nodes |
| **Search Capabilities** | BM25 + Vector + Hybrid | Configurable alpha for precision vs semantic balance |

### Why Two Libraries?

| Phase | Library | Why |
|-------|---------|-----|
| **Ingestion (PDF Upload)** | Weaviate Python Client (Direct SDK) | Need full control — create collections, define schema, batch upload, configure metadata |
| **Retrieval (Chat + PO)** | LangChain Weaviate Retriever | Clean plug-in for LangGraph workflow nodes, built-in hybrid search |

### Collection: selection_sheets

| Field | Type | Example |
|-------|------|---------|
| `text` | string | Flattened extracted content from the page |
| `vector` | float[1536] | Embedding from text-embedding-3-small |
| `pdf_type` | metadata | "selection_sheet" |
| `pdf_name` | metadata | "selection_sheet_E003.pdf" |
| `lot_code` | metadata | "E003" |
| `community` | metadata | "MEADOWS AT MANSFIELD" |
| `page_number` | metadata | 1, 2, 3, ... |
| `upload_batch_id` | metadata | "batch_001" |
| `extracted_at` | metadata | "2026-03-02T14:30:00" |

### Collection: take_offs

| Field | Type | Example |
|-------|------|---------|
| `text` | string | Flattened extracted content from the page |
| `vector` | float[1536] | Embedding from text-embedding-3-small |
| `pdf_type` | metadata | "take_off" |
| `pdf_name` | metadata | "takeoff_E003.pdf" |
| `lot_code` | metadata | "E003" |
| `section` | metadata | "base_house" or "options" |
| `page_number` | metadata | 1, 2, 3, ... |
| `upload_batch_id` | metadata | "batch_001" |
| `replaces` | metadata | "GREAT ROOM" (if option row) |
| `extracted_at` | metadata | "2026-03-02T14:30:00" |

### Hybrid Search — BM25 + Vector

Weaviate supports **hybrid search** with a configurable `alpha` parameter:

| Alpha Value | Behavior | Used For |
|-------------|----------|----------|
| `0.0` | Pure BM25 (exact keyword match) | Searching exact item codes like "FSA", "MAS" |
| `0.1 - 0.3` | BM25 dominant | PO generation — precision matters |
| `0.5` | Equal blend | General questions |
| `0.7 - 1.0` | Vector dominant | Natural language questions like "any foundation options?" |

### Why Weaviate?

- **Native BM25** — critical for exact keyword matching during PO generation
- **Native vector search** — for semantic/natural language queries
- **Native hybrid search** — combines both in a single query
- **Rich metadata filtering** — filter by pdf_type, lot_code, section before searching
- **Payload storage** — stores full extracted text alongside vectors

---

## Phase 5: Chat & Query Service

### What Happens

Users interact through a chat interface. The system intelligently routes queries to either a simple Q&A path or the full PO generation workflow.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Router** | LangGraph | Determines query intent and routes to appropriate path |
| **Simple Q&A** | LangChain Retrieval Chain | Weaviate retrieval → Claude 3.7 answer generation |
| **PO Generation** | LangGraph Workflow (7 nodes) | Full structured workflow (detailed in Phase 6) |
| **Conversation Memory** | LangChain Memory | Maintains context across messages |
| **LLM** | Claude 3.7 Sonnet via LiteLLM Proxy | All chat responses |

### Two Paths

#### Path A: Simple Q&A (Conversational)

For questions like:
- "What are the selected options?"
- "Who is the purchaser?"
- "Show me carpet materials from the take off"
- "What is the lot address?"

```
User Question
  → LangChain Retrieval Chain
    → Weaviate Hybrid Search (alpha = 0.5)
      → Filter by lot_code + pdf_type
      → Retrieved relevant pages
    → Context sent to Claude 3.7 Sonnet (via LiteLLM)
    → Natural language answer returned
```

#### Path B: PO Generation (Structured Workflow)

For requests like:
- "Generate the purchase order"
- "Create PO for this lot"

```
User Request
  → LangGraph PO Workflow (7 nodes)
    → Cross-references both PDFs + SAP Database
    → Returns structured Purchase Order
```

### Conversation Memory

The system remembers context across messages:

- "this lot" → E003
- "the purchaser" → Justina Sutherland
- "that option" → last discussed option
- "her contract date" → knows "her" = Justina Sutherland

---

## Phase 6: Purchase Order Generation Workflow

### What Happens

When the user requests PO generation, a 7-node LangGraph workflow executes. It cross-references the selection sheet, take off sheet, and SAP database to produce a structured purchase order.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Workflow Engine** | LangGraph | Defines nodes, edges, branching, validation loops |
| **Tools** | LangChain Tools | Weaviate Retriever + SAP Lookup Tool + LLM Tool |
| **LLM** | Claude 3.7 Sonnet via LiteLLM | Reasoning, replacement logic, PO formatting |

### The 7-Node Workflow

#### Node 1: Retrieve Selections

```
Source: Weaviate
Filter: pdf_type = "selection_sheet", lot_code = "E003"
Search: BM25 dominant (alpha = 0.2)

Output:
  ✅ SLAB FOUNDATION (FSA) — selected
  ✅ ELEVATION A (ELA) — selected
  ✅ Study (MAS) — selected
  ❌ Morning Room (MAA) — not selected
  ❌ Owners Bath (AMG) — not selected
```

#### Node 2: Retrieve Take Off Data

```
Source: Weaviate
Filter: pdf_type = "take_off", lot_code = "E003"
Search: BM25 dominant (alpha = 0.2)
Retrieve: ALL pages (need complete take off data)

Output:
  Base House Rooms: 315, 89, 200, 29, 129, 125
  Option Rooms: 316, 303, 21, 105, 197, 302
  All measurements, quantities, UOM, notes
```

#### Node 3: Apply Replacement Logic

```
LLM: Claude 3.7 Sonnet (via LiteLLM)

Logic:
  MAS is selected →
    Row 316 (GREAT ROOM WITH STUDY) REPLACES Row 315 (GREAT ROOM)
    Row 21 (BEDROOM HALL WITH STUDY) REPLACES Row 29 (BEDROOM HALL)
    Row 105 (STUDY) REPLACES Row 125 (BEDROOM #3)

  MAA is NOT selected →
    Row 302, 303 → IGNORED

  AMG is NOT selected →
    Row 197 → IGNORED

Output — ACTIVE ROOMS:
  ✅ 316 — Great Room with Study (replaced 315)
  ✅ 89  — Dining Area (unchanged)
  ✅ 200 — Owners Bedroom/WIC (unchanged)
  ✅ 21  — Bedroom Hall with Study (replaced 29)
  ✅ 129 — Bedroom #2 (unchanged)
  ✅ 105 — Study (replaced 125)

  ❌ 315 — REMOVED
  ❌ 29  — REMOVED
  ❌ 125 — REMOVED
```

#### Node 4: Calculate Material Quantities

```
From active rooms ONLY:

  Total Sq Yds = sum from active rows
  Total Pad Sq Yds = sum from active rows
  Total Wood/Tile Sq Ft = sum from active rows
  Total Shoe/Base LF = sum from active rows
  Total T-Moulding LF = sum from active rows
  Total Schluter LF = sum from active rows
  Total Marble Threshold INCHES = sum from active rows

Output: Material list with calculated quantities and UOM
```

#### Node 5: SAP Code Lookup

```
Source: PostgreSQL (SAP Master Data)
Library: SQLAlchemy wrapped in Custom LangChain Tool
Queries: Pre-defined, parameterized (LLM does NOT write SQL)

For each material:
  Material description → SAP Material Code
  Material description → Type of Material (Installation / Sundry / Labor)
  Material description → UOM
  Material description → Trade category

Example:
  "GOLDEN COVE, CASCADE" → 10488028, Installation, YD2, Carpet
  "EMERALD 7/16"         → 20000282, Sundry, YD2, Carpet
  "STRETCH IN STD CARPET" → 80000378, Labor, YD2, Carpet
```

#### Node 6: Validate

```
Check 1: All materials have SAP codes?
  ├── YES → continue
  └── NO  → flag unmatched items

Check 2: Quantities valid? (no negatives, no zeros)
  ├── YES → continue
  └── NO  → flag for review

Check 3: No duplicate replacements?
  ├── YES → continue
  └── NO  → error, loop back to Node 3

Check 4: All trades accounted for?
  ├── YES → continue
  └── NO  → flag missing trades
```

#### Node 7: Format & Generate Purchase Order

```
LLM: Claude 3.7 Sonnet (via LiteLLM)

Output Format:
┌───────────┬──────────────┬────────┬─────┬─────────────────────────────────┬──────────────┐
│ Trade     │ SAP Material │ Qty    │ UOM │ Material Description             │ Type         │
├───────────┼──────────────┼────────┼─────┼─────────────────────────────────┼──────────────┤
│ Carpet    │ 10488028     │ 12.66  │ YD2 │ GOLDEN COVE, CASCADE, HOME FDN  │ Installation │
│ Carpet    │ 20000282     │ 12     │ YD2 │ CARPENTER, EMERALD 7/16         │ Sundry       │
│ Carpet    │ 80000378     │ 12.027 │ YD2 │ Install, STRETCH IN STD CARPET  │ Labor        │
│ FloorTile │ 10651607     │ 94     │ FT2 │ CAVANITE, XNVF84CAVAWH1717     │ Installation │
│ FloorTile │ 20001490     │ 1      │ EA  │ 2", MASKING TAPE                │ Sundry       │
│ FloorTile │ 20011708     │ 90     │ FT2 │ DITRA30M, 323 FT2, UNCOUPLING  │ Sundry       │
└───────────┴──────────────┴────────┴─────┴─────────────────────────────────┴──────────────┘

+ PO Header: PO Number, Date, Lot Code, Community, Purchaser
+ Warnings: Any unmatched items
+ Export: Excel / PDF / JSON
```

---

## Phase 7: SAP Code Lookup from PostgreSQL

### What Happens

During PO generation (Node 5), the system queries PostgreSQL to find SAP material codes, vendor codes, types, and pricing for each material extracted from the take off sheet.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Database** | PostgreSQL | Relational database holding SAP master data |
| **ORM / Connection** | SQLAlchemy | Industry-standard Python SQL toolkit |
| **Driver** | psycopg2-binary | PostgreSQL adapter for Python |
| **Integration** | Custom LangChain Tool | Wraps SQLAlchemy with pre-defined safe queries |

### Why Custom LangChain Tool + SQLAlchemy (NOT LangChain SQL Agent)?

| Approach | Risk | Our Choice |
|----------|------|------------|
| LangChain SQL Agent (LLM writes SQL) | ❌ LLM might write wrong SQL → incorrect SAP codes → wrong PO | ❌ NOT used |
| Custom Tool + SQLAlchemy (pre-defined queries) | ✅ Safe, predictable, parameterized queries | ✅ USED |

**The LLM never writes raw SQL.** It only provides parameters (material description, trade name). The custom tool runs pre-defined, tested queries.

### Database Schema

#### Table: sap_master

| Column | Type | Example |
|--------|------|---------|
| `id` | SERIAL PK | 1 |
| `item_code` | VARCHAR | "FSA" |
| `item_description` | VARCHAR | "SLAB FOUNDATION" |
| `sap_material_code` | VARCHAR | "10488028" |
| `sap_vendor_code` | VARCHAR | "V-5001" |
| `unit_price` | DECIMAL | 12500.00 |
| `uom` | VARCHAR | "YD2" |
| `type_of_material` | VARCHAR | "Installation" / "Sundry" / "Labor" |
| `trade` | VARCHAR | "Carpet" |
| `plant_code` | VARCHAR | "P-1000" |
| `purchase_group` | VARCHAR | "PG-200" |

#### Table: material_mapping

| Column | Type | Example |
|--------|------|---------|
| `id` | SERIAL PK | 1 |
| `take_off_description` | VARCHAR | "GOLDEN COVE, CASCADE, HOME FOUNDATIONS" |
| `sap_material_code` | VARCHAR | "10488028" |
| `trade` | VARCHAR | "Carpet" |

### Pre-defined Safe Queries

```
Query 1: get_sap_by_description(material_description, trade)
  → Returns: sap_code, type, uom, vendor

Query 2: get_sap_by_item_code(item_code)
  → Returns: sap_code, type, uom, vendor

Query 3: get_all_materials_by_trade(trade_name)
  → Returns: list of all materials for that trade

Query 4: validate_sap_code_exists(sap_code)
  → Returns: boolean
```

---

## Phase 8: LLM Gateway — LiteLLM Proxy

### What Happens

**Every single LLM and embedding call** in the entire system goes through LiteLLM Proxy. It runs as a **separate service** — independent from LangChain, LangGraph, and the application.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Service** | LiteLLM Proxy Server | Runs on its own port (e.g., http://localhost:4000) |
| **Protocol** | OpenAI-compatible API | LangChain thinks it's talking to OpenAI |

### Why Separate Service (Not a Library)?

| Aspect | As Library (Inside App) | As Separate Service (Proxy) |
|--------|------------------------|----------------------------|
| **Cost tracking** | Mixed into app code | Centralized, one dashboard |
| **API key management** | Keys in app code | Keys stored in proxy only |
| **Model switching** | Change app code | Change proxy config, app untouched |
| **Multiple services** | Each service manages own LLM calls | All services share one gateway |
| **Independence** | Coupled to app | If app restarts, proxy keeps running |

### Model Routing

```
LiteLLM Proxy routes:

  "claude-3.7-sonnet" → Anthropic API
    Used for:
      • Vision extraction (both PDFs)
      • Replacement logic reasoning
      • Chat Q&A answer generation
      • PO formatting and generation

  "text-embedding-3-small" → OpenAI API
    Used for:
      • Text embedding creation (1536 dimensions)
```

### What LiteLLM Tracks

| Metric | Detail |
|--------|--------|
| Input tokens per call | How many tokens sent to the LLM |
| Output tokens per call | How many tokens the LLM generated |
| Cost per call | Calculated based on model pricing |
| Cost per PDF extraction | Sum of all vision calls for one PDF |
| Cost per PO generation | Sum of all LLM calls in the 7-node workflow |
| Total monthly spend | Aggregated across all operations |
| Latency per call | Response time from each provider |

### Additional Capabilities

- **Rate limiting** — prevent budget overruns
- **Fallback routing** — if Anthropic is down, route to OpenAI GPT-4o as backup
- **Load balancing** — distribute across multiple API keys
- **Request/response logging** — every call logged for debugging

---

## Phase 9: Observability

### What Happens

Every operation in the system is traced, logged, and monitored for debugging, quality evaluation, and performance tracking.

### What We Are Using

| Component | Technology | Details |
|-----------|-----------|---------|
| **Platform** | Langfuse (open-source) OR LangSmith | Full pipeline observability |
| **Integration** | Native LangChain/LangGraph integration | Auto-traces all chain and graph executions |

### What Gets Traced

| Operation | What's Visible |
|-----------|---------------|
| PDF extraction | Each vision call, input image, extracted JSON output |
| Embedding creation | Text input, embedding dimensions, token count |
| Weaviate retrieval | Search query, alpha value, returned documents, relevance scores |
| SAP lookup | Query parameters, returned SAP codes |
| LangGraph workflow | Every node execution, state transitions, branching decisions |
| Chat Q&A | User question, retrieved context, generated answer |
| PO generation | Complete end-to-end trace of all 7 nodes |

### When to Add

| Phase | Need |
|-------|------|
| Prototyping | Optional — print/log debugging is sufficient |
| Testing | Useful — evaluate PO accuracy against known correct outputs |
| Staging | Recommended — catch issues before production |
| Production | Essential — monitor every PO generation, track quality |

---

## Complete Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════╗
║                          USER INTERFACE                                  ║
║                       (Streamlit / React)                                ║
║                                                                          ║
║   [Upload Selection Sheet]  [Upload Take Off]  [Chat Box]  [PO Output] ║
╚════════════════════════════════╤═════════════════════════════════════════╝
                                 │
                 ════════════════╤════════════════
                                 │
                                 ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                        BACKEND APPLICATION                               ║
║                                                                          ║
║  ┌────────────────────────────────────────────────────────────────┐     ║
║  │                PHASE 1 & 2: PDF PROCESSING                      │     ║
║  │                                                                  │     ║
║  │  Selection Sheet PDF ──→ pdf2image (300 DPI) ──→ Page Images   │     ║
║  │       │                                                          │     ║
║  │       └──→ Claude 3.7 Sonnet Vision (via LiteLLM)              │     ║
║  │              └──→ Extracted JSON (lot, purchaser, options)      │     ║
║  │                                                                  │     ║
║  │  Take Off PDF ──→ pdf2image (300 DPI) ──→ Page Images          │     ║
║  │       │                                                          │     ║
║  │       └──→ Claude 3.7 Sonnet Vision (via LiteLLM)              │     ║
║  │              └──→ Extracted JSON (rooms, materials, quantities) │     ║
║  └────────────────────────────────┬───────────────────────────────┘     ║
║                                    │                                     ║
║                                    ▼                                     ║
║  ┌────────────────────────────────────────────────────────────────┐     ║
║  │                PHASE 3: EMBEDDING                                │     ║
║  │                                                                  │     ║
║  │  Extracted Text ──→ text-embedding-3-small (via LiteLLM)       │     ║
║  │                      └──→ 1536-dimensional vectors              │     ║
║  └────────────────────────────────┬───────────────────────────────┘     ║
║                                    │                                     ║
║                                    ▼                                     ║
║  ┌────────────────────────────────────────────────────────────────┐     ║
║  │                PHASE 4: STORE IN WEAVIATE                        │     ║
║  │                                                                  │     ║
║  │  Using: Weaviate Python Client (Direct SDK)                     │     ║
║  │                                                                  │     ║
║  │  Collection: selection_sheets                                    │     ║
║  │    → text + vector + metadata (pdf_type, lot_code, page, etc.) │     ║
║  │                                                                  │     ║
║  │  Collection: take_offs                                           │     ║
║  │    → text + vector + metadata (pdf_type, lot_code, section...)  │     ║
║  │                                                                  │     ║
║  │  Linked by: lot_code + upload_batch_id                          │     ║
║  └────────────────────────────────┬───────────────────────────────┘     ║
║                                    │                                     ║
║                                    ▼                                     ║
║  ┌────────────────────────────────────────────────────────────────┐     ║
║  │                PHASE 5 & 6: CHAT & PO SERVICE                    │     ║
║  │                                                                  │     ║
║  │  ┌──────────────────────────────────────────────────────┐      │     ║
║  │  │              LANGGRAPH ROUTER                          │      │     ║
║  │  │                                                        │      │     ║
║  │  │  Simple Q&A ──→ LangChain Retrieval Chain             │      │     ║
║  │  │                   (Weaviate Retriever → Claude 3.7)   │      │     ║
║  │  │                                                        │      │     ║
║  │  │  PO Generation ──→ LangGraph 7-Node Workflow          │      │     ║
║  │  │                     Node 1: Retrieve Selections        │      │     ║
║  │  │                     Node 2: Retrieve Take Off          │      │     ║
║  │  │                     Node 3: Replacement Logic          │      │     ║
║  │  │                     Node 4: Calculate Quantities       │      │     ║
║  │  │                     Node 5: SAP Lookup (PostgreSQL)    │      │     ║
║  │  │                     Node 6: Validate                   │      │     ║
║  │  │                     Node 7: Format PO                  │      │     ║
║  │  └──────────────────────────────────────────────────────┘      │     ║
║  │                                                                  │     ║
║  │  ┌──────────────────────────────────────────┐                   │     ║
║  │  │         CONVERSATION MEMORY               │                   │     ║
║  │  │  (LangChain Memory — context across msgs) │                   │     ║
║  │  └──────────────────────────────────────────┘                   │     ║
║  └────────────────────────────────────────────────────────────────┘     ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
         │                    │                    │
         │                    │                    │
         ▼                    ▼                    ▼
╔════════════════╗ ╔══════════════════╗ ╔═════════════════════════════════╗
║    WEAVIATE     ║ ║   POSTGRESQL     ║ ║      LITELLM PROXY              ║
║                 ║ ║                  ║ ║   (Separate Service)             ║
║ Vector + BM25   ║ ║ SAP Master Data  ║ ║   http://localhost:4000         ║
║                 ║ ║                  ║ ║                                  ║
║ Connected via:  ║ ║ Connected via:   ║ ║  Routes to:                     ║
║ • weaviate-     ║ ║ • SQLAlchemy     ║ ║  • Anthropic (Claude 3.7)       ║
║   python-client ║ ║ • psycopg2       ║ ║  • OpenAI (embeddings)          ║
║   (ingestion)   ║ ║ • Custom         ║ ║                                  ║
║ • langchain-    ║ ║   LangChain Tool ║ ║  Tracks:                        ║
║   weaviate      ║ ║                  ║ ║  • Cost per call                 ║
║   (retrieval)   ║ ║ Pre-defined safe ║ ║  • Tokens per call              ║
║                 ║ ║ queries only     ║ ║  • Monthly spend                 ║
║ Hybrid Search:  ║ ║ LLM NEVER writes ║ ║  • Latency                      ║
║ BM25 + Vector   ║ ║ raw SQL          ║ ║  • Fallback routing              ║
╚════════════════╝ ╚══════════════════╝ ╚═════════════════════════════════╝

                              │
                              ▼
                ╔═══════════════════════════╗
                ║    OBSERVABILITY           ║
                ║  (Langfuse / LangSmith)   ║
                ║                            ║
                ║  Traces all operations:    ║
                ║  • PDF extractions         ║
                ║  • Embeddings              ║
                ║  • Weaviate searches       ║
                ║  • SAP lookups             ║
                ║  • LangGraph workflows     ║
                ║  • Chat conversations      ║
                ╚═══════════════════════════╝
```

---

## Data Flow Summary

### Flow 1: PDF Upload & Processing

```
Selection Sheet PDF
  → pdf2image (300 DPI) → PNG images per page
  → Claude 3.7 Sonnet Vision (via LiteLLM Proxy → Anthropic)
  → Extracted JSON per page
  → text-embedding-3-small (via LiteLLM Proxy → OpenAI)
  → 1536-dim vector per page
  → Weaviate (via weaviate-python-client)
  → Stored: text + vector + metadata (pdf_type="selection_sheet", lot_code, page_number)

Take Off PDF
  → pdf2image (300 DPI) → PNG images per page
  → Claude 3.7 Sonnet Vision (via LiteLLM Proxy → Anthropic)
  → Extracted JSON per page
  → text-embedding-3-small (via LiteLLM Proxy → OpenAI)
  → 1536-dim vector per page
  → Weaviate (via weaviate-python-client)
  → Stored: text + vector + metadata (pdf_type="take_off", lot_code, section, replaces)
```

### Flow 2: Simple Chat Q&A

```
User Question
  → LangGraph Router → identifies as simple Q&A
  → LangChain Weaviate Retriever (via langchain-weaviate)
    → Hybrid search (BM25 + vector, alpha configurable)
    → Metadata filter: lot_code, pdf_type
    → Returns relevant pages
  → Claude 3.7 Sonnet (via LiteLLM Proxy → Anthropic)
    → Generates natural language answer
  → Answer displayed in chat
```

### Flow 3: Purchase Order Generation

```
"Generate PO"
  → LangGraph Router → identifies as PO request
  → LangGraph 7-Node Workflow:

    Node 1 → Weaviate (langchain-weaviate) → Selection sheet items
    Node 2 → Weaviate (langchain-weaviate) → Take off data
    Node 3 → Claude 3.7 (LiteLLM) → Apply replacement logic
    Node 4 → Python calculation → Material quantities
    Node 5 → PostgreSQL (SQLAlchemy + Custom LangChain Tool) → SAP codes
    Node 6 → Validation logic → Check completeness
    Node 7 → Claude 3.7 (LiteLLM) → Format final PO

  → Structured PO table displayed
  → Export options: Excel / PDF / JSON
```

---

## Python Libraries Required

| Library | Version | Purpose |
|---------|---------|---------|
| `pdf2image` | latest | PDF page to PNG image conversion |
| `Pillow` | latest | Image handling (dependency of pdf2image) |
| `weaviate-client` | v4.x | Direct Weaviate connection for ingestion |
| `langchain` | latest | Core framework — tools, prompts, memory |
| `langchain-weaviate` | latest | LangChain Weaviate retriever for LangGraph |
| `langchain-openai` | latest | ChatOpenAI connector (pointed at LiteLLM) |
| `langgraph` | latest | Workflow orchestration (7-node PO workflow) |
| `sqlalchemy` | latest | PostgreSQL ORM / connection |
| `psycopg2-binary` | latest | PostgreSQL driver |
| `openai` | latest | Embedding calls (pointed at LiteLLM) |
| `litellm` | latest | LiteLLM Proxy server |
| `langfuse` | latest | Observability (optional, can use LangSmith instead) |
| `openpyxl` | latest | Excel export for PO |
| `pandas` | latest | Data manipulation for PO formatting |
| `streamlit` | latest | Frontend (or React for custom UI) |

### System Dependencies

| Dependency | Purpose |
|-----------|---------|
| `poppler-utils` | Required by pdf2image for PDF rendering |
| `PostgreSQL 15+` | SAP code database |
| `Docker` (optional) | For running Weaviate and LiteLLM as containers |

---

## Cost Estimation

### Per PO Generation (One Lot)

| Step | LLM Calls | Estimated Cost |
|------|-----------|---------------|
| Selection Sheet extraction (8 pages) | 8 Claude Vision calls | ~$0.10 |
| Take Off extraction (10-12 pages) | 10-12 Claude Vision calls | ~$0.15 |
| Embedding creation (~20 pages) | ~20 embedding calls | ~$0.002 |
| PO workflow (7 nodes, ~4-5 LLM calls) | 4-5 Claude calls | ~$0.08 |
| **Total per PO** | | **~$0.33 - $0.40** |

### Monthly Estimate

| Volume | Monthly Cost |
|--------|-------------|
| 10 POs/day | ~$100 - $120 |
| 50 POs/day | ~$500 - $600 |
| 100 POs/day | ~$1,000 - $1,200 |

### Cost Tracked By

LiteLLM Proxy — centralized cost dashboard for all LLM and embedding calls.

---

## Summary

This system takes **two PDFs** (Selection Sheet + Take Off), extracts structured data using **Claude 3.7 Sonnet Vision**, creates embeddings using **text-embedding-3-small**, stores everything in **Weaviate** with rich metadata, and enables both **conversational Q&A** and **structured Purchase Order generation** through a **LangGraph workflow** that cross-references PDF data with **SAP codes from PostgreSQL** — all while routing every LLM call through a **LiteLLM Proxy** for centralized cost tracking and model management.

**Extract once. Query forever. Generate POs on demand.**
