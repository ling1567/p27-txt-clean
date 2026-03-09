import os
import uuid
import charset_normalizer
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi.responses import FileResponse, StreamingResponse
import io
import urllib.parse
import socket
import webbrowser
import threading
import time
import asyncio

# Internal modules
from core.cleaner import clean_text_pipeline
from core.chapter import detect_chapters, deduce_regex, reorder_chapters, auto_detect_chapter_pattern

app = FastAPI(title="27 TXT Formatter API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
tasks = {}
progress_states = {} # task_id -> int

# --- Pydantic Models ---

class UploadResponse(BaseModel):
    task_id: str
    file_name: str
    preview: List[str]
    encoding: str
    has_bom: bool
    auto_chapters: List[Dict[str, Any]] = []
    detected_regex: Optional[str] = None

class ProcessRequest(BaseModel):
    options: dict

class ProcessResponse(BaseModel):
    preview: List[str]
    logs: List[str]
    chapters: List[Dict[str, Any]] = []

class DeduceRequest(BaseModel):
    samples: List[str]

# --- Helper Functions ---

def process_initial_txt(content: bytes):
    result = charset_normalizer.from_bytes(content).best()
    encoding = result.encoding if result else "utf-8"
    try:
        text = content.decode(encoding)
    except:
        text = content.decode(encoding, errors="replace")
    has_bom = text.startswith('\ufeff')
    if has_bom:
        text = text.lstrip('\ufeff')
    return text, encoding, has_bom

# --- API Endpoints ---

@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="Only .txt files are allowed")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (Max 50MB)")
    text, original_encoding, has_bom = process_initial_txt(content)
    task_id = str(uuid.uuid4())
    
    # 自动识别章节
    auto_regex = auto_detect_chapter_pattern(text)
    auto_chapters = []
    if auto_regex:
        auto_chapters = detect_chapters(text, auto_regex)
    
    lines = text.splitlines()
    tasks[task_id] = {
        "file_name": file.filename,
        "content": text,
        "original_content": text,
        "encoding": original_encoding,
        "has_bom": has_bom
    }
    progress_states[task_id] = 0
    return {
        "task_id": task_id,
        "file_name": file.filename,
        "preview": lines[:500],
        "encoding": original_encoding,
        "has_bom": has_bom,
        "auto_chapters": auto_chapters,
        "detected_regex": auto_regex
    }

@app.get("/api/stream-progress/{task_id}")
async def stream_progress(task_id: str):
    async def event_generator():
        while True:
            if task_id in progress_states:
                progress = progress_states[task_id]
                yield f"data: {progress}\n\n"
                if progress >= 100:
                    break
            else:
                yield "data: 0\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/process/{task_id}", response_model=ProcessResponse)
async def process_file(task_id: str, request: ProcessRequest):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    progress_states[task_id] = 0
    task = tasks[task_id]
    original_text = task["original_content"]
    
    def update_progress(p):
        progress_states[task_id] = p

    # 核心清洗流水线
    processed_text, logs = clean_text_pipeline(original_text, request.options, update_progress)
    
    # 章节处理
    chapters = []
    chapter_pattern = request.options.get("chapter_pattern")
    
    if request.options.get("chapter", False):
        update_progress(95) # Artificial progress for chapter detection
        chapters = detect_chapters(processed_text, chapter_pattern)
        if request.options.get("chapter_reorder", False) and chapters:
            processed_text = reorder_chapters(processed_text, chapters)
            logs.append("已完成章节序号物理重排")
            chapters = detect_chapters(processed_text, chapter_pattern)
    elif chapter_pattern:
        # 即使没有勾选“手动处理-章节重排”，只要有正则，就返回识别结果供前端预览区导航
        chapters = detect_chapters(processed_text, chapter_pattern)
    
    task["content"] = processed_text
    update_progress(100)
    
    lines = processed_text.splitlines()
    return {
        "preview": lines[:500],
        "logs": logs,
        "chapters": chapters
    }

@app.post("/api/chapters/deduce")
async def api_deduce_regex(request: DeduceRequest):
    return {"regex": deduce_regex(request.samples)}

@app.post("/api/chapters/preview/{task_id}")
async def api_preview_chapters(task_id: str, request: dict):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    text = tasks[task_id]["content"]
    chapters = detect_chapters(text, request.get("pattern"), request.get("max_length", 35))
    return {"chapters": chapters}

@app.get("/api/chapters/content/{task_id}/{chapter_index}")
async def get_chapter_content(task_id: str, chapter_index: int):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    text = task["content"]
    options = {} # Default options for detection
    chapters = detect_chapters(text, None) # This uses builtin, ideally we'd pass the current regex
    # Wait, detect_chapters needs to be consistent. 
    # Let's assume the frontend provides the pattern if needed, but for now we'll just use the ones we found.
    # Actually, a better way is to pass the line range from frontend.
    
    return {"detail": "Use /api/preview/range instead for more flexibility"}

@app.post("/api/preview/range/{task_id}")
async def get_preview_range(task_id: str, request: dict):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    start_line = request.get("start_line", 0)
    end_line = request.get("end_line", start_line + 500)
    
    text = tasks[task_id]["content"]
    lines = text.splitlines()
    
    return {
        "preview": lines[start_line:end_line],
        "total_lines": len(lines)
    }

@app.get("/api/download/{task_id}")
async def download_file(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    name_parts = os.path.splitext(task["file_name"])
    new_filename = f"{name_parts[0]}-已处理{name_parts[1]}"
    output = io.BytesIO(task["content"].encode('utf-8'))
    encoded_filename = urllib.parse.quote(new_filename)
    return StreamingResponse(
        output,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def open_browser(port: int):
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:5173")

if __name__ == "__main__":
    import uvicorn
    port = 8000
    while is_port_in_use(port): port += 1
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
