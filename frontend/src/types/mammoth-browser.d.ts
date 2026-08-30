declare module 'mammoth/mammoth.browser' {
  interface ExtractRawTextOptions {
    arrayBuffer: ArrayBuffer
  }

  interface ExtractRawTextResult {
    value: string
    messages?: unknown[]
  }

  export function extractRawText(options: ExtractRawTextOptions): Promise<ExtractRawTextResult>
}

