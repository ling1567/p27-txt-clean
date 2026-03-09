import os
import sys
import uuid
import charset_normalizer
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import io
import urllib.parse
import socket
import webbrowser
import threading
import time
import asyncio

# Win32 modules for lightweight tray
import win32gui
import win32con
import win32api

# --- Helpers ---
def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 解决 PyInstaller --windowed 模式下 stdout/stderr 为 None
if hasattr(sys, '_MEIPASS'):
    sys.path.append(sys._MEIPASS)
    log_path = os.path.join(os.path.dirname(sys.executable), "app_debug.log")
    sys.stdout = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
elif sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

# Internal modules
from core.cleaner import clean_text_pipeline
from core.chapter import detect_chapters, deduce_regex, reorder_chapters, auto_detect_chapter_pattern

app = FastAPI(title="27 TXT Formatter API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
tasks = {}
progress_states = {} 

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
                if progress >= 100: break
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
    def update_progress(p): progress_states[task_id] = p
    processed_text, logs = clean_text_pipeline(original_text, request.options, update_progress)
    chapters = []
    chapter_pattern = request.options.get("chapter_pattern")
    if request.options.get("chapter", False):
        update_progress(95)
        chapters = detect_chapters(processed_text, chapter_pattern)
        if request.options.get("chapter_reorder", False) and chapters:
            processed_text = reorder_chapters(processed_text, chapters)
            logs.append("已完成章节序号物理重排")
            chapters = detect_chapters(processed_text, chapter_pattern)
    elif chapter_pattern:
        chapters = detect_chapters(processed_text, chapter_pattern)
    task["content"] = processed_text
    update_progress(100)
    lines = processed_text.splitlines()
    return {"preview": lines[:500], "logs": logs, "chapters": chapters}

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

@app.post("/api/preview/range/{task_id}")
async def get_preview_range(task_id: str, request: dict):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    start_line = request.get("start_line", 0)
    end_line = request.get("end_line", start_line + 500)
    text = tasks[task_id]["content"]
    lines = text.splitlines()
    return {"preview": lines[start_line:end_line], "total_lines": len(lines)}

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
    webbrowser.open(f"http://localhost:{port}")

# --- Static Files & Frontend Routing ---
dist_path = get_resource_path("dist")
if os.path.exists(dist_path):
    @app.get("/")
    async def serve_index(): return FileResponse(os.path.join(dist_path, "index.html"))
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

# --- Native Win32 Tray Logic ---
class SysTrayIcon:
    def __init__(self, port):
        self.port = port
        self.msg_taskbar = win32gui.RegisterWindowMessage("TaskbarCreated")
        
        # 注册窗口类
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = "27txtFormatterTray"
        wc.lpfnWndProc = self.wnd_proc
        self.class_atom = win32gui.RegisterClass(wc)
        
        # 创建隐藏窗口用于接收消息
        self.hwnd = win32gui.CreateWindow(self.class_atom, "27txt Tray", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
        win32gui.UpdateWindow(self.hwnd)
        
        # 加载图标
        icon_path = get_resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.hicon = win32gui.LoadImage(None, icon_path, win32con.IMAGE_ICON, 0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        else:
            self.hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            
        # 添加托盘图标
        self.add_icon()

    def add_icon(self):
        nid = (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, 
               win32con.WM_USER + 20, self.hicon, "27 TXT Formatter")
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_USER + 20:
            if lparam == win32con.WM_RBUTTONUP:
                self.show_menu()
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                open_browser(self.port)
        elif msg == win32con.WM_COMMAND:
            if wparam == 1001: open_browser(self.port)
            elif wparam == 1002: win32gui.DestroyWindow(self.hwnd)
        elif msg == win32con.WM_DESTROY:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
            os._exit(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1001, "打开网页")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1002, "退出程序")
        
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

if __name__ == "__main__":
    import uvicorn
    port = 8000
    while is_port_in_use(port): port += 1
    
    # 启动后端线程
    server_thread = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": port}, daemon=True)
    server_thread.start()
    
    # 自动打开浏览器
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    
    # 启动托盘图标（Win32 消息循环必须在主线程）
    tray = SysTrayIcon(port)
    win32gui.PumpMessages()
