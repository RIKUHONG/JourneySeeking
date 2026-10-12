// Desktop/mobile smoke checks through Chrome's DevTools protocol.

import { spawn } from 'node:child_process'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const outputDir = process.argv[2] || tmpdir()
const profile = await mkdtemp(join(tmpdir(), 'p2-10-chrome-'))
const chrome = spawn(chromePath, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'http://127.0.0.1:5173/'
], { stdio: 'ignore', windowsHide: true })

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
let ws
let nextId = 1
const pending = new Map()

async function send(method, params = {}) {
  const id = nextId++
  const answer = new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
  ws.send(JSON.stringify({ id, method, params }))
  return answer
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true
  })
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text)
  return response.result.value
}

async function navigate(url) {
  await send('Page.navigate', { url })
  await sleep(1500)
}

async function snapshot(name, width, height) {
  await send('Emulation.setDeviceMetricsOverride', {
    width, height, deviceScaleFactor: 1, mobile: width < 600
  })
  await navigate('http://127.0.0.1:5173/result')
  const metrics = await evaluate(`(() => {
    const root = document.documentElement
    const images = [...document.querySelectorAll('.places img')]
    return {
      title: document.title,
      viewport_width: window.innerWidth,
      document_width: root.scrollWidth,
      has_itinerary: !!document.querySelector('#overview'),
      day_panels: document.querySelectorAll('.ant-collapse-item').length,
      spot_images: images.length,
      loaded_images: images.filter(img => img.complete && img.naturalWidth > 0).length,
      toolbar_buttons: document.querySelectorAll('.toolbar button').length
    }
  })()`)
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const path = resolve(outputDir, `p2-10-${name}.png`)
  await writeFile(path, Buffer.from(shot.data, 'base64'))
  return { ...metrics, screenshot: path, passed: metrics.has_itinerary && metrics.day_panels === 3 && metrics.document_width <= width }
}

try {
  let port
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0])
      break
    } catch { await sleep(100) }
  }
  if (!port) throw new Error('Chrome DevTools port was unavailable')
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
  const page = pages.find(item => item.type === 'page')
  if (!page) throw new Error('Chrome page was unavailable')
  ws = new WebSocket(page.webSocketDebuggerUrl)
  ws.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (!data.id || !pending.has(data.id)) return
    const { resolve, reject } = pending.get(data.id)
    pending.delete(data.id)
    data.error ? reject(new Error(data.error.message)) : resolve(data.result)
  })
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', reject, { once: true })
  })
  await send('Page.enable')
  await send('Runtime.enable')
  const fixture = JSON.parse(await readFile('docs/fixtures/trip-generate-hangzhou-20260929.json', 'utf8'))
  await evaluate(`sessionStorage.setItem('itinerary', ${JSON.stringify(JSON.stringify(fixture))})`)
  const desktop = await snapshot('desktop', 1440, 900)
  const mobile = await snapshot('mobile', 390, 844)
  await evaluate("document.querySelector('#places')?.scrollIntoView()")
  await sleep(400)
  const placesShot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const mobilePlaces = resolve(outputDir, 'p2-10-mobile-places.png')
  await writeFile(mobilePlaces, Buffer.from(placesShot.data, 'base64'))
  await evaluate("document.querySelectorAll('#days .ant-collapse-header')[1]?.click()")
  await sleep(400)
  const dailyPanel = await evaluate("document.querySelectorAll('#days .ant-collapse-item')[1]?.classList.contains('ant-collapse-item-active')")
  await navigate('http://127.0.0.1:5173/')
  await evaluate("document.querySelector('button[type=submit]')?.click()")
  await sleep(500)
  const emptyForm = await evaluate(`(() => ({
    field_errors: document.querySelectorAll('.ant-form-item-explain-error').length,
    prompt_visible: !!document.querySelector('.ant-message-notice')
  }))()`)
  console.log(JSON.stringify({ desktop, mobile, mobile_places: mobilePlaces, daily_panel_opened: dailyPanel, empty_form: emptyForm }, null, 2))
} finally {
  if (ws) ws.close()
  chrome.kill()
  if (profile.startsWith(tmpdir())) await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
}
