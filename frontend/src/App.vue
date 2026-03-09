<script setup lang="ts">
import { ref, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useRuleStore } from './store/ruleStore'
import { storeToRefs } from 'pinia'

// API base URL
const API_BASE = 'http://localhost:8000'

// Pinia Store
const store = useRuleStore()
const { autoOptions, manualOptions, manualBlacklist, chapterConfig } = storeToRefs(store)

// local states
const task_id = ref('')
const fileUploaded = ref(false)
const fileName = ref('')
const previewLines = ref<string[]>([])
const logEntries = ref<{ time: string, level: string, message: string }[]>([
  { time: new Date().toLocaleTimeString(), level: 'INFO', message: '系统启动成功' }
])
const logVisible = ref(false)
const isUploading = ref(false)
const processingProgress = ref(0)
const isProcessing = ref(false)
const detectedChapters = ref<any[]>([])
const isDeducing = ref(false)
const selectedChapterIndex = ref<number | null>(null)
const isSidebarCollapsed = ref(false)
const previewScrollContainer = ref<HTMLElement | null>(null)

let sseSource: EventSource | null = null

const addLog = (message: string, level = 'INFO') => {
  logEntries.value.push({
    time: new Date().toLocaleTimeString(),
    level,
    message
  })
}

// Manual Filter Logic
const manualInput = ref('')
const parsedChars = ref<any[]>([])

const parseManualInput = () => {
  const chars = Array.from(manualInput.value.slice(0, 200))
  const uniqueChars = [...new Set(chars)]
  parsedChars.value = uniqueChars.map(c => {
    const code = c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')
    const isInvisible = /[\x00-\x1F\x7F-\x9F\u200B-\u200D\uFEFF]/.test(c) || c.trim() === ''
    return { char: c, code: `U+${code}`, isInvisible }
  })
}

const toggleBlacklist = (char: string) => {
  if (manualBlacklist.value.has(char)) {
    manualBlacklist.value.delete(char)
  } else {
    manualBlacklist.value.add(char)
  }
}

// Chapter Logic
const refreshChapterPreview = async () => {
  if (!task_id.value) return
  try {
    const response = await axios.post(`${API_BASE}/api/chapters/preview/${task_id.value}`, {
      pattern: chapterConfig.value.regex || null,
      max_length: 35
    })
    detectedChapters.value = response.data.chapters
  } catch (e) {
    console.error('Failed to preview chapters', e)
  }
}

const handleDeduce = async () => {
  if (!chapterConfig.value.sample) return
  isDeducing.value = true
  try {
    const response = await axios.post(`${API_BASE}/api/chapters/deduce`, {
      samples: [chapterConfig.value.sample]
    })
    chapterConfig.value.regex = response.data.regex
    await refreshChapterPreview()
    ElMessage.success('正则已自动推导')
  } catch (e) {
    ElMessage.error('推导失败')
  } finally {
    isDeducing.value = false
  }
}

const handleChapterChange = async (index: number) => {
  if (!task_id.value || index === null) return
  const currentChapter = detectedChapters.value.find(c => c.index === index)
  if (!currentChapter) return
  
  const nextChapter = detectedChapters.value.find(c => c.index === index + 1)
  
  const startLine = currentChapter.line_number
  const endLine = nextChapter ? nextChapter.line_number : undefined
  
  try {
    const response = await axios.post(`${API_BASE}/api/preview/range/${task_id.value}`, {
      start_line: startLine,
      end_line: endLine
    })
    previewLines.value = response.data.preview
    
    // 重置滚动位置到顶部
    nextTick(() => {
      if (previewScrollContainer.value) {
        previewScrollContainer.value.scrollTop = 0
      }
    })
    
    addLog(`已跳转至章节: ${currentChapter.title}`)
  } catch (e) {
    ElMessage.error('获取章节内容失败')
  }
}

