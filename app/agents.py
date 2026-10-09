"""Six specialised agents powered by GroqCloud LPU inference. Enhanced with file analysis and interactive chatbot capabilities."""
import io, json, os, re, math, time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import httpx
from .file_utils import chunk_text

# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv()

# 1. GroqCloud API configuration
GROQ_API_BASE = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1").rstrip("/")
RAW_MODEL = os.getenv("OMNI_MODEL", "openai/gpt-oss-120b").strip()

if not RAW_MODEL or any(x in RAW_MODEL.lower() for x in ("grok", "claude", "llama-3.3-70b")):
    MODEL = "openai/gpt-oss-120b"
else:
    MODEL = RAW_MODEL

_http_client = None

def get_groq_key() -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key or key.strip().startswith("your-"):
        raise ValueError("GROQ_API_KEY is not set in your .env file")
    return key.strip()

def get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=60.0)
    return _http_client

def llm_messages(messages: list[dict], max_tokens: int = 2500, temperature: float = 0.2, json_mode: bool = False) -> str:
    api_key = get_groq_key()
    client = get_http_client()
    
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    max_retries = 6
    for attempt in range(max_retries):
        r = client.post(f"{GROQ_API_BASE}/chat/completions", headers=headers, json=payload)
        
        # If json_mode was rejected, retry without it
        if r.status_code == 400 and json_mode:
            payload.pop("response_format", None)
            r = client.post(f"{GROQ_API_BASE}/chat/completions", headers=headers, json=payload)
            
        if r.status_code == 200:
            data = r.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError(f"Groq API returned empty choices: {data}")
            return choices[0].get("message", {}).get("content", "")

        # Gracefully handle 429 Rate Limits on Groq
        if r.status_code == 429:
            err_text = r.text
            match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_text, re.IGNORECASE)
            wait_time = float(match.group(1)) + 1.0 if match else (2.5 * (attempt + 1))
            time.sleep(wait_time)
            continue

        error_msg = r.text
        try:
            err_json = r.json()
            if "error" in err_json:
                error_msg = err_json["error"].get("message", error_msg)
        except Exception:
            pass
        raise RuntimeError(f"Groq API error ({r.status_code}): {error_msg}")

    raise RuntimeError("Groq API rate limit exceeded after multiple retry attempts. Please wait a few seconds and retry.")

def llm(system: str, user: str, max_tokens: int = 2500, json_mode: bool = False) -> str:
    return llm_messages([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ], max_tokens=max_tokens, json_mode=json_mode)

def extract_json(txt: str):
    """Safely extracts JSON even if the model includes markdown code fences or conversational text."""
    txt = txt.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    bracket_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", txt)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0).strip())
        except json.JSONDecodeError:
            pass

    return json.loads(txt)

def jllm(system: str, user: str):
    sys_prompt = system + "\nYou must reply with a valid JSON object only. Do not wrap in markdown or conversational commentary."
    txt = llm(sys_prompt, user, json_mode=True)
    return extract_json(txt)

def toks(s: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))

# Local Semantic Embedding Engine (FastEmbed)
_embedder = None
_embedding_available = None

def get_embedder():
    global _embedder, _embedding_available
    if _embedding_available is None:
        try:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            _embedding_available = True
        except Exception:
            _embedder = None
            _embedding_available = False
    return _embedder

