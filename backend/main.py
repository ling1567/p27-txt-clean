import os
import uvicorn
import socket
import uuid
import time
import asyncio
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from backend.models.config import RuleConfig
from backend.core.cleaning import process_chunk, detect_encoding, remove_bom, identify_chapters

app = FastAPI(title="27txt-formatter-backend")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task storage
tasks: Dict[str, dict] = {}
UPLOAD_DIR = "temp_uploads"
OUTPUT_DIR = "temp_outputs"

for d in [UPLOAD_DIR, OUTPUT_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

@app.get("/")
async def root():
    return {"message": "27txt Formatter API is running"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}_{file.filename}")
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    tasks[task_id] = {
        "filename": file.filename,
        "file_path": file_path,
        "output_path": None,
        "status": "uploaded",
        "progress": 0,
        "report": {},
        "chapters": []
    }
    
    return {"task_id": task_id, "filename": file.filename}

@app.get("/api/stream-progress/{task_id}")
async def stream_progress(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_progress = -1
        while True:
            current_progress = tasks[task_id]["progress"]
            status = tasks[task_id]["status"]
            if current_progress != last_progress or status in ["done", "error"]:
                yield f"data: {{\"progress\": {current_progress}, \"status\": \"{status}\"}}\n\n"
                last_progress = current_progress
            if status in ["done", "error"]:
                break
            await asyncio.sleep(0.2)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def run_cleaning_pipeline(task_id: str, config: RuleConfig):
    task = tasks[task_id]
    input_path = task["file_path"]
    output_filename = f"cleaned_{task['filename']}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    task["output_path"] = output_path
    
    start_time = time.time()
    
    try:
        with open(input_path, "rb") as f:
            encoding = detect_encoding(f)
        
        file_size = os.path.getsize(input_path)
        chunk_size = 1024 * 1024 
        processed_size = 0
        
        # Read the entire file content to identify chapters (for metadata)
        # Note: For very large files, we'd do this iteratively, but for 50MB it's manageable in memory
        with open(input_path, "r", encoding=encoding, errors="ignore") as f:
            all_content = f.read()
            task["chapters"] = identify_chapters(all_content, config)

        with open(input_path, "r", encoding=encoding, errors="ignore") as fin, \
             open(output_path, "w", encoding="utf-8", newline='\n') as fout:
            
            first_chunk = fin.read(chunk_size)
            if first_chunk:
                first_chunk = remove_bom(first_chunk)
                cleaned = process_chunk(first_chunk, config)
                fout.write(cleaned)
                processed_size += len(first_chunk.encode(encoding, errors="ignore"))
                task["progress"] = int((processed_size / file_size) * 100)
            
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                cleaned = process_chunk(chunk, config)
                fout.write(cleaned)
                processed_size += len(chunk.encode(encoding, errors="ignore"))
                task["progress"] = min(99, int((processed_size / file_size) * 100))
        
        end_time = time.time()
        task["status"] = "done"
        task["progress"] = 100
        task["report"] = {
            "duration": round(end_time - start_time, 2),
            "original_size": file_size,
            "cleaned_size": os.path.getsize(output_path),
            "encoding_detected": encoding,
            "chapters_found": len(task["chapters"])
        }
        
    except Exception as e:
        print(f"Error processing {task_id}: {str(e)}")
        task["status"] = "error"
        task["message"] = str(e)

@app.post("/api/process/{task_id}")
async def process_file(task_id: str, config: RuleConfig, background_tasks: BackgroundTasks):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 0
    background_tasks.add_task(run_cleaning_pipeline, task_id, config)
    return {"message": "Processing started"}

@app.post("/api/preview/{task_id}")
async def preview_file(task_id: str, config: RuleConfig, lines: int = 200):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
        
    input_path = tasks[task_id]["file_path"]
    with open(input_path, "rb") as f:
        encoding = detect_encoding(f)
    
    # Read snippet
    with open(input_path, "r", encoding=encoding, errors="ignore") as f:
        # Read the first N lines
        snippet_lines = []
        for _ in range(lines):
            line = f.readline()
            if not line: break
            snippet_lines.append(line)
        
        original_snippet = "".join(snippet_lines)
        cleaned_snippet = process_chunk(original_snippet, config)
        chapters = identify_chapters(original_snippet, config)
        
        return {
            "original": original_snippet,
            "cleaned": cleaned_snippet,
            "chapters": chapters
        }

@app.get("/api/download/{task_id}")
async def download_file(task_id: str):
    if task_id not in tasks or tasks[task_id]["status"] != "done":
        raise HTTPException(status_code=404, detail="File not ready")
    return FileResponse(tasks[task_id]["output_path"], filename=f"cleaned_{tasks[task_id]['filename']}")

@app.get("/api/report/{task_id}")
async def get_report(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]["report"]

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
