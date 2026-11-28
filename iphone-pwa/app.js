// The JARVIS iPhone page.
//
// The page holds the pairing secret in memory only. It signs every bridge
// request with the shared scheme, so the phone never holds a provider key
// and never talks to a provider directly.
//
// Everything that can fail on a phone is treated as normal: no network, a
// locked screen, a browser without voice and a browser without
// notifications are all handled without breaking the page.

import { BridgeClient, BridgeError, signCanonical } from './js/bridge.js';
import { ChatTranscript, renderTranscript } from './js/chat.js';
import { KINDS, Outbox, createIndexedDbStore } from './js/offline.js';
import { parsePairingLink, parsePairingPayload } from './js/pairing.js';
import { decodeQrFromFile } from './js/qr.js';
import { backupTask } from './js/history.js';
import {
  chooseLanguage, defaultLanguage, recognitionSupported, speak, startListening,
  synthesisSupported,
} from './js/speech.js';

const $ = (id) => document.getElementById(id);

/**
 * How often the queued work is tried while the page is open.
 *
 * iOS Safari has no Background Sync, so the queue is only ever sent while the
 * app is in front. This is the slow heartbeat that covers the case where the
 * `online` event never came.
 */
const FLUSH_INTERVAL_MS = 30000;
const CHAT_COMMANDS = new Map([
  ['/disk', diskSpaceTask],
  ['command check disk space', diskSpaceTask],
  ['கமாண்ட் டிஸ்க் ஸ்பேஸ்', diskSpaceTask],
  ['/backup', backupTask],
  ['command back up history', backupTask],
]);

const state = {
  client: null,
  transcript: new ChatTranscript(),
  outbox: new Outbox(),
  listening: null,
  call: null,
  camera: null,
  cameraRequest: null,
  speakAnswers: false,
  timer: null,
  flushTimer: null,
  lastError: '',
};

const transcriptElement = $('transcript');

function say(message, kind = '') {
  const element = $('banner');
  if (!message) {
    element.hidden = true;
    element.textContent = '';
    return;
  }
  element.hidden = false;
  element.textContent = message;
  element.className = `banner${kind ? ` ${kind}` : ''}`;
}

function setStatus(id, message, kind = '') {
  const element = $(id);
  element.textContent = message;
  element.className = `status${kind ? ` ${kind}` : ''}`;
}

function formatPercent(value) {
  return typeof value === 'number' ? `${value.toFixed(0)}%` : 'unknown';
}

function formatGigabytes(value) {
  return typeof value === 'number' ? `${value.toFixed(1)} GB` : 'unknown';
}

// --------------------------------------------------------------- connection

/** Build a client from the fields on the page. */
function buildClient() {
  const url = $('url').value.trim();
  const key = $('key').value.trim();
  const secret = $('secret').value;
  return new BridgeClient({ baseUrl: url, keyId: key, secret });
}

async function connect() {
  try {
    state.client = buildClient();
  } catch (error) {
    setStatus('pairStatus', error.message, 'error');
    return;
  }
  $('connectionLabel').textContent = 'Connecting…';
  setStatus('pairStatus', 'Checking the PC…');
  try {
    const status = await state.client.status();
    setStatus('pairStatus', `Connected to ${status.hostname || 'the PC'}.`, 'ok');
    showStatus(status);
    // The PC is there, so the work that was kept while it was not reachable
    // can go out now.
    await flushOutbox();
    await refreshAll();
  } catch (error) {
    $('connectionLabel').textContent = 'Reconnect PC';
    setStatus('pairStatus', error.message, 'error');
    say(error.message);
  }
}

const WAKE_STORAGE = 'jarvis.siri.wake.v1';

async function enableSiriWake() {
  try {
    const client = state.client;
    if (!client || new URL(client.baseUrl).origin !== location.origin || location.protocol !== 'https:') {
      throw new Error('Connect in Safari on the PC’s HTTPS Phone Remote page first.');
    }
    await client.status();
    const secret = await signCanonical('JARVIS/iphone/wake/v1', client.secret);
    if (state.client !== client) return;
    localStorage.setItem(WAKE_STORAGE, JSON.stringify({ keyId: client.keyId, secret }));
    const link = new URL(location.pathname, location.origin);
    link.hash = 'wake';
    $('siriLink').value = link.href;
    $('siriLink').hidden = false;
    try {
      await navigator.clipboard.writeText(link.href);
      say('Wake link copied. Use it in a Siri shortcut with Open URLs.');
    } catch {
      $('siriLink').select();
      say('Copy the wake link and use it in a Siri shortcut with Open URLs.');
    }
  } catch (error) {
    say(error.message, 'error');
  }
}

