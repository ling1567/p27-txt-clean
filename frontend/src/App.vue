<script setup lang="ts">
import { ref, onUnmounted, reactive, watch } from 'vue'
import axios from 'axios'

const taskId = ref('')
const filename = ref('')
const uploadStatus = ref<'idle' | 'uploading' | 'processing' | 'done' | 'error'>('idle')
const progress = ref(0)
const statusMessage = ref('')
const report = ref<any>(null)
const chapters = ref<any[]>([])
const originalSnippet = ref('')
const cleanedSnippet = ref('')
let eventSource: EventSource | null = null

// RuleConfig reactive state
const config = reactive({
  encoding: { detect: true, manual_encoding: null },
  base_cleaning: { remove_html: false, remove_control_chars: true, manual_blacklists: [] as string[] },
  formatting: { fullwidth_halfwidth: 'none', paragraph_indent: false, empty_line_threshold: 2, normalize_line_breaks: true },
  chapter: { built_in_patterns: true, custom_regex: '', renumber: false },
  stitching: { enable: false }
})

const cleanupSSE = () => {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

onUnmounted(() => {
  cleanupSSE()
})

// Debounced preview trigger
let previewTimeout: any = null
watch(config, () => {
  if (!taskId.value) return
  if (previewTimeout) clearTimeout(previewTimeout)
  previewTimeout = setTimeout(fetchPreview, 500)
}, { deep: true })

const fetchPreview = async () => {
  if (!taskId.value) return
  try {
    const res = await axios.post(`http://127.0.0.1:8000/api/preview/${taskId.value}`, config)
    originalSnippet.value = res.data.original
    cleanedSnippet.value = res.data.cleaned
    chapters.value = res.data.chapters
  } catch (e) {
    console.error('Preview failed:', e)
  }
}

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  
  const file = target.files[0]
  filename.value = file.name
  uploadStatus.value = 'uploading'
  progress.value = 0
  statusMessage.value = '正在上传文件...'
  report.value = null
  originalSnippet.value = ''
  cleanedSnippet.value = ''

  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await axios.post('http://127.0.0.1:8000/api/upload', formData, {
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          progress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        }
      }
    })
    taskId.value = response.data.task_id
    uploadStatus.value = 'idle'
    statusMessage.value = '上传成功，请配置规则或开始清洗'
    fetchPreview()
  } catch (error) {
    uploadStatus.value = 'error'
    statusMessage.value = '上传失败'
  }
}

const startProcessing = async () => {
  if (!taskId.value) return
  uploadStatus.value = 'processing'
  progress.value = 0
  try {
    await axios.post(`http://127.0.0.1:8000/api/process/${taskId.value}`, config)
    startProgressStream(taskId.value)
  } catch (error) {
    uploadStatus.value = 'error'
  }
}

const startProgressStream = (id: string) => {
  cleanupSSE()
  eventSource = new EventSource(`http://127.0.0.1:8000/api/stream-progress/${id}`)
  eventSource.onmessage = async (event) => {
    const data = JSON.parse(event.data)
    progress.value = data.progress
    if (data.status === 'done') {
      uploadStatus.value = 'done'
      progress.value = 100
      cleanupSSE()
      const reportRes = await axios.get(`http://127.0.0.1:8000/api/report/${taskId.value}`)
      report.value = reportRes.data
    }
  }
}

const downloadFile = () => {
  window.open(`http://127.0.0.1:8000/api/download/${taskId.value}`, '_blank')
}

const exportConfig = () => {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '27txt_config.json'
  a.click()
}

const importConfig = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const imported = JSON.parse(e.target?.result as string)
      Object.assign(config, imported)
    } catch (err) {
      alert('无效的配置文件')
    }
  }
  reader.readAsText(file)
}
</script>

