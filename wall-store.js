// Shared data layer for the classroom wall (index.html) and the teacher page (admin.html).
// Uses Firebase Realtime Database when it is reachable, so every phone and the
// projector see the same wall. If Firebase can't be reached, it falls back to
// localStorage so the demo still works across tabs in one browser.
(function () {
  const FIREBASE_CONFIG = {
    databaseURL: "https://nook-classroom-wall-default-rtdb.firebaseio.com"
  };
  const ROOT = 'nook_wall';
  const LOCAL_KEY = 'nook_wall_local_v3';
  const ADMIN_KEY = 'nook_wall_admin';
  const CONNECT_TIMEOUT_MS = 6000;
  const EXPIRATION_MS = 30 * 60 * 1000;
  const DEFAULT_PIN = '1234';

  const CHARACTERS = [
    { id: 'bunny', name: 'Bunny', icon: '🐰' },
    { id: 'robot', name: 'Robot', icon: '🤖' },
    { id: 'fox', name: 'Sleepy Fox', icon: '🦊' },
    { id: 'cat', name: 'Cool Cat', icon: '🐱' },
    { id: 'duck', name: 'Duck', icon: '🦆' },
    { id: 'frog', name: 'Matcha Frog', icon: '🐸' },
    { id: 'panda', name: 'Happy Panda', icon: '🐼' },
    { id: 'owl', name: 'Wise Owl', icon: '🦉' },
    { id: 'camel', name: 'Speedy Camel', icon: '🐪' }
  ];

  // Small, non-cryptographic hash. The PIN is only a speed bump to keep
  // students out of the teacher page; it is not real security.
  function hashPin(pin) {
    let h = 0x811c9dc5;
    const s = 'nook:' + String(pin);
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16);
  }

  const DEFAULT_SETTINGS = {
    isLocked: false,
    requireApproval: false,
    showSamples: true,
    prompt: 'What made you smile in class today?',
    joinUrl: '',
    bannedWords: 'stupid, idiot, dumb, hate you, shut up, loser, ugly, غبي, اسكت, حمار',
    pinHash: hashPin(DEFAULT_PIN)
  };

  let mode = 'connecting';
  let fbRef = null;
  let messages = [];
  let settings = { ...DEFAULT_SETTINGS };
  // Why the wall isn't live: 'sdk' (Firebase scripts blocked), 'timeout' (database never
  // answered: wrong URL, not created, or network) or 'denied' (database rules refuse access).
  let problem = null;
  const listeners = [];

  function snapshot() {
    return { messages: messages.slice(), settings: { ...settings }, mode, problem };
  }

  function emit() {
    const snap = snapshot();
    listeners.forEach(fn => fn(snap));
  }

  function normalize(raw) {
    raw = raw || {};
    const msgData = raw.messages || {};
    messages = Object.keys(msgData)
      .map(id => ({ id, ...msgData[id] }))
      .filter(m => typeof m.text === 'string' && typeof m.name === 'string')
      .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
    settings = { ...DEFAULT_SETTINGS, ...(raw.settings || {}) };
  }

  // ---------- localStorage fallback ----------
  function readLocal() {
    try { return JSON.parse(localStorage.getItem(LOCAL_KEY)) || {}; } catch (e) { return {}; }
  }

  function writeLocal(raw) {
    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(raw)); } catch (e) {}
    normalize(raw);
    emit();
  }

  function startLocal(reason) {
    problem = reason;
    if (mode === 'local') { emit(); return; }
    mode = 'local';
    normalize(readLocal());
    emit();
    window.addEventListener('storage', e => {
      if (mode === 'local' && e.key === LOCAL_KEY) { normalize(readLocal()); emit(); }
    });
  }

  // ---------- Firebase ----------
  function startFirebase() {
    try {
      if (!window.firebase) throw new Error('Firebase SDK not loaded');
      if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);
      fbRef = firebase.database().ref(ROOT);
    } catch (e) {
      startLocal('sdk');
      return;
    }
    // On a slow network, show the local wall after a few seconds but keep listening:
    // if Firebase answers later, switch over to the live wall.
    const timer = setTimeout(() => { if (mode === 'connecting') startLocal('timeout'); }, CONNECT_TIMEOUT_MS);
    fbRef.on('value', snap => {
      clearTimeout(timer);
      mode = 'live';
      problem = null;
      normalize(snap.val());
      emit();
    }, err => {
      clearTimeout(timer);
      console.error('Classroom wall: Firebase refused access', err);
      startLocal('denied');
    });
  }

  // ---------- writes ----------
  // path is relative to the wall root, e.g. "messages/msg_123". A null value removes it.
  function setPath(path, value) {
    if (mode === 'live') return fbRef.child(path).set(value);
    const raw = readLocal();
    const parts = path.split('/');
    let node = raw;
    for (let i = 0; i < parts.length - 1; i++) {
      node[parts[i]] = node[parts[i]] || {};
      node = node[parts[i]];
    }
    const last = parts[parts.length - 1];
    if (value === null) delete node[last]; else node[last] = value;
    writeLocal(raw);
    return Promise.resolve();
  }

  function addMessage(msg) {
    const id = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
    return setPath('messages/' + id, msg).then(() => id);
  }

  function heart(id) {
    if (mode === 'live') {
      return fbRef.child('messages/' + id).transaction(m => {
        if (m) m.hearts = (m.hearts || 0) + 1;
        return m;
      });
    }
    const m = messages.find(x => x.id === id);
    if (!m) return Promise.resolve();
    return setPath('messages/' + id + '/hearts', (m.hearts || 0) + 1);
  }

  function remove(id) { return setPath('messages/' + id, null); }
  function approve(id) { return setPath('messages/' + id + '/status', 'approved'); }
  function clearAll() { return setPath('messages', null); }

  function updateSettings(partial) {
    if (mode === 'live') return fbRef.child('settings').update(partial);
    const raw = readLocal();
    raw.settings = { ...(raw.settings || {}), ...partial };
    writeLocal(raw);
    return Promise.resolve();
  }

  function removeExpired() {
    const now = Date.now();
    messages
      .filter(m => now - (m.createdAt || 0) >= EXPIRATION_MS)
      .forEach(m => remove(m.id));
  }

  // ---------- helpers ----------
  function bannedList(s) {
    return String((s || settings).bannedWords || '')
      .split(/[,\n]/)
      .map(w => w.trim().toLowerCase())
      .filter(Boolean);
  }

  // Returns the first blocked word found in text, or null.
  function findBannedWord(text, s) {
    const lower = String(text || '').toLowerCase();
    for (const word of bannedList(s)) {
      if (/^[a-z0-9']+$/.test(word)) {
        if (new RegExp('\\b' + word + '\\b').test(lower)) return word;
      } else if (lower.includes(word)) {
        return word;
      }
    }
    return null;
  }

  function isAdminHere() {
    try { return localStorage.getItem(ADMIN_KEY) === settings.pinHash; } catch (e) { return false; }
  }

  function setAdminHere(on) {
    try {
      if (on) localStorage.setItem(ADMIN_KEY, settings.pinHash);
      else localStorage.removeItem(ADMIN_KEY);
    } catch (e) {}
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function character(id) {
    return CHARACTERS.find(c => c.id === id) || CHARACTERS[0];
  }

  window.WallStore = {
    CHARACTERS,
    DEFAULT_PIN,
    DEFAULT_SETTINGS,
    EXPIRATION_MS,
    subscribe(fn) { listeners.push(fn); if (mode !== 'connecting') fn(snapshot()); },
    getMode: () => mode,
    getProblem: () => problem,
    databaseUrl: FIREBASE_CONFIG.databaseURL,
    addMessage, heart, remove, approve, clearAll, updateSettings, removeExpired,
    findBannedWord, hashPin, isAdminHere, setAdminHere, escapeHtml, character
  };

  startFirebase();
})();