async function handleSiriWake() {
  if (globalThis.location?.hash !== '#wake') return;
  history.replaceState(null, '', location.pathname);
  try {
    const saved = JSON.parse(localStorage.getItem(WAKE_STORAGE));
    if (!saved) throw new Error('Pair this Safari browser, then choose Set up Siri wake.');
    const client = new BridgeClient({ ...saved, baseUrl: location.origin });
    await client.request('POST', '/api/wake');
    say('Wake request received by your PC.', 'ok');
  } catch (error) {
    say(error.message, 'error');
  }
}

function forgetSecret() {
  localStorage.removeItem(WAKE_STORAGE);
  $('siriLink').hidden = true;
  $('siriLink').value = '';
  endPhoneCall();
  state.client = null;
  $('secret').value = '';
  $('connectionLabel').textContent = 'Connect PC';
  setStatus('pairStatus', 'The secret was cleared from this page.');
  stopWatching();
}

function applyPairing(text) {
  try {
    const pairing = text.trim().startsWith('https://')
      ? parsePairingLink(text.trim()) : parsePairingPayload(text);
    $('url').value = pairing.bridgeUrl;
    $('key').value = pairing.keyId;
    $('secret').value = pairing.secret;
    setStatus('pairStatus', 'Pairing code read. Tap Connect to use it.', 'ok');
    return true;
  } catch (error) {
    setStatus('pairStatus', error.message, 'error');
    return false;
  }
}

async function scanPairing(file) {
  setStatus('pairStatus', 'Reading the picture…');
  try {
    const text = await decodeQrFromFile(file);
    if (!text) {
      setStatus('pairStatus', 'No pairing code was found in that picture.', 'error');
      return;
    }
    if (!applyPairing(text)) {
      return;
    }
    await connect();
  } catch (error) {
    setStatus('pairStatus', error.message, 'error');
  }
}

// ------------------------------------------------------------------- status

function showStatus(status) {
  $('connectionLabel').textContent = status.state === 'stopped' ? 'PC stopped' : 'PC connected';
  const fields = {
    state: status.state || '—',
    hostname: status.hostname || '—',
    platform: status.platform || '—',
    cpu_percent: formatPercent(status.cpu_percent),
    memory_percent: formatPercent(status.memory_percent),
    gpu_percent: formatPercent(status.gpu_percent),
    disk_free_gb: formatGigabytes(status.disk_free_gb),
    jobs: `${status.queued_jobs ?? 0} queued · ${status.running_jobs ?? 0} running`,
  };
  for (const [name, value] of Object.entries(fields)) {
    const element = document.querySelector(`[data-field="${name}"]`);
    if (element) {
      element.textContent = value;
    }
  }
}

async function refreshStatus() {
  if (!state.client) {
    return;
  }
  try {
    const status = await state.client.status();
    showStatus(status);
    state.lastError = '';
  } catch (error) {
    $('connectionLabel').textContent = 'PC unavailable';
    handleFailure(error, 'status');
  }
}

function startWatching() {
  stopWatching();
  state.timer = setInterval(refreshStatus, 15000);
}

function stopWatching() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

// --------------------------------------------------------------------- chat

function drawChat() {
  renderTranscript(state.transcript, transcriptElement);
}

