import os, uuid, traceback
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Automatically load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv()
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import agents as A, export as X, db
from .file_utils import extract_text_from_file

app = FastAPI(title="OmniResearch", version="1.2")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static directory for Web UI
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Initialize database
db.init_db()

# Memory cache + Worker pool for bounded concurrency
JOBS: dict[str, dict] = {}
WORKER_POOL = ThreadPoolExecutor(max_workers=3)

class Req(BaseModel):
    objective: str
    file_context: Optional[str] = ""
    file_name: Optional[str] = None

class ChatReq(BaseModel):
    message: str

def execute_pipeline(jid: str, objective: str, file_context: str = "", file_name: str = ""):
    j = JOBS[jid]
    def step(name, fn):
        j["stage"] = name
        msg = f"{name.capitalize()} started"
        j["log"].append(msg)
        db.save_job(j)
        r = fn()
        j["log"].append(f"{name.capitalize()} done")
        db.save_job(j)
        return r

    try:
        tasks = step("planner", lambda: A.planner(objective, file_context=file_context, file_name=file_name))
        j["plan"] = tasks
        
        got = step("retriever", lambda: A.retriever(tasks, file_context=file_context, file_name=file_name))
        docs = got.get("docs", [])
        j["duplicates_removed"] = got.get("duplicates_removed", 0)
        j["sources"] = docs
        
        claims = step("verifier", lambda: A.verifier(objective, docs))
        j["claims"] = claims
        
        analysis = step("analyst", lambda: A.analyst(objective, claims))
        j["analysis"] = analysis
        
        chart_png = step("visualizer", lambda: A.visualizer(analysis.get("chart", {})))
        j["chart_png"] = chart_png
        
        report_md = step("writer", lambda: A.writer(objective, claims, analysis, docs, file_name=file_name))
        j["report_md"] = report_md
        
        j["status"], j["stage"] = "done", "done"
        j["log"].append("Research completed successfully")
    except Exception as e:
        j["status"] = "failed"
        j["error"] = f"{type(e).__name__}: {str(e)}"
        j["log"].append(f"Failed at {j.get('stage')}: {str(e)}")
        traceback.print_exc()
    finally:
        db.save_job(j)