def cosine_sim(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# 1. Planner
def planner(objective: str, file_context: str = "", file_name: str = "") -> list[str]:
    file_note = ""
    if file_context:
        file_note = f"\nNote: An uploaded document '{file_name or 'Uploaded Document'}' is attached. Plan tasks to extract core findings, analyze key data, and cross-reference with industry/market context."

    plan = jllm(
        "You are an autonomous research planner. Break the objective into 4-5 focused research sub-tasks in JSON.",
        f'Objective: {objective}{file_note}\nReturn JSON format: {{"tasks": ["subtask 1", "subtask 2", ...]}}'
    )
    tasks = plan.get("tasks", [])
    if not tasks:
        tasks = [objective]
    return tasks[:5]

# 2. Retriever (web search + dedupe + chunking for RAG + uploaded file incorporation)
def search(query: str, n: int = 4) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key or api_key.strip().startswith("your-"):
        return []
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            timeout=30,
            json={"api_key": api_key.strip(), "query": query, "max_results": n}
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return [{"url": x.get("url", ""), "title": x.get("title", ""), "text": x.get("content", "")} for x in results]
    except Exception:
        return []

def retriever(tasks: list[str], file_context: str = "", file_name: str = "") -> dict:
    seen_urls, docs, dropped = set(), [], 0

    # If user provided an uploaded document, chunk and prioritize as primary sources
    if file_context:
        chunks = chunk_text(file_context, chunk_size=1200, overlap=150)
        clean_name = file_name or "Uploaded Document"
        for i, chunk in enumerate(chunks[:12]):
            doc_item = {
                "id": len(docs) + 1,
                "url": f"attachment://{clean_name}#chunk={i+1}",
                "title": f"{clean_name} (Part {i+1})",
                "text": chunk,
                "domain": "attached-document",
                "is_uploaded": True
            }
            docs.append(doc_item)

    # Perform web queries to supplement
    for t in tasks:
        try:
            items = search(t, n=3)
        except Exception:
            items = []
        for d in items:
            key = d["url"].split("#")[0].rstrip("/")
            d_toks = toks(d["text"])
            near = any(
                len(d_toks & toks(o["text"])) / max(1, len(d_toks | toks(o["text"]))) > 0.8
                for o in docs
            )
            if key in seen_urls or near:
                dropped += 1
                continue
            seen_urls.add(key)
            d["id"] = len(docs) + 1
            d["domain"] = urlparse(d["url"]).netloc
            d["is_uploaded"] = False
            docs.append(d)

    return {"docs": docs, "duplicates_removed": dropped}

def top_chunks(claim: str, docs: list[dict], k: int = 3) -> list[dict]:
    """Semantic RAG using FastEmbed embeddings when available; lexical overlap fallback."""
    if not docs:
        return []
    embedder = get_embedder()
    if embedder is not None:
        try:
            texts = [d["text"][:700] for d in docs]
            doc_embeddings = list(embedder.embed(texts))
            claim_embedding = list(embedder.embed([claim]))[0]
            scored = [
                (cosine_sim(claim_embedding, doc_emb), doc)
                for doc_emb, doc in zip(doc_embeddings, docs)
            ]
            scored.sort(key=lambda x: -x[0])
            return [d for s, d in scored[:k] if s > 0.15]
        except Exception:
            pass

    q = toks(claim)
    scored = [
        (len(q & toks(d["text"])) / math.sqrt(len(toks(d["text"])) + 1), d)
        for d in docs
    ]
    return [d for s, d in sorted(scored, key=lambda x: -x[0])[:k] if s > 0]

# 3. Verifier
def _check_single_claim(claim: str, docs: list[dict]) -> dict:
    ev = top_chunks(claim, docs, k=3)
    ctx = "\n".join(f"[{d['id']}] {d['text'][:400]}" for d in ev)
    try:
        v = jllm(
            "You are a strict fact checker. Judge whether the evidence supports the claim in JSON. "
            'Return JSON format: {"support": 0.0-1.0, "supporting_ids": [ints], "note": "short explanation"}',
            f"Claim: {claim}\nEvidence:\n{ctx}"
        )
    except Exception:
        v = {"support": 0.0, "supporting_ids": [], "note": "Verification check completed"}

    ids = [i for i in v.get("supporting_ids", []) if any(d["id"] == i for d in docs)]
    domains = {d["domain"] for d in docs if d["id"] in ids}
    try:
        support_val = float(v.get("support", 0.0))
    except (ValueError, TypeError):
        support_val = 0.0

    conf = round(100 * (0.6 * support_val + 0.4 * min(len(domains), 3) / 3))
    status = "Verified" if conf >= 70 else "Partly verified" if conf >= 45 else "Unverified"
    return {
        "claim": claim,
        "confidence": conf,
        "status": status,
        "sources": ids,
        "note": v.get("note", "")
    }

def verifier(objective: str, docs: list[dict]) -> list[dict]:
    if not docs:
        return []
    corpus = "\n\n".join(f"[{d['id']}] {d['title']}: {d['text'][:450]}" for d in docs[:10])
    claims_res = jllm(
        "Extract 5-7 key factual claims relevant to the objective, only ones stated in the sources, as JSON.",
        f'Objective: {objective}\nSources:\n{corpus}\nReturn JSON format: {{"claims": ["...", "..."]}}'
    )
    claims = claims_res.get("claims", [])
    if not claims:
        return []

    out = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        out = list(pool.map(lambda c: _check_single_claim(c, docs), claims[:7]))

    return sorted(out, key=lambda x: -x["confidence"])

# 4. Analyst
def analyst(objective: str, claims: list[dict]) -> dict:
    good = [c for c in claims if c.get("confidence", 0) >= 45]
    if not good:
        good = claims
    return jllm(
        "You are a market analyst. Use ONLY numbers present in the claims; never invent figures. "
        'Return valid JSON: {"insights": ["..."], "risks": ["..."], "chart": {"title": "", "unit": "", '
        '"data": [{"label": "", "value": 0}]}} where chart data uses figures from the claims '
        "(empty list if none).",
        f"Objective: {objective}\nClaims:\n{json.dumps(good)}"
    )

# 5. Visualizer
def visualizer(chart: dict) -> bytes | None:
    data = chart.get("data") or []
    if not data:
        return None

    clean_labels, clean_values = [], []
    for d in data:
        label = str(d.get("label", "")).strip() or "Item"
        raw_val = d.get("value")
        if raw_val is None:
            continue
        if isinstance(raw_val, (int, float)):
            val = float(raw_val)
        else:
            num_str = re.sub(r"[^\d.-]", "", str(raw_val))
            try:
                val = float(num_str)
            except ValueError:
                continue
        clean_labels.append(label)
        clean_values.append(val)

    if not clean_values:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.6))
    # Sleek minimalist monochrome black & charcoal styling for chart
    bars = ax.barh(clean_labels[::-1], clean_values[::-1], color="#18181b", edgecolor="#09090b", height=0.6)
    ax.set_title(chart.get("title", ""), fontsize=12, fontweight="bold", pad=12, color="#09090b")
    ax.set_xlabel(chart.get("unit", ""), fontsize=10, color="#52525b")
    ax.tick_params(colors="#27272a")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#e4e4e7')
    ax.spines['bottom'].set_color('#e4e4e7')
    ax.grid(axis="x", linestyle=":", alpha=0.6, color="#d4d4d8")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=160, facecolor="#ffffff")
    plt.close(fig)
    return buf.getvalue()

