# OmniResearch

> **"One Platform. Unlimited Knowledge."**  
> Autonomous Multi-Agent Intelligence Engine: Planner → Retriever → Verifier → Analyst → Visualizer → Writer, with Document Upload Analysis, Interactive Chatbot Assistant, and PDF/DOCX/PPTX Export.

---

## Key Features

- **Document Upload & File Analysis**: Upload PDF, DOCX, TXT, CSV, or JSON documents. OmniResearch automatically parses, chunks, and incorporates your files as primary grounded evidence in the research pipeline.
- **Interactive Research Analyst Chatbot**: Follow-up multi-turn conversation tab grounded strictly in the generated report, verified claims, and attached sources. Ask for summaries, deep dives, risk analyses, or executive email drafts.
- **Minimalist White & Black UI/UX**: High-contrast, distraction-free monochrome interface (Linear / Vercel aesthetic) with real-time agent telemetry, confidence meters, and interactive charts.
- **Persistent Database**: SQLite persistence (`omniresearch.db`) storing all research runs, verified claims, and multi-turn chat conversations.
- **Multi-Format Export**: Direct 1-click downloads as PDF, DOCX, or PPTX presentations.
- **Semantic Vector Retrieval**: Hybrid RAG powered by `FastEmbed` (`BAAI/bge-small-en-v1.5`) with lexical fallback.
- **Parallel Fact Verification**: Concurrent fact-checking across multiple independent domains with LLM judge scoring.

---

## Getting Started

### 1. Setup Environment
```bash
cp .env.example .env
```
Add your API keys to `.env`:
```ini
GROQ_API_KEY=your-groqcloud-api-key-here
TAVILY_API_KEY=your-tavily-key-here
OMNI_MODEL=openai/gpt-oss-120b
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Or using Docker:
```bash
docker build -t omniresearch .
docker run -p 8001:8001 --env-file .env omniresearch
```

---

## How to Use

### A. Web Interface
Open your browser and navigate to:
```
http://localhost:8001/
```
- **Topic Research**: Enter any question or prompt (or choose a quick prompt chip) and click **Start Research**.
- **Document Analysis**: Drag & drop or click **Attach Document** to upload a PDF, DOCX, or CSV, then click **Start Research**.
- **Interactive Chat**: After generation, open the **Interactive Chatbot** tab to ask follow-up questions about the findings.
- **History Drawer**: Click **History** in the top navigation to revisit and chat with past research jobs.

### B. REST API

1. **Start Research (Text Query)**:
   ```bash
   curl -X POST http://localhost:8001/research \
     -H 'Content-Type: application/json' \
     -d '{"objective":"Analyze global solar capacity projections for 2027"}'
   ```

2. **Start Research with File Upload**:
   ```bash
   curl -X POST http://localhost:8001/research/upload \
     -F "file=@financials.pdf" \
     -F "objective=Analyze Q3 financial health and key vulnerabilities"
   ```

3. **Chat with Research Report**:
   ```bash
   curl -X POST http://localhost:8001/research/<id>/chat \
     -H 'Content-Type: application/json' \
     -d '{"message":"Summarize the key takeaways in 3 bullet points."}'
   ```

4. **Export Formats**:
   ```bash
   curl -o report.pdf http://localhost:8001/research/<id>/export/pdf
   curl -o report.docx http://localhost:8001/research/<id>/export/docx
   curl -o report.pptx http://localhost:8001/research/<id>/export/pptx
   ```

---

## Agent Pipeline Architecture

1. **Planner**: Deconstructs objective into 4–5 targeted sub-tasks, accounting for attached document context.
2. **Retriever**: Ingests uploaded document chunks as verified primary sources and queries Tavily Search for live web corroboration, eliminating near-identical duplicates.
3. **Verifier**: Extracts factual claims and validates them using semantic RAG embeddings (`Confidence = 60% LLM support + 40% independent domain diversity`).
4. **Analyst**: Synthesizes market insights, risks, and extracts strict numerical metrics for visualization.
5. **Visualizer**: Generates clean monochrome quantitative charts using Matplotlib.
6. **Writer**: Produces a structured Markdown report with `[n]` source footnotes and executive recommendations.

---

## Production Deployment (Render + Vercel)

### 1. Backend on Render (FastAPI + PostgreSQL)
1. **Create PostgreSQL Database on Render**:
   - In Render Dashboard, click **New +** → **PostgreSQL**.
   - Note the **Internal Database URL** (or External Database URL).
2. **Deploy Web Service**:
   - Click **New +** → **Web Service** → Connect your GitHub repository `RajaYuvateja/OmniResearch`.
   - **Root Directory**: `omniresearch` (or leave empty if repository root).
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables**:
     - `GROQ_API_KEY`: Your Groq API key
     - `TAVILY_API_KEY`: Your Tavily API key
     - `DATABASE_URL`: Connection string from your Render PostgreSQL instance
     - `FRONTEND_URL`: Your Vercel frontend URL (e.g. `https://your-frontend.vercel.app`)

*(Alternatively, use the included `render.yaml` Blueprint for 1-click automatic provisioning of both the Web Service and PostgreSQL database).*

### 2. Frontend on Vercel
1. Import repository on [Vercel](https://vercel.com/new).
2. **Root Directory**: Select `omniresearch/app/static` (or `app/static`).
3. **Build & Development Settings**:
   - Framework Preset: **Other**
   - Build Command: *(leave blank)*
   - Output Directory: *(leave blank)*
4. Set your deployed Render backend URL in `config.js` (`window.OMNI_API_BASE = "https://your-backend.onrender.com"`) or use the in-app **Backend Settings** modal.
