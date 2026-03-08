import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useRuleStore = defineStore('ruleConfig', () => {
  const autoOptions = ref({
    newline: true,
    html: true,
    illegal: true,
    fullwidth: true,
    paragraph: true,
    emptyline: true,
    stitch: true,
  })

  const manualOptions = ref({
    manualIllegal: false,
    chapter: false,
  })

  const manualBlacklist = ref<Set<string>>(new Set())
  
  const chapterConfig = ref({
    regex: '',
    reorder: false,
    sample: ''
  })

  return {
    autoOptions,
    manualOptions,
    manualBlacklist,
    chapterConfig
  }
})