<template>
  <div class="h-screen w-screen flex flex-row overflow-hidden text-slate-900 bg-slate-50 font-sans">
    <main class="w-2/3 flex flex-col border-r border-slate-200 overflow-y-auto bg-white">
      <header class="p-4 border-b border-slate-200 flex justify-between items-center sticky top-0 bg-white/80 backdrop-blur-md z-10">
        <div class="flex items-center space-x-3">
           <div class="w-8 h-8 bg-blue-600 rounded flex items-center justify-center text-white font-bold">27</div>
           <h1 class="text-xl font-bold tracking-tight text-slate-800">27txt 文本格式化工具</h1>
        </div>
        <div class="space-x-2">
          <input type="file" id="import-config" class="hidden" @change="importConfig" accept=".json">
          <button @click="$refs.configInput.click()" class="px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded-md hover:bg-slate-200">导入配置</button>
          <input type="file" ref="configInput" class="hidden" @change="importConfig" accept=".json">
          <button @click="exportConfig" class="px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded-md hover:bg-slate-200">导出配置</button>
        </div>
      </header>

      <div class="flex-1 p-6 space-y-6 max-w-5xl mx-auto w-full">
        <!-- Step 1: Upload -->
        <section class="p-6 bg-slate-50 rounded-xl border border-slate-200 shadow-sm transition-all">
          <div v-if="!taskId" class="flex flex-col items-center py-8 border-2 border-dashed border-slate-300 rounded-lg bg-white hover:border-blue-400 cursor-pointer group" @click="$refs.fileInput.click()">
            <input type="file" ref="fileInput" class="hidden" @change="handleFileUpload" accept=".txt">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10 text-slate-300 group-hover:text-blue-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p class="text-sm font-medium text-slate-600">点击上传待处理的 .txt 文件</p>
          </div>
          <div v-else class="flex items-center justify-between">
             <div class="flex items-center space-x-3">
                <div class="bg-blue-100 p-2 rounded text-blue-600">
                   <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                </div>
                <div>
                   <p class="font-bold text-slate-800">{{ filename }}</p>
                   <p class="text-xs text-slate-500">{{ statusMessage }}</p>
                </div>
             </div>
             <button @click="taskId = ''; uploadStatus = 'idle'" class="text-xs text-blue-600 hover:underline">更换文件</button>
          </div>
          <div v-if="uploadStatus === 'processing' || uploadStatus === 'uploading'" class="mt-4">
             <div class="w-full bg-slate-200 rounded-full h-1.5"><div class="bg-blue-600 h-1.5 rounded-full transition-all" :style="{width: progress+'%'}"></div></div>
          </div>
        </section>

        <!-- Step 2: Configuration & Diff Preview -->
        <div class="grid grid-cols-12 gap-6" :class="{'opacity-50 pointer-events-none': !taskId}">
           <!-- Config Panel -->
           <div class="col-span-4 space-y-6">
              <div class="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
                 <h3 class="font-bold text-sm text-slate-700 mb-4 flex items-center"><span class="w-1 h-4 bg-blue-600 mr-2 rounded"></span>基础清洗</h3>
                 <div class="space-y-3">
                    <label class="flex items-center space-x-2 text-xs text-slate-600 cursor-pointer">
                       <input type="checkbox" v-model="config.formatting.normalize_line_breaks" class="rounded text-blue-600">
                       <span>换行符归一化 (\n)</span>
                    </label>
                    <label class="flex items-center space-x-2 text-xs text-slate-600 cursor-pointer">
                       <input type="checkbox" v-model="config.base_cleaning.remove_control_chars" class="rounded text-blue-600">
                       <span>移除不可见字符/控制符</span>
                    </label>
                    <label class="flex items-center space-x-2 text-xs text-slate-600 cursor-pointer">
                       <input type="checkbox" v-model="config.base_cleaning.remove_html" class="rounded text-blue-600">
                       <span>剥离 HTML 标签</span>
                    </label>
                 </div>
              </div>

              <div class="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
                 <h3 class="font-bold text-sm text-slate-700 mb-4 flex items-center"><span class="w-1 h-4 bg-blue-600 mr-2 rounded"></span>排版格式</h3>
                 <div class="space-y-4">
                    <div class="flex items-center justify-between">
                       <span class="text-xs text-slate-600">空行保留阈值</span>
                       <input type="number" v-model="config.formatting.empty_line_threshold" class="w-12 border rounded px-1 py-0.5 text-xs text-center" min="0" max="5">
                    </div>
                    <label class="flex items-center space-x-2 text-xs text-slate-600 cursor-pointer">
                       <input type="checkbox" v-model="config.formatting.paragraph_indent" class="rounded text-blue-600">
                       <span>首尾去杂 (Trim)</span>
                    </label>
                 </div>
              </div>

              <div class="p-4 bg-white border border-slate-200 rounded-xl shadow-sm">
                 <h3 class="font-bold text-sm text-slate-700 mb-4 flex items-center"><span class="w-1 h-4 bg-blue-600 mr-2 rounded"></span>章节提取</h3>
                 <div class="space-y-3">
                    <label class="flex items-center space-x-2 text-xs text-slate-600 cursor-pointer">
                       <input type="checkbox" v-model="config.chapter.built_in_patterns" class="rounded text-blue-600">
                       <span>内置模式 (第X章/Chapter)</span>
                    </label>
                    <div class="space-y-1">
                       <span class="text-[10px] text-slate-400 uppercase font-bold">自定义正则</span>
                       <input type="text" v-model="config.chapter.custom_regex" placeholder="^第.*章$" class="w-full border rounded px-2 py-1 text-xs font-mono">
                    </div>
                 </div>
              </div>
           </div>

           <!-- Diff Preview -->
           <div class="col-span-8 space-y-4 flex flex-col h-[500px]">
              <div class="flex items-center justify-between px-2">
                 <span class="text-xs font-bold text-slate-500">实时 Diff 预览 (前 200 行)</span>
                 <span class="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-bold">预览模式</span>
              </div>
              <div class="flex-1 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                 <Diff 
                   v-if="taskId && originalSnippet" 
                   mode="split" 
                   theme="light" 
                   language="plaintext" 
                   :prev="originalSnippet" 
                   :current="cleanedSnippet" 
                   class="h-full text-xs"
                 />
                 <div v-else class="h-full flex items-center justify-center text-slate-300 italic text-sm">
                    上传文件后查看 Diff
                 </div>
              </div>
           </div>
        </div>

        <div class="flex flex-col items-center pt-8 border-t border-slate-100">
           <button 
             @click="startProcessing"
             class="px-12 py-4 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all shadow-xl hover:shadow-2xl font-bold text-lg disabled:opacity-50" 
             :disabled="!taskId || uploadStatus === 'processing'">
             开始深度清洗
           </button>
           <div v-if="uploadStatus === 'done'" class="mt-6 flex flex-col items-center animate-bounce">
              <button @click="downloadFile" class="flex items-center px-8 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-bold shadow-lg">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                立即下载清洗后的文本
              </button>
           </div>
        </div>
      </div>
    </main>

    <!-- Right Sidebar: Report & Navigation -->
    <aside class="w-1/3 bg-slate-100/50 flex flex-col overflow-hidden">
       <div class="p-6 overflow-y-auto space-y-6 flex-1">
          <div v-if="uploadStatus === 'done' && report" class="space-y-4">
             <h2 class="font-bold text-lg text-slate-800">清洗报告</h2>
             <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
                <div class="grid grid-cols-2 gap-4 text-sm">
                   <div class="text-slate-500">检测编码</div><div class="font-mono text-right text-blue-600 font-bold uppercase">{{ report.encoding_detected }}</div>
                   <div class="text-slate-500">识别章节</div><div class="text-right font-bold">{{ report.chapters_found }}</div>
                   <div class="text-slate-500">压缩效率</div><div class="text-right font-bold text-green-600">{{ (100 - (report.cleaned_size/report.original_size*100)).toFixed(1) }}%</div>
                   <div class="text-slate-500">原始大小</div><div class="text-right">{{ (report.original_size/1024/1024).toFixed(2) }} MB</div>
                   <div class="text-slate-500">最终大小</div><div class="text-right">{{ (report.cleaned_size/1024/1024).toFixed(2) }} MB</div>
                </div>
             </div>
          </div>

          <div class="space-y-4">
             <div class="flex items-center justify-between">
                <h2 class="font-bold text-lg text-slate-800">目录概览</h2>
                <span class="text-[10px] bg-slate-200 px-2 py-0.5 rounded-full font-bold text-slate-500">{{ chapters.length }} 章节</span>
             </div>
             <div class="bg-white rounded-xl border border-slate-200 shadow-sm min-h-[300px] overflow-hidden">
                <div v-if="chapters.length === 0" class="h-[300px] flex items-center justify-center text-slate-300 text-sm italic p-10 text-center">
                   未检测到章节，尝试在左侧修改匹配模式
                </div>
                <div v-else class="max-h-[600px] overflow-y-auto divide-y divide-slate-100">
                   <div v-for="ch in chapters" :key="ch.line_index" class="p-3 text-xs hover:bg-slate-50 cursor-default flex items-center space-x-2">
                      <span class="w-8 text-slate-300 font-mono text-[10px]">#{{ ch.original_order }}</span>
                      <span class="text-slate-600 truncate">{{ ch.title }}</span>
                   </div>
                </div>
             </div>
          </div>
       </div>
       <footer class="p-4 bg-slate-800 text-slate-400 text-[10px] flex justify-between uppercase tracking-widest font-bold">
          <span>Version 1.0.0</span>
          <span>&copy; 2026 27TXT</span>
       </footer>
    </aside>
  </div>
</template>

<style>
.vue-diff-wrapper { border-radius: 0.75rem; }
.vue-diff-row-delete { background-color: #fee2e2 !important; }
.vue-diff-row-insert { background-color: #dcfce7 !important; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
</style>