// File Lifecycle
const handleUpload = async (options: any) => {
  const { file } = options
  if (!file.name.endsWith('.txt')) {
    ElMessage.error('只允许上传 .txt 文件')
    return
  }

  isUploading.value = true
  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await axios.post(`${API_BASE}/api/upload`, formData)
    const data = response.data
    
    task_id.value = data.task_id
    fileName.value = data.file_name
    previewLines.value = data.preview
    fileUploaded.value = true
    selectedChapterIndex.value = null
    
    addLog(`文件 ${data.file_name} 上传成功`)
    addLog(`已将 ${data.encoding} 编码改成 utf-8 编码`)
    if (data.has_bom) addLog('已去除 BOM')

    // 处理自动识别的章节
    if (data.detected_regex) {
      chapterConfig.value.regex = data.detected_regex
      detectedChapters.value = data.auto_chapters
      manualOptions.value.chapter = false
      addLog(`✨ 自动识别章节成功：发现 ${data.auto_chapters.length} 个章节`)
      addLog(`已自动应用正则：${data.detected_regex}`)
    } else {
      detectedChapters.value = []
      addLog('未发现匹配的章节范式，您可以尝试手动推导', 'WARN')
    }
    
    addLog('预览区已刷新')
    
  } catch (error: any) {
    addLog(`上传失败: ${error.response?.data?.detail || error.message}`, 'ERROR')
    ElMessage.error('上传失败')
  } finally {
    isUploading.value = false
  }
}

const handleProcess = async () => {
  if (!task_id.value) return

  addLog('开始处理文件...')
  isProcessing.value = true
  processingProgress.value = 0
  
  // Start SSE for progress
  sseSource = new EventSource(`${API_BASE}/api/stream-progress/${task_id.value}`)
  sseSource.onmessage = (event) => {
    processingProgress.value = parseInt(event.data)
    if (processingProgress.value >= 100) {
      sseSource?.close()
    }
  }

  try {
    const response = await axios.post(`${API_BASE}/api/process/${task_id.value}`, {
      options: {
        ...autoOptions.value,
        ...manualOptions.value,
        manual_blacklist: Array.from(manualBlacklist.value),
        chapter_pattern: chapterConfig.value.regex || null,
        chapter_reorder: chapterConfig.value.reorder
      }
    })
    
    const data = response.data
    previewLines.value = data.preview
    detectedChapters.value = data.chapters
    
    // 如果用户之前选择了具体章节，刷新后尝试保持在该章节
    if (selectedChapterIndex.value !== null) {
      await handleChapterChange(selectedChapterIndex.value)
    }
    
    data.logs.forEach((msg: string) => addLog(msg))
    addLog('预览区已刷新为处理后的文件')
    ElMessage.success('处理完成')
    
  } catch (error: any) {
    addLog(`处理失败: ${error.response?.data?.detail || error.message}`, 'ERROR')
    ElMessage.error('处理失败')
  } finally {
    isProcessing.value = false
    if (sseSource) sseSource.close()
  }
}