@app.get("/")
def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        resp = FileResponse(index_file, media_type="text/html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return {"message": "OmniResearch API is running. Access interactive docs at /docs"}

@app.get("/static/{filename}")
def static_file(filename: str):
    target = os.path.join(STATIC_DIR, filename)
    if os.path.exists(target):
        media_type = "text/css" if filename.endswith(".css") else "application/javascript" if filename.endswith(".js") else None
        resp = FileResponse(target, media_type=media_type)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/research")
def create(req: Req):
    jid = uuid.uuid4().hex[:12]
    job_record = {
        "id": jid,
        "status": "running",
        "stage": "queued",
        "log": ["Job registered in queue"],
        "objective": req.objective,
        "plan": [],
        "duplicates_removed": 0,
        "sources": [],
        "claims": [],
        "analysis": {},
        "report_md": "",
        "chart_png": None,
        "file_name": req.file_name,
        "file_context": req.file_context or "",
        "chat": [],
        "error": None
    }
    JOBS[jid] = job_record
    db.save_job(job_record)
    WORKER_POOL.submit(execute_pipeline, jid, req.objective, req.file_context or "", req.file_name or "")
    return {"id": jid}

@app.post("/research/upload")
async def create_with_upload(
    file: Optional[UploadFile] = File(None),
    objective: Optional[str] = Form(None)
):
    """Initiates research with an uploaded document (PDF, DOCX, TXT, CSV, JSON, MD)."""
    file_context = ""
    file_name = None

    if file and file.filename:
        file_bytes = await file.read()
        extracted = extract_text_from_file(file_bytes, file.filename)
        file_context = extracted["text"]
        file_name = file.filename

    clean_obj = (objective or "").strip()
    if not clean_obj:
        if file_name:
            clean_obj = f"Analyze document '{file_name}': synthesize key findings, verify claims, and provide strategic recommendations."
        else:
            raise HTTPException(status_code=400, detail="Either an objective or an uploaded file must be provided.")

    jid = uuid.uuid4().hex[:12]
    job_record = {
        "id": jid,
        "status": "running",
        "stage": "queued",
        "log": [
            f"Job registered in queue" + (f" with attached document: {file_name}" if file_name else "")
        ],
        "objective": clean_obj,
        "plan": [],
        "duplicates_removed": 0,
        "sources": [],
        "claims": [],
        "analysis": {},
        "report_md": "",
        "chart_png": None,
        "file_name": file_name,
        "file_context": file_context,
        "chat": [],
        "error": None
    }
    JOBS[jid] = job_record
    db.save_job(job_record)
    WORKER_POOL.submit(execute_pipeline, jid, clean_obj, file_context, file_name or "")
    return {"id": jid, "file_name": file_name, "char_count": len(file_context)}

@app.get("/research")
def list_jobs():
    """List recent research runs from persistent database."""
    return db.list_recent_jobs(limit=25)

@app.get("/research/{jid}")
def get(jid: str):
    # Check cache first, then database
    j = JOBS.get(jid)
    if not j:
        j = db.get_job(jid)
        if j:
            JOBS[jid] = j
    if not j:
        raise HTTPException(status_code=404, detail="Unknown job")
    return {k: v for k, v in j.items() if k not in ("chart_png", "file_context")}

@app.get("/research/{jid}/chart")
def get_chart(jid: str):
    """Retrieve the generated analytics chart as an image directly."""
    j = JOBS.get(jid) or db.get_job(jid)
    if not j:
        raise HTTPException(status_code=404, detail="Unknown job")
    chart_data = j.get("chart_png")
    if not chart_data:
        raise HTTPException(status_code=404, detail="No chart available for this research job")
    return Response(content=chart_data, media_type="image/png")

@app.get("/research/{jid}/export/{fmt}")
def export(jid: str, fmt: str):
    j = JOBS.get(jid) or db.get_job(jid)
    if not j or j.get("status") != "done":
        raise HTTPException(status_code=409, detail="Report not ready")
    fn = {
        "pdf": (X.to_pdf, "application/pdf"),
        "docx": (X.to_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "pptx": (X.to_pptx, "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    }.get(fmt.lower())
    if not fn:
        raise HTTPException(status_code=400, detail="fmt must be pdf, docx or pptx")
    return Response(
        fn[0](j["report_md"], j.get("chart_png")),
        media_type=fn[1],
        headers={"Content-Disposition": f"attachment; filename=omniresearch-{jid}.{fmt.lower()}"}
    )

# ----------------- CHATBOT ENDPOINTS -----------------
@app.post("/research/{jid}/chat")
def chat(jid: str, req: ChatReq):
    """Chat interactively with the research report findings and sources."""
    j = JOBS.get(jid) or db.get_job(jid)
    if not j:
        raise HTTPException(status_code=404, detail="Unknown job")

    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    history = db.get_chat_history(jid)
    
    # Generate response from research analyst agent
    try:
        reply = A.chat_analyst(
            objective=j.get("objective", ""),
            report_md=j.get("report_md", ""),
            claims=j.get("claims", []),
            analysis=j.get("analysis", {}),
            sources=j.get("sources", []),
            file_name=j.get("file_name", ""),
            file_context=j.get("file_context", ""),
            history=history,
            user_message=msg
        )
    except Exception as e:
        reply = f"I encountered an issue generating a response: {str(e)}"

    # Save turns to database
    db.append_chat_message(jid, "user", msg)
    updated_history = db.append_chat_message(jid, "assistant", reply)

    # Sync memory cache if active
    if jid in JOBS:
        JOBS[jid]["chat"] = updated_history

    return {"reply": reply, "history": updated_history}

@app.get("/research/{jid}/chat")
def get_chat(jid: str):
    """Retrieve multi-turn chat history for a research job."""
    j = JOBS.get(jid) or db.get_job(jid)
    if not j:
        raise HTTPException(status_code=404, detail="Unknown job")
    return {"history": db.get_chat_history(jid)}

@app.get("/health")
def health():
    return {"ok": True, "worker_active": True, "database": "sqlite", "file_upload": True, "chat_enabled": True}