async function sendMessage(text, { images } = {}) {
  const message = (text || '').trim();
  if (!message) {
    return;
  }
  if (!state.client) {
    setStatus('chatStatus', 'Connect to the PC first.', 'error');
    return;
  }
  const call = state.call;
  const command = message.toLowerCase().replace(/[.!?]+$/, '');
  const asksToLook = /^(?:look|look at this|look through the camera|what is this|what do you see|what object is this|ithu enna|இந்தப் பொருள் என்ன|இந்த பொருள் என்ன|பார்|பாரு|இதைப் பார்|இதை பாரு|இது என்ன|நான் என்ன காட்டுறேன்|camera paaru|கேமராவில் பார்)[.!?]*$/iu.test(message);
  if (!images && (asksToLook || (call?.mode === 'video' && !CHAT_COMMANDS.has(command)))) {
    const view = $('liveCameraView');
    if (!state.camera || !view.videoWidth) {
      setStatus('chatStatus', 'Turn on the phone camera and wait for the preview.', 'error');
      return;
    }
    if (!$('consent').checked) {
      setStatus('chatStatus', 'Allow Gemini for this camera question first.', 'error');
      return;
    }
    try {
      images = [cameraFrame(view, view.videoWidth, view.videoHeight)];
    } catch {
      setStatus('chatStatus', 'Could not read the current camera frame. Try again.', 'error');
      return;
    }
  }
  state.transcript.add('person', message);
  drawChat();
  const task = images ? undefined : CHAT_COMMANDS.get(command);
  if (task) {
    await submitTaskRequest(task());
    return;
  }
  setStatus('chatStatus', 'Thinking…');
  const consent = $('consent').checked;
  try {
    const answer = await state.client.chat(message, { consent, images });
    state.transcript.add('jarvis', answer.text || '(no answer)');
    drawChat();
    setStatus('chatStatus', `Answered by ${answer.provider || 'the PC'}.`, 'ok');
    if (state.speakAnswers || (call && state.call === call)) {
      speak(answer.text || '', {
        lang: chooseLanguage(answer.text || '', { current: chosenVoiceLanguage() }),
      });
    }
    // The work is done, so a copy that waits in the queue must not be sent
    // a second time.
    if (!images) await state.outbox.discard(KINDS.CHAT, { message, consent });
  } catch (error) {
    const kept = !images && await keepForLater(error, KINDS.CHAT, { message, consent });
    handleFailure(error, 'chat', { kept });
    state.transcript.add('system', error.message);
    drawChat();
  }
}

function cameraFrame(source, width, height) {
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, 400 / Math.max(width, height));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  const image = canvas.toDataURL('image/jpeg', 0.5).split(',')[1];
  if (!image || image.length > 26_000) throw new Error('Camera frame is too large');
  return image;
}

function stopPhoneCamera() {
  state.cameraRequest = null;
  if (state.camera) {
    for (const track of state.camera.getTracks()) track.stop();
  }
  state.camera = null;
  const view = $('liveCameraView');
  view.srcObject = null;
  view.hidden = true;
  $('phoneCamera').textContent = 'Camera on';
}

async function togglePhoneCamera() {
  if (state.camera || state.cameraRequest) {
    stopPhoneCamera();
    return;
  }
  const request = {};
  let stream;
  state.cameraRequest = request;
  $('phoneCamera').textContent = 'Cancel camera';
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } }, audio: false,
    });
    if (state.cameraRequest !== request) {
      for (const track of stream.getTracks()) track.stop();
      return;
    }
    state.cameraRequest = null;
    state.camera = stream;
    const view = $('liveCameraView');
    view.srcObject = stream;
    view.hidden = false;
    $('phoneCamera').textContent = 'Camera off';
    await view.play();
  } catch {
    if (state.cameraRequest === request || (stream && state.camera === stream)) {
      stopPhoneCamera();
      setStatus('chatStatus', 'The phone camera could not start. Check browser permission.', 'error');
    }
  }
}

function showCallStatus() {
  const mode = state.call?.mode;
  $('callStatus').textContent = mode === 'video' ? 'Video call · tap Listen to speak'
    : mode === 'audio' ? 'Audio call · tap Listen to speak' : 'Call ended';
  $('audioCall').disabled = !!mode;
  $('videoCall').disabled = !!mode;
  $('endCall').disabled = !mode;
}

function endPhoneCall() {
  state.call = null;
  const listening = state.listening;
  state.listening = null;
  if (listening) listening.stop();
  $('listen').textContent = 'Listen';
  stopPhoneCamera();
  globalThis.speechSynthesis?.cancel();
  showCallStatus();
}