const handleSave = async () => {
  if (!task_id.value) return
  try {
    const response = await axios.get(`${API_BASE}/api/download/${task_id.value}`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    const contentDisposition = response.headers['content-disposition']
    let downloadName = `${fileName.value.replace('.txt', '-已处理.txt')}`
    if (contentDisposition) {
      const match = contentDisposition.match(/filename\*=UTF-8''(.+)/)
      if (match) downloadName = decodeURIComponent(match[1])
    }
    link.setAttribute('download', downloadName)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    addLog(`已保存：${downloadName}`)
    ElMessage.success(`文件已成功保存: ${downloadName}`)
  } catch (error: any) {
    addLog(`保存失败: ${error.message}`, 'ERROR')
    ElMessage.error('保存失败')
  }
}

onUnmounted(() => {
  if (sseSource) sseSource.close()
})
</script>

<template>
  <div class="h-screen w-screen bg-gray-50 text-gray-800 flex flex-col font-sans overflow-hidden">
    <!-- Header -->
    <header class="h-14 bg-white border-b border-gray-200 flex items-center px-4 shadow-sm shrink-0 gap-3">
      <el-button 
        type="primary" 
        link 
        class="text-xl p-2 hover:bg-gray-100 rounded transition-colors"
        @click="isSidebarCollapsed = !isSidebarCollapsed"
      >
        <el-icon><Expand v-if="isSidebarCollapsed" /><Fold v-else /></el-icon>
      </el-button>
      <h1 class="text-xl font-bold text-blue-600">27 TXT Formatter - 文本清理工具</h1>
    </header>

    <!-- Main Content -->
    <main class="flex-1 flex overflow-hidden">
      <!-- Left: Function Area (2/3) -->
      <section 
        class="transition-all duration-300 ease-in-out flex flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-white"
        :class="isSidebarCollapsed ? 'w-0 opacity-0 invisible overflow-hidden border-0 p-0' : 'w-2/3 p-6 opacity-100 visible'"
      >
        <!-- Upload -->
        <div class="shrink-0 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 transition-colors shadow-sm overflow-hidden">
          <el-upload class="w-full" drag :http-request="handleUpload" :show-file-list="false" :disabled="isUploading || isProcessing">
            <div class="flex flex-col items-center justify-center h-32 py-4 w-full">
              <template v-if="!isUploading">
                <el-icon v-if="!fileUploaded" class="text-4xl text-gray-400 mb-2"><Upload /></el-icon>
                <div v-if="!fileUploaded" class="text-gray-600 font-medium text-lg">📂 点击或拖拽上传文本文件 (Max 50MB)</div>
                <div v-else class="text-blue-600 font-bold text-xl flex items-center justify-center w-full px-6">
                  <el-icon class="mr-2 text-2xl"><Document /></el-icon>
                  <span class="truncate max-w-[70%]">{{ fileName }}</span>
                  <span class="ml-2 text-sm font-normal text-gray-400 shrink-0">(已就绪)</span>
                </div>
              </template>
              <div v-else class="flex items-center gap-3 text-blue-500">
                <el-icon class="is-loading text-2xl"><Loading /></el-icon>
                <span class="text-lg font-medium">正在分析文件...</span>
              </div>
            </div>
          </el-upload>
        </div>

        <!-- Processing Panels -->
        <div class="shrink-0 grid grid-cols-2 gap-4">
          <!-- Automatic Processing -->
          <div class="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h2 class="text-base font-bold mb-3 border-b border-gray-200 pb-2 text-gray-700">⚙️ 自动处理 (Automatic)</h2>
            <div class="space-y-1">
              <el-checkbox v-model="autoOptions.newline" label="换行符归一化 (LF)" class="w-full" />
              <el-checkbox v-model="autoOptions.html" label="HTML 标签清理" class="w-full" />
              <el-checkbox v-model="autoOptions.illegal" label="非法/控制字符过滤" class="w-full" />
              <el-checkbox v-model="autoOptions.fullwidth" label="全半角转换 (数字/字母/标点)" class="w-full" />
              <el-checkbox v-model="autoOptions.paragraph" label="段落清洗 (首尾去杂/自动缩进)" class="w-full" />
              <el-checkbox v-model="autoOptions.emptyline" label="空行压缩 (2行)" class="w-full" />
              <el-checkbox v-model="autoOptions.stitch" label="断句缝合 (修复非正常换行)" class="w-full" />
              <el-checkbox label="去除广告 (暂不支持)" disabled class="w-full opacity-50" />
            </div>
          </div>

          <!-- Manual Processing -->
          <div class="bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h2 class="text-base font-bold mb-3 border-b border-gray-200 pb-2 text-gray-700">🛠️ 手动处理 (Manual)</h2>
            <div class="space-y-3">
              <!-- Inline Manual Filter -->
              <div class="border border-gray-200 rounded-lg overflow-hidden bg-white">
                <div class="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50 transition-colors" @click="manualOptions.manualIllegal = !manualOptions.manualIllegal">
                  <div class="flex items-center gap-2">
                    <el-checkbox v-model="manualOptions.manualIllegal" @click.stop />
                    <span class="text-sm font-medium text-gray-700">手动过滤非法字符</span>
                    <el-tag v-if="manualBlacklist.size > 0" size="small" type="danger" effect="dark">{{ manualBlacklist.size }}</el-tag>
                  </div>
                  <el-icon :class="{'rotate-180': manualOptions.manualIllegal}" class="transition-transform"><ArrowDown /></el-icon>
                </div>
                <div v-if="manualOptions.manualIllegal" class="p-4 border-t border-gray-100 bg-gray-50 space-y-4">
                  <div class="text-[12px] text-blue-600 bg-blue-50 p-2 rounded border border-blue-100 leading-tight">💡 粘贴包含乱码的文本，点击字符加入黑名单：</div>
                  <el-input v-model="manualInput" type="textarea" :rows="2" placeholder="在此粘贴包含异常字符的文本..." size="small" @input="parseManualInput" />
                  <div v-if="parsedChars.length > 0" class="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-1">
                    <button v-for="item in parsedChars" :key="item.code" class="px-2 py-1 rounded border transition-all flex flex-col items-center min-w-[40px]" :class="[manualBlacklist.has(item.char) ? 'bg-red-500 border-red-600 text-white shadow-sm' : item.isInvisible ? 'bg-orange-50 border-orange-200 text-orange-600' : 'bg-white border-gray-200 text-gray-600 hover:border-blue-300']" @click="toggleBlacklist(item.char)">
                      <span class="text-base font-bold leading-none mb-1">{{ item.isInvisible ? '◌' : item.char }}</span>
                      <span class="text-[9px] font-mono opacity-50">{{ item.code }}</span>
                    </button>
                  </div>
                  <div v-if="manualBlacklist.size > 0" class="flex justify-between items-center pt-2 border-t border-gray-200">
                    <span class="text-[10px] text-gray-400">已选中 {{ manualBlacklist.size }} 个字符</span>
                    <el-button size="small" link type="danger" @click="manualBlacklist.clear(); manualInput=''; parsedChars=[]">全部清空</el-button>
                  </div>
                </div>
              </div>

              <!-- Inline Chapter Recognition -->
              <div class="border border-gray-200 rounded-lg overflow-hidden bg-white">
                <div class="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50 transition-colors" @click="manualOptions.chapter = !manualOptions.chapter">
                  <div class="flex items-center gap-2">
                    <el-checkbox v-model="manualOptions.chapter" @click.stop />
                    <span class="text-sm font-medium text-gray-700">章节识别与序号重排</span>
                    <el-tag v-if="detectedChapters.length > 0" size="small" type="success" effect="dark">{{ detectedChapters.length }}</el-tag>
                  </div>
                  <el-icon :class="{'rotate-180': manualOptions.chapter}" class="transition-transform"><ArrowDown /></el-icon>
                </div>
                <div v-if="manualOptions.chapter" class="p-4 border-t border-gray-100 bg-gray-50 space-y-4">
                  <div class="space-y-2 bg-white p-3 rounded border border-gray-200 shadow-sm">
                    <div class="text-xs font-bold text-blue-600 mb-1 flex items-center gap-1">✨ 智能引导：输入样例推导正则</div>
                    <div class="flex gap-2">
                      <el-input v-model="chapterConfig.sample" placeholder="例如: ☆卷二 chap124 陨落☆" size="small" class="flex-1" />
                      <el-button type="primary" size="small" @click="handleDeduce" :loading="isDeducing">推导</el-button>
                    </div>
                  </div>
                  <div class="space-y-1">
                    <div class="text-[11px] text-gray-400 font-bold uppercase tracking-wider px-1">正则表达式</div>
                    <el-input v-model="chapterConfig.regex" placeholder="留空使用内置正则库..." size="small" @input="refreshChapterPreview" />
                  </div>
                  <div class="flex items-center justify-between px-1">
                    <span class="text-xs text-gray-600 font-medium">章节序号重排</span>
                    <el-switch v-model="chapterConfig.reorder" size="small" />
                  </div>
                  <div v-if="detectedChapters.length > 0" class="space-y-2">
                    <div class="text-[11px] text-gray-400 font-bold uppercase tracking-wider px-1">实时目录预览 (前5条)</div>
                    <div class="bg-white border border-gray-200 rounded p-2 max-h-32 overflow-y-auto shadow-inner">
                      <div v-for="ch in detectedChapters.slice(0, 5)" :key="ch.index" class="text-[12px] text-gray-600 py-1 border-b border-gray-50 last:border-0 truncate">
                        <span class="text-blue-500 font-mono mr-2">{{ String(ch.index).padStart(2, '0') }}.</span>
                        {{ ch.title }}
                      </div>
                      <div v-if="detectedChapters.length > 5" class="text-[10px] text-gray-400 text-center pt-1 italic">... 共 {{ detectedChapters.length }} 个章节</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Start Process Button & Progress -->
        <div class="bg-gray-50 p-4 rounded-lg border border-gray-200 shadow-sm space-y-3">
          <el-button type="success" size="large" class="w-full h-16 text-xl font-bold" @click="handleProcess" :disabled="!fileUploaded || isProcessing" :loading="isProcessing">
            🚀 开始处理
          </el-button>
          <el-progress v-if="isProcessing" :percentage="processingProgress" :stroke-width="10" striped striped-flow />
        </div>

        <!-- Save Button -->
        <div class="bg-gray-50 p-4 rounded-lg border border-gray-200 shadow-sm">
          <el-button type="warning" size="large" class="w-full h-12 text-lg font-bold" @click="handleSave" :disabled="!fileUploaded || isProcessing">💾 保存处理后的文件</el-button>
        </div>

        <!-- Log Panel -->
        <div class="mt-auto">
          <div class="bg-gray-100 rounded-t-lg border-t border-x border-gray-200 p-2 cursor-pointer hover:bg-gray-200 transition-colors flex justify-between items-center shadow-sm" @click="logVisible = !logVisible">
            <span class="text-xs font-bold text-gray-600 uppercase tracking-wider">▼ 日志信息 (Log)</span>
            <span class="text-xs text-gray-400">{{ logVisible ? '点击折叠' : '点击展开' }}</span>
          </div>
          <div v-show="logVisible" class="bg-gray-50 p-3 h-32 overflow-y-auto border border-gray-200 font-mono text-xs">
            <div v-for="(log, index) in logEntries" :key="index" class="mb-1 border-b border-gray-100 pb-1 last:border-0">
              <span class="text-gray-400">[{{ log.time }}]</span>
              <span :class="{'text-blue-600': log.level === 'INFO', 'text-orange-500': log.level === 'WARN', 'text-red-600': log.level === 'ERROR'}" class="ml-2 font-bold uppercase">{{ log.level }}:</span>
              <span class="ml-2 text-gray-700">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Right: Preview Area -->
      <section class="flex-1 p-4 bg-gray-100 flex flex-col overflow-hidden transition-all duration-300 ease-in-out">
        <div class="flex items-center justify-between mb-3 shrink-0 px-1 gap-2">
          <h2 class="text-base font-bold text-gray-700 uppercase tracking-wide whitespace-nowrap">📄 文本预览</h2>
          <el-select 
            v-model="selectedChapterIndex" 
            placeholder="按章节读取" 
            size="small" 
            class="flex-1"
            :disabled="detectedChapters.length === 0"
            @change="handleChapterChange"
          >
            <el-option
              v-for="item in detectedChapters"
              :key="item.index"
              :label="item.title"
              :value="item.index"
            />
          </el-select>
          <span class="text-xs text-blue-600 font-bold px-2 py-1 bg-blue-50 rounded truncate max-w-[80px]" v-if="fileUploaded" :title="fileName">{{ fileName }}</span>
        </div>
        <div ref="previewScrollContainer" class="flex-1 bg-white border border-gray-200 rounded-xl font-mono text-sm overflow-y-auto text-gray-600 leading-relaxed shadow-inner custom-scrollbar">
          <div v-if="!fileUploaded && !isProcessing" class="h-full flex flex-col items-center justify-center text-gray-400 italic gap-2">
            <el-icon class="text-4xl opacity-20 mb-1"><Document /></el-icon>
            请上传文件以显示预览
          </div>
          <div v-else-if="isProcessing" class="h-full flex items-center justify-center text-blue-400 italic gap-2 animate-pulse">正在处理中 ({{ processingProgress }}%)...</div>
          <div v-else class="p-4 min-w-full">
            <div v-for="(line, idx) in previewLines" :key="idx" class="flex hover:bg-blue-50 transition-colors group">
              <span class="w-10 shrink-0 text-right pr-3 text-gray-300 select-none group-hover:text-blue-200">{{ idx + 1 }}</span>
              <span class="whitespace-pre-wrap break-all flex-1">{{ line || ' ' }}</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style>
/* 覆盖 Element Plus 的全局样式 */
:root { --el-color-primary: #2563eb; --el-color-success: #16a34a; --el-color-warning: #ea580c; }
.el-checkbox { --el-checkbox-text-color: #374151; --el-checkbox-checked-text-color: #2563eb; margin-right: 0 !important; height: 32px; }
.el-checkbox__label { font-size: 14px; }
.el-upload-dragger { 
  background-color: transparent !important; 
  border: none !important; 
  padding: 0 !important; 
  width: 100% !important;
  height: 100% !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.el-upload-dragger:hover { border: none !important; }
body { margin: 0; padding: 0; overflow: hidden; background-color: #f9fafb; }
#app { width: 100vw; height: 100vh; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; border: 2px solid transparent; background-clip: content-box; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
::-webkit-scrollbar-track { background: #f1f5f9; }
</style>
