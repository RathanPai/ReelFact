# ReelFact - Multimodal Instagram Reel Fact-Checker & Conversational RAG

An AI-powered multimodal fact-checking pipeline designed to ingest Instagram Reels (or uploaded video files), extract speech and on-screen text overlays (OCR), isolate checkable atomic claims, retrieve evidence from authoritative peer-reviewed and journalistic sources, deliver fact-checked verdicts with source citations, and enable interactive follow-up QA.

---

## Key Features

1. **Multimodal Ingestion & Perception**:
   - Downloads public Instagram Reels via `yt-dlp` or accepts local `.mp4`/`.mov` uploads.
   - GPU-accelerated speech-to-text with timestamp alignment using `faster-whisper`.
   - On-screen text overlay detection using `EasyOCR`.
   - Temporal fusion of audio and visual text streams into a unified multimodal timeline.

2. **Atomic Claim Extraction**:
   - Filters out opinions, banter, and hype to isolate verifiable factual statements (health, science, politics, statistics, historical quotes).
   - Generates targeted, neutral search queries per claim.

3. **Credible Source Retrieval (RAG)**:
   - Zero-config DuckDuckGo web search + optional Tavily / Fact-Check APIs.
   - Domain credibility scoring algorithm (prioritizing Tier 1 authoritative sources like PubMed, WHO, CDC, Nature, Snopes, Reuters, AP).
   - Full article extraction (`Trafilatura`) and vector indexing in **ChromaDB**.

4. **Fact Verification & Scoring**:
   - Cross-examines each claim against retrieved evidence passages.
   - Assigns structured verdicts (`TRUE`, `MOSTLY_TRUE`, `MISLEADING`, `FALSE`, `UNVERIFIABLE`), confidence scores, and plain-English rationales.
   - Synthesizes an overall **Reel Trust Score (0 - 100)** and executive takeaway summary.

5. **Conversational Follow-Up Agent**:
   - Interactive conversational RAG agent with memory.
   - Answers follow-up questions with video timestamp citations and direct evidence links.

6. **High-Aesthetic Web UI**:
   - Glassmorphic dark-mode dashboard with neon status badges.
   - Interactive HTML5 video player synced with claim timestamps (clicking a claim seeks the video directly).
   - Real-time animated pipeline progress stepper.

---

## Quick Start

### 1. Conda Environment
The dedicated Conda environment `reel_fact_checker` is already set up:
```bash
conda activate reel_fact_checker
```

### 2. Configure Environment (`.env`)
Edit `.env` to configure your preferred LLM provider:
```bash
# Options: "ollama", "gemini", "openai", "lmstudio"
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Search provider (default is zero-config duckduckgo)
SEARCH_PROVIDER=duckduckgo
```

### 3. Launch Application
Run the startup script:
```bash
./start.sh
```
Or start Uvicorn directly:
```bash
PYTHONPATH=. /home/xern/miniconda3/envs/reel_fact_checker/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **`http://localhost:8000`**.

---

## Running Tests

Run the complete test suite:
```bash
PYTHONPATH=. /home/xern/miniconda3/envs/reel_fact_checker/bin/pytest tests/
```