async function startPhoneCall(mode) {
  if (!state.client) {
    setStatus('callStatus', 'Pair and connect to the PC first.', 'error');
    return;
  }
  const call = { mode };
  state.call = call;
  showCallStatus();
  if (mode === 'audio') {
    if (!state.listening && recognitionSupported()) toggleListening();
    return;
  }
  if (!state.camera) await togglePhoneCamera();
  if (state.call === call && !state.camera) {
    endPhoneCall();
    setStatus('callStatus', 'The video call needs phone camera access.', 'error');
  }
}

function videoEvent(video, name) {
  return new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timer);
      video.removeEventListener(name, ready);
      video.removeEventListener('error', failed);
      if (error) reject(error); else resolve();
    };
    const ready = () => finish();
    const failed = () => finish(new Error('The video could not be opened.'));
    const timer = setTimeout(failed, 5000);
    video.addEventListener(name, ready);
    video.addEventListener('error', failed);
  });
}

async function clipFrames(url) {
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  try {
    const loaded = videoEvent(video, 'loadedmetadata');
    video.src = url;
    await loaded;
    if (!Number.isFinite(video.duration) || video.duration <= 0 || video.duration > 30) {
      throw new Error('Choose a video up to 30 seconds long.');
    }
    const frames = [];
    for (const portion of [0.15, 0.5, 0.85]) {
      const ready = videoEvent(video, 'seeked');
      video.currentTime = video.duration * portion;
      await ready;
      frames.push(cameraFrame(video, video.videoWidth, video.videoHeight));
    }
    return frames;
  } finally {
    video.removeAttribute('src');
    video.load();
  }
}