# 6. Writer
def writer(objective: str, claims: list[dict], analysis: dict, docs: list[dict], file_name: str = "") -> str:
    attached_note = f" (including analysis of uploaded file: {file_name})" if file_name else ""
    body = llm(
        "You are a senior research analyst. Write a professional, comprehensive markdown report: "
        "Executive Summary, Key Findings, Analysis, Opportunities, Risks, Recommendations, Limitations. "
        "Cite sources strictly as [n] using only the source ids provided. "
        "Flag Partly verified/Unverified claims as lower certainty. Do not add facts that are not in the claims.",
        f"Objective: {objective}{attached_note}\nClaims:\n{json.dumps(claims)}\nAnalysis:\n{json.dumps(analysis)}",
        3000
    )
    refs = "\n".join(f"[{d['id']}] {d['title']}. {d['url']}" for d in docs)
    return f"# {objective}\n\n{body}\n\n## Sources\n{refs}\n"

# 7. Interactive Research Chatbot
def chat_analyst(objective: str, report_md: str, claims: list[dict], analysis: dict, sources: list[dict], file_name: str, file_context: str, history: list[dict], user_message: str) -> str:
    """Provides conversational answers to user follow-up questions grounded in the research report and sources."""
    system_prompt = (
        "You are OmniResearch AI Assistant, an authoritative, analytical, and helpful research partner.\n"
        "You have conducted autonomous research on the user's objective and have access to the full report, "
        "verified claims, data points, and source citations.\n\n"
        "GUIDELINES:\n"
        "1. Ground your answers strictly in the generated research findings, data, and sources.\n"
        "2. Be concise, sharp, and structured. Use bullet points or mini-tables where helpful.\n"
        "3. Cite source indices [n] if referencing specific facts from the report.\n"
        "4. If asked to summarize, elaborate on a section, or extract strategic takeaways, fulfill it immediately.\n"
        "5. If asked about something not in the research report, acknowledge the boundary honestly."
    )

    # Provide concise digest of the research job to anchor the conversation
    digest = [
        f"RESEARCH OBJECTIVE: {objective}",
        f"ATTACHED DOCUMENT: {file_name or 'None'}",
        "\n--- REPORT EXCERPTS ---",
        report_md[:4000] if report_md else "Report in progress.",
        "\n--- VERIFIED CLAIMS & CONFIDENCE ---",
        json.dumps([{"claim": c["claim"], "confidence": f"{c['confidence']}%", "status": c["status"]} for c in claims[:8]]),
        "\n--- KEY INSIGHTS & RISKS ---",
        json.dumps({"insights": analysis.get("insights", [])[:4], "risks": analysis.get("risks", [])[:4]}),
        "\n--- SOURCES LIST ---",
        "\n".join(f"[{d['id']}] {d['title']}" for d in sources[:10])
    ]
    context_text = "\n".join(digest)

    messages = [{"role": "system", "content": f"{system_prompt}\n\nRESEARCH CONTEXT:\n{context_text}"}]
    
    # Append conversation history (up to last 10 turns)
    for h in history[-10:]:
        role = h.get("role")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    return llm_messages(messages, max_tokens=1500, temperature=0.3)
