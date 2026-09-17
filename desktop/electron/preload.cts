import { contextBridge, ipcRenderer } from 'electron'

// Expose one method per allowed backend operation instead of the ipcRenderer object.
// Source: https://www.electronjs.org/docs/latest/tutorial/tutorial-preload#ipc-security
contextBridge.exposeInMainWorld('scut', {
  getHealth: () => ipcRenderer.invoke('scut:get-health'),
  getStatus: () => ipcRenderer.invoke('scut:get-status'),
  getRealtimeEndpoint: () => ipcRenderer.invoke('scut:get-realtime-endpoint'),
  resizeFloatingBar: (size: { width: 196 | 332, height: 48 | 58 }) => ipcRenderer.invoke('scut:resize-floating-bar', size),
  showMainWindow: () => ipcRenderer.invoke('scut:show-main-window'),
  notifyVisualReady: () => ipcRenderer.send('scut:visual-ready'),
  notifyFloatingBarReady: () => ipcRenderer.send('scut:floating-bar-ready'),
  setMode: (mode: 'OFF' | 'TEST' | 'PROTECT') => ipcRenderer.invoke('scut:set-mode', mode),
  createPairing: () => ipcRenderer.invoke('scut:create-pairing'),
  runDiagnostic: (name: 'capture' | 'earbuds' | 'network' | 'predemo' | 'guarded-transcription') => ipcRenderer.invoke('scut:run-diagnostic', name),
  testAndroidAlert: () => ipcRenderer.invoke('scut:test-android-alert'),
  submitDiagnosticTranscript: (text: string) => ipcRenderer.invoke('scut:submit-diagnostic-transcript', text),
  getRecordingUrl: () => ipcRenderer.invoke('scut:get-recording-url'),
  getHistory: (cursor?: string) => ipcRenderer.invoke('scut:get-history', cursor),
  getAlerts: (cursor?: string) => ipcRenderer.invoke('scut:get-alerts', cursor),
  getConversation: (id: string) => ipcRenderer.invoke('scut:get-conversation', id),
  deleteConversation: (id: string) => ipcRenderer.invoke('scut:delete-conversation', id),
})
