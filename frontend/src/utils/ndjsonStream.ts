export const readNdjsonStream = async <T>(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: T) => void | Promise<void>,
) => {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const text = line.trim()
      if (!text) continue
      await onEvent(JSON.parse(text) as T)
    }
  }

  const tail = buffer.trim()
  if (tail) {
    await onEvent(JSON.parse(tail) as T)
  }
}