async function askAboutCamera(file, isClip) {
  if (!state.client || !$('consent').checked) {
    setStatus('chatStatus', 'Connect to the PC and allow Gemini for this camera request first.', 'error');
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    setStatus('chatStatus', 'Choose a camera file smaller than 20 MB.', 'error');
    return;
  }
  const url = URL.createObjectURL(file);
  try {
    let images;
    if (isClip) {
      images = await clipFrames(url);
    } else {
      const source = new Image();
      source.src = url;
      await source.decode();
      images = [cameraFrame(source, source.naturalWidth, source.naturalHeight)];
    }
    const question = $('message').value.trim() || (isClip
      ? 'இந்த வீடியோவின் மூன்று படங்களில் என்ன நடக்கிறது? தமிழில் சொல்லு.'
      : 'இந்தப் படத்தில் என்ன தெரிகிறது? தமிழில் சொல்லு.');
    await sendMessage(question, { images });
  } catch {
    setStatus('chatStatus', isClip ? 'Try a shorter video under 30 seconds.'
      : 'Could not read this photo. Try a JPEG photo.', 'error');
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** The language the person chose for the voice, or the one of the phone. */
function chosenVoiceLanguage() {
  const picker = $('voiceLanguage');
  const chosen = picker && picker.value;
  return chosen || defaultLanguage();
}

function toggleListening() {
  if (state.listening) {
    state.listening.stop();
    state.listening = null;
    $('listen').textContent = 'Listen';
    return;
  }
  if (!recognitionSupported()) {
    setStatus('chatStatus', 'This browser cannot recognise speech.', 'error');
    return;
  }
  try {
    const call = state.call;
    state.listening = startListening({
      lang: chosenVoiceLanguage(),
      onResult: (text) => {
        state.listening = null;
        $('listen').textContent = 'Listen';
        if (text && (!call || state.call === call)) {
          $('message').value = text;
          sendMessage(text);
        }
      },
      onError: (error) => {
        state.listening = null;
        $('listen').textContent = 'Listen';
        setStatus('chatStatus', `Voice input failed: ${error}`, 'error');
      },
      onEnd: () => {
        state.listening = null;
        $('listen').textContent = 'Listen';
      },
    });
    $('listen').textContent = 'Stop';
    setStatus('chatStatus', 'Listening…');
  } catch (error) {
    setStatus('chatStatus', error.message, 'error');
  }
}

// -------------------------------------------------------------------- tasks

function drawJobs(jobs) {
  const list = $('jobs');
  list.textContent = '';
  for (const job of jobs) {
    const item = document.createElement('li');
    const badge = document.createElement('span');
    badge.className = `badge badge-${String(job.state || '').toLowerCase()}`;
    badge.textContent = job.state || 'UNKNOWN';
    const title = document.createElement('span');
    title.textContent = job.title || job.id;
    item.append(badge, title);
    const details = job.error || (Array.isArray(job.outputs) ? job.outputs.join(' ') : '');
    if (details) {
      const result = document.createElement('p');
      result.textContent = details;
      item.append(result);
    }
    const progress = document.createElement('div');
    progress.className = 'progress';
    const bar = document.createElement('span');
    bar.style.width = `${Math.round((Number(job.progress) || 0) * 100)}%`;
    progress.append(bar);
    item.append(progress);
    if (job.state === 'QUEUED' || job.state === 'RUNNING') {
      const cancel = document.createElement('button');
      cancel.className = 'ghost';
      cancel.textContent = 'Cancel';
      cancel.addEventListener('click', () => cancelJob(job.id));
      item.append(cancel);
    }
    list.append(item);
  }
}

async function refreshJobs() {
  if (!state.client) {
    return;
  }
  try {
    drawJobs(await state.client.jobs());
  } catch (error) {
    handleFailure(error, 'jobs');
  }
}

function diskSpaceTask() {
  return { kind: 'CUSTOM', title: 'Check PC disk space',
    payload: JSON.stringify({ action: 'check_disk_space' }), requireApproval: true };
}

async function submitTaskRequest(task) {
  if (!state.client) return false;
  try {
    await state.client.submitJob(task);
    setStatus('chatStatus', 'The task was sent. Approve it on the PC.', 'ok');
    // The task is on the PC now, so a copy that waits in the queue must not
    // be sent a second time.
    await state.outbox.discard(KINDS.TASK, task);
    await refreshJobs();
    return true;
  } catch (error) {
    const kept = await keepForLater(error, KINDS.TASK, task);
    handleFailure(error, 'tasks', { kept });
    return false;
  }
}

async function submitTask() {
  const title = $('taskTitle').value.trim();
  const payload = $('taskPayload').value;
  if (await submitTaskRequest({ kind: 'CUSTOM', title, payload, requireApproval: true })) {
    $('taskTitle').value = '';
    $('taskPayload').value = '';
  }
}
/**
 * Ask the PC to back up the conversation history.
 *
 * The history itself is never sent over the bridge. The PC makes the
 * backup, keeps it, and the phone is told the name, the size and the
 * checksum of what was made. The owner approves it on the PC.
 */
async function backupHistory() {
  if (!state.client) {
    setStatus('chatStatus', 'The PC cannot be reached right now.', 'warn');
    return;
  }
  const task = backupTask();
  try {
    await state.client.submitJob(task);
    await state.outbox.discard(KINDS.TASK, task);
    setStatus('chatStatus', 'The backup was asked for. Approve it on the PC.', 'ok');
    await refreshJobs();
  } catch (error) {
    const kept = await keepForLater(error, KINDS.TASK, task);
    handleFailure(error, 'tasks', { kept });
  }
}

async function cancelJob(jobId) {
  if (!state.client) {
    return;
  }
  try {
    await state.client.cancelJob(jobId);
    await refreshJobs();
  } catch (error) {
    handleFailure(error, 'tasks');
  }
}

// ------------------------------------------------------------------- memory

function drawMemory(entries) {
  const list = $('memory');
  list.textContent = '';
  for (const entry of entries) {
    const item = document.createElement('li');
    item.textContent = entry.text;
    const source = document.createElement('span');
    source.className = 'badge';
    source.textContent = entry.source || 'unknown';
    item.prepend(source);
    list.append(item);
  }
}

async function refreshMemory() {
  if (!state.client) {
    return;
  }
  try {
    drawMemory(await state.client.memory());
  } catch (error) {
    handleFailure(error, 'memory');
  }
}

async function remember() {
  if (!state.client) {
    return;
  }
  const text = $('memoryText').value.trim();
  if (!text) {
    return;
  }
  try {
    await state.client.remember(text, 'iphone');
    $('memoryText').value = '';
    await refreshMemory();
  } catch (error) {
    // A memory entry is not kept for later: the desktop stores every entry it
    // receives, so sending it twice would write it twice. The page says that
    // the entry was lost instead of pretending it is safe.
    handleFailure(error, 'memory', { lost: true });
  }
}

// ------------------------------------------------------------ notifications

function drawNotifications(items) {
  const list = $('notifications');
  list.textContent = '';
  for (const item of items) {
    const entry = document.createElement('li');
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = item.level || 'info';
    const title = document.createElement('span');
    title.textContent = item.title || '';
    entry.append(badge, title);
    if (item.body) {
      const body = document.createElement('p');
      body.className = 'hint';
      body.textContent = item.body;
      entry.append(body);
    }
    const ack = document.createElement('button');
    ack.className = 'ghost';
    ack.textContent = 'Seen';
    ack.addEventListener('click', () => acknowledge(item.id));
    entry.append(ack);
    list.append(entry);
  }
}

async function refreshNotifications() {
  if (!state.client) {
    return;
  }
  try {
    const items = await state.client.notifications();
    drawNotifications(items);
    if ($('allowNotifications').checked && items.length && 'Notification' in window) {
      if (Notification.permission === 'granted') {
        new Notification(items[items.length - 1].title || 'JARVIS', { body: items[items.length - 1].body || '' });
      }
    }
  } catch (error) {
    handleFailure(error, 'notifications');
  }
}

async function acknowledge(notificationId) {
  if (!state.client) {
    return;
  }
  try {
    await state.client.acknowledge(notificationId);
    // The notification is seen, so a copy that waits in the queue must not be
    // sent a second time.
    await state.outbox.discard(KINDS.NOTIFICATION_ACK, { id: notificationId });
    await refreshNotifications();
  } catch (error) {
    // Marking a notification as seen twice changes nothing, so this one may
    // safely wait in the queue.
    const kept = await keepForLater(error, KINDS.NOTIFICATION_ACK, { id: notificationId });
    handleFailure(error, 'notifications', { kept });
  }
}

// ------------------------------------------------------------------- outbox

/**
 * Whether the failure means the PC could not be reached at all.
 *
 * A status of zero is the answer for a request that never left the phone: a
 * dead bridge, a closed Wi-Fi or a VPN that is not up. An answer the PC gave
 * is a real answer, and repeating the request would not change it.
 */
function isUnreachable(error) {
  return error instanceof BridgeError && error.status === 0;
}

/**
 * Do the work one queued descriptor stands for.
 *
 * The outbox holds plain data, so this is where a descriptor becomes a call.
 * The page owns the mapping, the queue never holds a function.
 */
async function executeQueued(item) {
  if (!state.client) {
    throw new Error('The PC is not connected yet.');
  }
  if (item.kind === KINDS.CHAT) {
    const answer = await state.client.chat(item.payload.message, {
      consent: Boolean(item.payload.consent),
    });
    state.transcript.add('jarvis', answer.text || '(no answer)');
    drawChat();
    return answer;
  }
  if (item.kind === KINDS.TASK) {
    await state.client.submitJob({
      kind: item.payload.kind || 'CUSTOM',
      title: item.payload.title,
      payload: item.payload.payload || '',
      requireApproval: item.payload.requireApproval !== false,
    });
    return null;
  }
  if (item.kind === KINDS.NOTIFICATION_ACK) {
    await state.client.acknowledge(item.payload.id);
    return null;
  }
  throw new Error(`The outbox does not know the kind "${item.kind}".`);
}

/**
 * Keep the work when the PC could not be reached.
 *
 * Only work that may be repeated safely is kept: a chat message, a task for
 * approval and the acknowledgement of a notification. A memory entry is not
 * one of them, because the desktop would store it a second time.
 */
async function keepForLater(error, kind, payload) {
  if (!isUnreachable(error)) {
    return null;
  }
  const result = await state.outbox.push({ kind, payload });
  showOutboxStatus();
  return result;
}

/**
 * Say how many items are waiting, and whether they can be saved.
 *
 * The line never promises a delivery in the background: iOS does not give a
 * web app one.
 */
function showOutboxStatus() {
  const element = $('outboxStatus');
  if (!element) {
    return;
  }
  const waiting = state.outbox.length;
  if (!waiting) {
    element.textContent = '';
    element.className = 'status';
    return;
  }
  if (state.outbox.storageError) {
    element.textContent = `${waiting} item(s) are waiting on this phone, but they cannot be saved (${state.outbox.storageError}), so closing the app loses them.`;
    element.className = 'status error';
    return;
  }
  const dropped = state.outbox.dropped
    ? ` ${state.outbox.dropped} item(s) were dropped because the queue was full.`
    : '';
  element.textContent = `${waiting} item(s) are waiting on this phone. They go out when this app is open and the PC answers.${dropped}`;
  element.className = 'status';
}

/**
 * Read the queue back from the phone.
 *
 * The work survives a reload, but the pairing secret does not: the queue can
 * only be sent once the PC has been paired again and it answers.
 */
async function restoreOutbox() {
  const store = createIndexedDbStore();
  if (store) {
    state.outbox.useStore(store);
  } else {
    // Without IndexedDB the work is only kept while the page stays open, and
    // the page has to say so.
    state.outbox.storageError = 'this browser has no IndexedDB';
  }
  const waiting = await state.outbox.restore();
  showOutboxStatus();
  if (waiting) {
    say(`${waiting} item(s) are waiting on this phone. Pair with the PC and they are sent.`);
  }
  return waiting;
}

/**
 * Send the queued work.
 *
 * This only happens while the app is open. iOS does not let a web app run in
 * the background, so the queue is sent when the app starts, when the
 * connection returns, when the app comes back to the front, and every few
 * seconds while the page is in front.
 */
async function flushOutbox() {
  if (!state.client || state.outbox.length === 0) {
    showOutboxStatus();
    return null;
  }
  const results = await state.outbox.flush(executeQueued);
  showOutboxStatus();
  if (results.sent) {
    say(`${results.sent} item(s) sent to the PC.`);
  }
  return results;
}

function startFlushing() {
  stopFlushing();
  state.flushTimer = setInterval(() => {
    flushOutbox();
  }, FLUSH_INTERVAL_MS);
}

function stopFlushing() {
  if (state.flushTimer) {
    clearInterval(state.flushTimer);
    state.flushTimer = null;
  }
}

// ------------------------------------------------------------------ failure

/**
 * Show a failure and say what really happened to the work.
 *
 * Work that was kept is on this phone and goes out when the app is open and
 * the PC answers. Work that was lost has to be asked for again, and work that
 * was only a reading has to be tried again. The page never promises a
 * delivery that cannot happen.
 */
function handleFailure(error, area, { kept = null, lost = false } = {}) {
  const message = error instanceof Error ? error.message : String(error);
  if (isUnreachable(error)) {
    if (kept && kept.duplicate && kept.sent) {
      say('The PC could not be reached. That work was sent a moment ago, so it was not queued again.');
    } else if (kept && kept.duplicate) {
      say('The PC could not be reached. That work is already waiting on this phone.');
    } else if (kept && !kept.persisted) {
      say('The PC could not be reached. Your work is kept in this page only: closing the app loses it.');
    } else if (kept) {
      say('The PC could not be reached. Your work is kept on this phone and goes out when this app is open and the PC answers.');
    } else if (lost) {
      say('The PC could not be reached. That entry was not saved, so write it again when the connection is back.');
    } else {
      say('The PC could not be reached.');
    }
  } else {
    say(message);
  }
  if (area === 'chat') {
    setStatus('chatStatus', message, 'error');
  }
  state.lastError = message;
}

async function refreshAll() {
  await refreshStatus();
  await refreshJobs();
  await refreshMemory();
  await refreshNotifications();
}

// -------------------------------------------------------------------- setup

function installListeners() {
  const picker = $('voiceLanguage');
  if (picker) {
    picker.value = defaultLanguage();
  }
  $('enableSiriWake').addEventListener('click', enableSiriWake);
  window.addEventListener('hashchange', handleSiriWake);
  $('connect').addEventListener('click', connect);
  $('disconnect').addEventListener('click', forgetSecret);
  $('scan').addEventListener('click', () => $('scanFile').click());
  $('scanFile').addEventListener('change', (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) {
      scanPairing(file);
    }
    event.target.value = '';
  });
  $('paste').addEventListener('click', () => {
    if (applyPairing($('pairingText').value)) {
      connect();
    }
  });
  $('refresh').addEventListener('click', refreshStatus);
  $('autoRefresh').addEventListener('change', (event) => {
    if (event.target.checked) {
      startWatching();
    } else {
      stopWatching();
    }
  });
  $('send').addEventListener('click', () => sendMessage($('message').value));
  $('message').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      sendMessage($('message').value);
      $('message').value = '';
    }
  });
  $('listen').addEventListener('click', toggleListening);
  $('audioCall').addEventListener('click', () => startPhoneCall('audio'));
  $('videoCall').addEventListener('click', () => startPhoneCall('video'));
  $('endCall').addEventListener('click', endPhoneCall);
  $('phoneCamera').addEventListener('click', togglePhoneCamera);
  $('lookNow').addEventListener('click', () => {
    if (!state.client) {
      setStatus('cameraStatus', 'Connect to the PC first.', 'error');
      return;
    }
    const question = $('message').value.trim();
    const view = $('liveCameraView');
    if (!state.camera || !view.videoWidth || !$('consent').checked) {
      setStatus('cameraStatus', 'Turn on the camera and allow Gemini in Chat.', 'error');
      return;
    }
    try {
      const images = [cameraFrame(view, view.videoWidth, view.videoHeight)];
      setStatus('cameraStatus', 'See the answer in Chat.');
      window.location.hash = 'chatPanel';
      sendMessage(question || 'இது என்ன?', { images });
    } catch {
      setStatus('cameraStatus', 'Could not read the current camera frame. Try again.', 'error');
    }
  });
  window.addEventListener('pagehide', endPhoneCall);
  for (const [button, input, isClip] of [
    ['cameraAsk', 'cameraPhoto', false], ['clipAsk', 'cameraClip', true],
  ]) {
    $(button).addEventListener('click', () => $(input).click());
    $(input).addEventListener('change', (event) => {
      const file = event.target.files[0];
      if (file) askAboutCamera(file, isClip);
      event.target.value = '';
    });
  }
  $('speak').addEventListener('click', () => {
    state.speakAnswers = !state.speakAnswers;
    $('speak').textContent = state.speakAnswers ? 'Speaking on' : 'Speak answers';
    if (!synthesisSupported()) {
      setStatus('chatStatus', 'This browser cannot speak.', 'error');
    }
  });
  $('moreNav').addEventListener('click', () => { $('morePanel').open = true; });
  $('checkDisk').addEventListener('click', async () => {
    if (!state.client) {
      setStatus('taskStatus', 'Connect to the PC first.', 'error');
      return;
    }
    setStatus('taskStatus', 'Sending disk check…');
    const submitted = await submitTaskRequest(CHAT_COMMANDS.get('/disk')());
    setStatus('taskStatus', submitted ? 'Sent. Approve it on the PC.' : 'Check the connection message.',
      submitted ? 'ok' : '');
  });
  $('submitTask').addEventListener('click', submitTask);
  $('refreshJobs').addEventListener('click', refreshJobs);
  $('backupHistory').addEventListener('click', backupHistory);
  $('remember').addEventListener('click', remember);
  $('refreshMemory').addEventListener('click', refreshMemory);
  $('refreshNotifications').addEventListener('click', refreshNotifications);
  $('allowNotifications').addEventListener('change', (event) => {
    if (event.target.checked && 'Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  });
  $('install').addEventListener('click', async () => {
    if (state.installPrompt) {
      state.installPrompt.prompt();
      await state.installPrompt.userChoice;
      state.installPrompt = null;
      $('install').hidden = true;
    }
  });
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    state.installPrompt = event;
    $('install').hidden = false;
  });
  window.addEventListener('online', () => {
    say('');
    flushOutbox().then(() => refreshAll());
  });
  window.addEventListener('offline', () => say('This phone is offline. Anything you send now is kept on this phone and goes out when this app is open and the PC answers.'));
  // iOS brings the app back to the front without an `online` event, so the
  // queue is tried again whenever the page comes back into sight.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      flushOutbox();
    }
  });
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

async function start() {
  const location = globalThis.location;
  const pairingLink = location?.hash.startsWith('#pair=') && location.href;
  if (pairingLink) globalThis.history.replaceState(null, '', location.pathname);
  drawChat();
  installListeners();
  registerServiceWorker();
  // The work that was kept before a reload is read back, the heartbeat that
  // sends it while the app is open is started, and whatever can be sent now
  // is sent now.
  await handleSiriWake();
  await restoreOutbox();
  if (pairingLink && applyPairing(pairingLink)) await connect();
  await flushOutbox();
  startFlushing();
  if ($('autoRefresh').checked) {
    startWatching();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
