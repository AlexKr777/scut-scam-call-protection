import type { AlertsPage, BackendHealth, ConversationDetail, DiagnosticName, HistoryPage, PairingPayload, ScutMode, ScutStatus } from './api/contracts'

declare global {
  interface Window {
    scut: {
      getHealth(): Promise<BackendHealth>
      getStatus(): Promise<ScutStatus>
      getRealtimeEndpoint(): Promise<string>
      notifyVisualReady?(): void
      resizeFloatingBar?(size: { width: 196 | 332; height: 48 | 58 }): Promise<void>
      showMainWindow?(): Promise<void>
      notifyFloatingBarReady?(): void
      setMode(mode: ScutMode): Promise<ScutStatus>
      createPairing(): Promise<PairingPayload>
      runDiagnostic(name: DiagnosticName): Promise<ScutStatus>
      testAndroidAlert(): Promise<{ ok?: boolean }>
      submitDiagnosticTranscript(text: string): Promise<{ risk?: string; reason?: string }>
      getRecordingUrl(): Promise<string>
      getHistory(cursor?: string): Promise<HistoryPage>
      getAlerts(cursor?: string): Promise<AlertsPage>
      getConversation(id: string): Promise<{ conversation: ConversationDetail }>
      deleteConversation(id: string): Promise<{ deleted: boolean }>
    }
  }
}

export {}
