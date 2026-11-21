# Jnana Vistara (ಜ್ಞಾನ ವಿಸ್ತಾರ)
### Offline-First AI Study Tutor for Rural Students

Jnana Vistara is an offline-first, multilingual AI study tutor designed for rural schools with limited or no internet access. Students pick a subject and chapter, ask questions in English (Hindi/Kannada coming soon), and receive simple, friendly explanations strictly grounded in their textbooks with page-level citations. Students can also take interactive quizzes and track their progress over time.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |       Student Devices (Tablets/Phones)|
                      |    Local Wi-Fi Browser: http://<IP>:8000
                      +-------------------+-------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| Host Laptop (Windows 11, 16GB RAM, RTX 2050 4GB VRAM)                             |
|                                                                                   |
|  +---------------------------+        +----------------------------------------+  |
|  | Frontend: React + Vite   |        | FastAPI Web Server (0.0.0.0:8000)      |  |
|  | Tailwind CSS + Lucide     | -----> |  - /api/ask (Streaming SSE)            |  |
|  | Static build in dist/     |        |  - /api/quiz/*, /api/progress/*        |  |
|  +---------------------------+        +-------------------+--------------------+  |
|                                                           |                       |
|           +-----------------------------------------------+                       |
|           v                                               v                       |
|  +-----------------------------+        +--------------------------------------+  |
|  | Hybrid Retrieval Engine     |        | Offline Local LLM                    |  |
|  | Dense: BAAI/bge-m3 (1024d)  |        | Ollama (`phi3:latest` / `qwen2.5:3b`)|  |
|  | Sparse: BM25 (rank_bm25)    |        | Grounded Prompting (Temp: 0.2)       |  |
|  | Fusion: Reciprocal Rank (RRF)        +--------------------------------------+  |
|  +--------------+--------------+                                                  |
|                 |                                                                 |
|                 v                                                                 |
|  +-----------------------------+        +--------------------------------------+  |
|  | Local On-Disk Qdrant DB     |        | Local SQLite Storage                 |  |
|  | Path: `qdrant_db/`          |        | `app.db` (Quizzes, Attempts, Scores) |  |
|  +-----------------------------+        +--------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## Prerequisites
1. **Windows 11** with Python 3.12 (`./venv`)
2. **Ollama** installed with `phi3:latest` downloaded:
   ```bash
   ollama pull phi3:latest
   ```
3. **Node.js LTS** (v20+ or v24) and `npm`

---

## 1. Setup & Installation

Activate the virtual environment and install the dependencies:
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

---

## 2. Ingestion (Textbook Processing)

Place NCERT/State Board textbook PDFs in `data/textbooks/` (e.g. `Science_Class8_Ch1.pdf`).

Run the ingestion pipeline:
```powershell
python -m core.ingest
```

This extracts text page-by-page, divides it into overlapping chunks, generates 1024-dimensional normalized embeddings using `BAAI/bge-m3`, and indexes them in local on-disk Qdrant (`qdrant_db/`).

---

## 3. Running Fully Offline

Once packages and model weights are downloaded, you can disable internet access completely. Jnana Vistara enforces offline mode by setting:
```powershell
$env:HF_HUB_OFFLINE="1"
```

---

## 4. Running the Application

### Start Backend:
```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
Interactive API documentation is available at `http://localhost:8000/docs`.

### Start Frontend (Development):
```powershell
cd frontend
npm run dev
```

---

## 5. Accessing from Other Devices over Local Wi-Fi

1. Connect the host laptop and student tablets/phones to the same local Wi-Fi router or hotspot (no internet required).
2. On the host laptop, open PowerShell and find your local IP address:
   ```powershell
   ipconfig
   ```
   Look for `IPv4 Address` (e.g. `192.168.1.15`).
3. On student devices, open any web browser and navigate to:
   ```
   http://192.168.1.15:8000
   ```
