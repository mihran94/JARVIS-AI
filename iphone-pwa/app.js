// The JARVIS iPhone page.
//
// The page holds the pairing secret in memory only. It signs every bridge
// request with the shared scheme, so the phone never holds a provider key
// and never talks to a provider directly.
//
// Everything that can fail on a phone is treated as normal: no network, a
// locked screen, a browser without voice and a browser without
// notifications are all handled without breaking the page.

import { BridgeClient, BridgeError } from './js/bridge.js';
import { ChatTranscript, renderTranscript } from './js/chat.js';
import { Outbox } from './js/offline.js';
import { parsePairingPayload } from './js/pairing.js';
import { decodeQrFromFile } from './js/qr.js';
import {
  chooseLanguage, defaultLanguage, recognitionSupported, speak, startListening,
  synthesisSupported,
} from './js/speech.js';

const $ = (id) => document.getElementById(id);

const state = {
  client: null,
  transcript: new ChatTranscript(),
  outbox: new Outbox(),
  listening: null,
  speakAnswers: false,
  timer: null,
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
  setStatus('pairStatus', 'Checking the PC…');
  try {
    const status = await state.client.status();
    setStatus('pairStatus', `Connected to ${status.hostname || 'the PC'}.`, 'ok');
    showStatus(status);
    await refreshAll();
  } catch (error) {
    setStatus('pairStatus', error.message, 'error');
    say(error.message);
  }
}

function forgetSecret() {
  state.client = null;
  $('secret').value = '';
  setStatus('pairStatus', 'The secret was cleared from this page.');
  stopWatching();
}

function applyPairing(text) {
  try {
    const pairing = parsePairingPayload(text);
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

async function sendMessage(text) {
  const message = (text || '').trim();
  if (!message) {
    return;
  }
  if (!state.client) {
    setStatus('chatStatus', 'Connect to the PC first.', 'error');
    return;
  }
  state.transcript.add('person', message);
  drawChat();
  setStatus('chatStatus', 'Thinking…');
  try {
    const answer = await state.client.chat(message, { consent: $('consent').checked });
    state.transcript.add('jarvis', answer.text || '(no answer)');
    drawChat();
    setStatus('chatStatus', `Answered by ${answer.provider || 'the PC'}.`, 'ok');
    if (state.speakAnswers) {
      speak(answer.text || '', { lang: chooseLanguage(answer.text || '') });
    }
  } catch (error) {
    handleFailure(error, 'chat');
    state.transcript.add('system', error.message);
    drawChat();
  }
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
    state.listening = startListening({
      lang: defaultLanguage(),
      onResult: (text) => {
        state.listening = null;
        $('listen').textContent = 'Listen';
        if (text) {
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

async function submitTask() {
  if (!state.client) {
    return;
  }
  const title = $('taskTitle').value.trim();
  const payload = $('taskPayload').value;
  try {
    await state.client.submitJob({ kind: 'CUSTOM', title, payload, requireApproval: true });
    $('taskTitle').value = '';
    $('taskPayload').value = '';
    setStatus('chatStatus', 'The task was sent. Approve it on the PC.', 'ok');
    await refreshJobs();
  } catch (error) {
    handleFailure(error, 'tasks');
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
    handleFailure(error, 'memory');
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
    await refreshNotifications();
  } catch (error) {
    handleFailure(error, 'notifications');
  }
}

// ------------------------------------------------------------------ failure

/**
 * Show a failure and keep the work if the PC simply could not be reached.
 *
 * A task that was asked for while the phone was out of reach is kept and
 * sent when the connection returns, so the person does not have to type it
 * again.
 */
function handleFailure(error, area) {
  const message = error instanceof Error ? error.message : String(error);
  if (error instanceof BridgeError && error.status === 0) {
    say('The PC could not be reached. Your work is kept and will be sent when the connection returns.');
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
  $('speak').addEventListener('click', () => {
    state.speakAnswers = !state.speakAnswers;
    $('speak').textContent = state.speakAnswers ? 'Speaking on' : 'Speak answers';
    if (!synthesisSupported()) {
      setStatus('chatStatus', 'This browser cannot speak.', 'error');
    }
  });
  $('submitTask').addEventListener('click', submitTask);
  $('refreshJobs').addEventListener('click', refreshJobs);
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
    state.outbox.flush().then(() => refreshAll());
  });
  window.addEventListener('offline', () => say('This phone is offline. Your work is kept.'));
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

function start() {
  drawChat();
  installListeners();
  registerServiceWorker();
  if ($('autoRefresh').checked) {
    startWatching();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
