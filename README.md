# ReelFact - Multimodal Instagram Reel Fact-Checker & Conversational RAG

An AI-powered multimodal fact-checking pipeline designed to ingest Instagram Reels (or uploaded video files), extract speech and visual evidence natively with multimodal models like **Gemma 4**, isolate checkable atomic claims across audio and visual modalities, retrieve evidence from authoritative peer-reviewed and journalistic sources, deliver fact-checked verdicts with source citations and visual grounding, and enable interactive follow-up QA.

---

## Key Features

1. **Native Multimodal Perception & Gemma 4 Support**:
   - Direct end-to-end multimodal perception using **Gemma 4** (via LM Studio, Ollama, or OpenAI-compatible endpoints).
   - Ingests video keyframes and audio speech simultaneously to capture visual demonstration claims, infographic chart manipulations, and fine-print contradictions.
   - Dual-mode architecture: `native_multimodal` (Gemma 4 single-pass) or `legacy_cascaded` (Whisper + EasyOCR fallback).

2. **Atomic Claim Extraction**:
   - Isolates checkable factual assertions across spoken dialogue, visual overlays, infographics, and visual demonstrations.
   - Generates targeted, neutral search queries per claim.

3. **Credible Source Retrieval (RAG)**:
   - Zero-config DuckDuckGo web search + optional Tavily / Fact-Check APIs.
   - Domain credibility scoring algorithm (prioritizing Tier 1 authoritative sources like PubMed, WHO, CDC, Nature, Snopes, Reuters, AP).
   - Full article extraction (`Trafilatura`) and vector indexing in **ChromaDB**.

4. **Fact Verification & Scoring**:
   - Cross-examines each claim and associated video keyframe against retrieved evidence passages.
   - Assigns structured verdicts (`TRUE`, `MOSTLY_TRUE`, `MISLEADING`, `FALSE`, `UNVERIFIABLE`), confidence scores, and plain-English rationales.
   - Synthesizes an overall **Reel Trust Score (0 - 100)** and executive takeaway summary.

5. **Visually-Grounded Follow-Up Agent**:
   - Interactive conversational RAG agent with multimodal memory.
   - Inspects specific video keyframes when users inquire about visual objects, timestamps, or charts.
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
# Pipeline mode ("native_multimodal" for Gemma 4 / LM Studio or "legacy_cascaded")
PIPELINE_MODE=native_multimodal

# Options: "lmstudio", "ollama", "gemini", "openai"
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=gemma-4

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
