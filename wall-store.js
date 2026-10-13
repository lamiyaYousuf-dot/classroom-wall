// Shared data layer for the classroom wall (index.html) and the teacher page (admin.html).
// Uses Firebase Realtime Database when it is reachable, so every phone and the
// projector see the same wall. If Firebase can't be reached, it falls back to
// localStorage so the demo still works across tabs in one browser.
(function () {
  const FIREBASE_CONFIG = {
    databaseURL: "https://classroom-wall-73f88-default-rtdb.firebaseio.com"
  };
  const ROOT = 'nook_wall';
  const LOCAL_KEY = 'nook_wall_local_v3';
  const ADMIN_KEY = 'nook_wall_admin';
  const CONNECT_TIMEOUT_MS = 6000;
  const EXPIRATION_MS = 30 * 60 * 1000;
  const DEFAULT_PIN = '1234';

  // Cute animal faces drawn as inline SVG, so they look the same on every phone
  // (emoji differ between iPhone, Android and Windows). Sized with font-size (1em).
  const INK = '#3B2A20';
  const svg = body => `<svg viewBox="0 0 64 64" width="1em" height="1em" aria-hidden="true" style="display:inline-block;vertical-align:middle;overflow:visible">${body}</svg>`;
  const eyes = (y = 36, dx = 7) =>
    `<circle cx="${32 - dx}" cy="${y}" r="2.7" fill="${INK}"/><circle cx="${32 + dx}" cy="${y}" r="2.7" fill="${INK}"/>` +
    `<circle cx="${31.1 - dx}" cy="${y - 1}" r="0.95" fill="#fff"/><circle cx="${31.1 + dx}" cy="${y - 1}" r="0.95" fill="#fff"/>`;
  const sleepyEyes = (y = 36, dx = 7) =>
    `<path d="M${28.5 - dx} ${y} q3.5 3 7 0 M${28.5 + dx} ${y} q3.5 3 7 0" stroke="${INK}" stroke-width="1.8" fill="none" stroke-linecap="round"/>`;
  const blush = (y = 42, dx = 11) =>
    `<ellipse cx="${32 - dx}" cy="${y}" rx="3.4" ry="2.1" fill="#FF9EB5" opacity="0.75"/><ellipse cx="${32 + dx}" cy="${y}" rx="3.4" ry="2.1" fill="#FF9EB5" opacity="0.75"/>`;
  const smile = (y = 41) =>
    `<path d="M29.4 ${y} q1.3 1.7 2.6 0 q1.3 1.7 2.6 0" stroke="${INK}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;

  const CHARACTERS = [
    { id: 'bunny', name: 'Bunny', icon: svg(
      `<ellipse cx="23" cy="15" rx="5.8" ry="13" fill="#FFF7F3" stroke="#EBD9D1" stroke-width="1.5"/>` +
      `<ellipse cx="41" cy="15" rx="5.8" ry="13" fill="#FFF7F3" stroke="#EBD9D1" stroke-width="1.5"/>` +
      `<ellipse cx="23" cy="16" rx="2.6" ry="9" fill="#FFC4D3"/><ellipse cx="41" cy="16" rx="2.6" ry="9" fill="#FFC4D3"/>` +
      `<circle cx="32" cy="38" r="19" fill="#FFF7F3" stroke="#EBD9D1" stroke-width="1.5"/>` +
      eyes(37) + blush(43) + `<ellipse cx="32" cy="41" rx="1.6" ry="1.1" fill="#FF8FAB"/>` + smile(42.5)) },
    { id: 'bear', name: 'Teddy Bear', icon: svg(
      `<circle cx="16" cy="21" r="7.5" fill="#C98B5A"/><circle cx="48" cy="21" r="7.5" fill="#C98B5A"/>` +
      `<circle cx="16" cy="21" r="3.8" fill="#EDBB91"/><circle cx="48" cy="21" r="3.8" fill="#EDBB91"/>` +
      `<circle cx="32" cy="36" r="20" fill="#C98B5A"/>` +
      `<ellipse cx="32" cy="43" rx="8" ry="6" fill="#F3D5B5"/>` + eyes(34) + blush(41, 12.5) +
      `<ellipse cx="32" cy="40.5" rx="2.6" ry="1.8" fill="${INK}"/>` + smile(43.5)) },
    { id: 'fox', name: 'Sleepy Fox', icon: svg(
      `<path d="M13 28 L16 7 L30 19 Z" fill="#F08A3C"/><path d="M51 28 L48 7 L34 19 Z" fill="#F08A3C"/>` +
      `<path d="M17 23 L18.5 12 L26 19 Z" fill="#FFE3CC"/><path d="M47 23 L45.5 12 L38 19 Z" fill="#FFE3CC"/>` +
      `<circle cx="32" cy="37" r="19.5" fill="#F08A3C"/>` +
      `<path d="M13 39 Q22 36 32 47 Q42 36 51 39 Q48 56 32 56.5 Q16 56 13 39 Z" fill="#FFF5EC"/>` +
      sleepyEyes(35) + blush(41, 12.5) + `<ellipse cx="32" cy="45" rx="2.3" ry="1.6" fill="${INK}"/>`) },
    { id: 'cat', name: 'Cool Cat', icon: svg(
      `<path d="M13 30 L15 8 L29 19 Z" fill="#F5B971"/><path d="M51 30 L49 8 L35 19 Z" fill="#F5B971"/>` +
      `<path d="M17 24 L18 14 L25 19.5 Z" fill="#FFD6DE"/><path d="M47 24 L46 14 L39 19.5 Z" fill="#FFD6DE"/>` +
      `<circle cx="32" cy="37" r="19.5" fill="#F5B971"/>` +
      `<path d="M27 21 l2 5 M32 19.5 v5.5 M37 21 l-2 5" stroke="#E39A4A" stroke-width="2" stroke-linecap="round"/>` +
      `<rect x="18.5" y="31" width="11" height="8" rx="4" fill="${INK}"/><rect x="34.5" y="31" width="11" height="8" rx="4" fill="${INK}"/>` +
      `<path d="M29.5 34 h5" stroke="${INK}" stroke-width="2"/><path d="M21 33 l3 -1" stroke="#fff" stroke-width="1.3" stroke-linecap="round" opacity="0.8"/><path d="M37 33 l3 -1" stroke="#fff" stroke-width="1.3" stroke-linecap="round" opacity="0.8"/>` +
      blush(44, 12) + `<path d="M30.4 42 h3.2 l-1.6 1.8 Z" fill="#FF8FAB"/>` + smile(44.5) +
      `<path d="M10 41 h7 M10.5 45 l6.5 -1.5 M54 41 h-7 M53.5 45 l-6.5 -1.5" stroke="#B9814A" stroke-width="1.2" stroke-linecap="round"/>`) },
    { id: 'chick', name: 'Little Chick', icon: svg(
      `<path d="M30 17 q-2 -8 3 -10 q-1 5 3 7 q2 -4 6 -3 q-4 3 -4 7" fill="#FFC93C"/>` +
      `<circle cx="32" cy="37" r="20" fill="#FFD84D"/>` + eyes(34) + blush(41, 12) +
      `<path d="M27.5 39.5 Q32 37 36.5 39.5 Q32 45 27.5 39.5 Z" fill="#FF9A3C"/>` +
      `<path d="M13 44 q-5 -3 -4 -9 q5 2 6 6" fill="#FFC93C"/><path d="M51 44 q5 -3 4 -9 q-5 2 -6 6" fill="#FFC93C"/>`) },
    { id: 'frog', name: 'Matcha Frog', icon: svg(
      `<circle cx="21" cy="22" r="9" fill="#8DCB72"/><circle cx="43" cy="22" r="9" fill="#8DCB72"/>` +
      `<ellipse cx="32" cy="40" rx="22" ry="17" fill="#8DCB72"/>` +
      `<circle cx="21" cy="22" r="5.5" fill="#fff"/><circle cx="43" cy="22" r="5.5" fill="#fff"/>` +
      `<circle cx="21.5" cy="23" r="3" fill="${INK}"/><circle cx="43.5" cy="23" r="3" fill="${INK}"/>` +
      `<circle cx="20.6" cy="21.8" r="1" fill="#fff"/><circle cx="42.6" cy="21.8" r="1" fill="#fff"/>` +
      blush(41, 13.5) + `<path d="M24 41 Q32 49 40 41" stroke="${INK}" stroke-width="1.8" fill="none" stroke-linecap="round"/>` +
      `<ellipse cx="32" cy="50" rx="9" ry="3" fill="#B4E09E" opacity="0.7"/>`) },
    { id: 'panda', name: 'Happy Panda', icon: svg(
      `<circle cx="15.5" cy="20" r="7.5" fill="${INK}"/><circle cx="48.5" cy="20" r="7.5" fill="${INK}"/>` +
      `<circle cx="32" cy="37" r="20" fill="#FFFFFF" stroke="#E5E1DC" stroke-width="1.5"/>` +
      `<ellipse cx="24" cy="35" rx="5" ry="6.5" fill="${INK}" transform="rotate(25 24 35)"/><ellipse cx="40" cy="35" rx="5" ry="6.5" fill="${INK}" transform="rotate(-25 40 35)"/>` +
      `<circle cx="24.5" cy="34.5" r="2" fill="#fff"/><circle cx="39.5" cy="34.5" r="2" fill="#fff"/>` +
      blush(44, 12.5) + `<ellipse cx="32" cy="42" rx="2.4" ry="1.6" fill="${INK}"/>` + smile(44)) },
    { id: 'owl', name: 'Wise Owl', icon: svg(
      `<path d="M14 22 L16 8 L25 17 Z" fill="#A47A55"/><path d="M50 22 L48 8 L39 17 Z" fill="#A47A55"/>` +
      `<ellipse cx="32" cy="37" rx="20" ry="20" fill="#A47A55"/>` +
      `<path d="M18 44 Q32 62 46 44 Q32 52 18 44 Z" fill="#E8CFAE"/>` +
      `<circle cx="24" cy="32" r="8" fill="#FFF8EC"/><circle cx="40" cy="32" r="8" fill="#FFF8EC"/>` +
      `<circle cx="24.5" cy="32.5" r="4" fill="${INK}"/><circle cx="39.5" cy="32.5" r="4" fill="${INK}"/>` +
      `<circle cx="23.2" cy="31" r="1.4" fill="#fff"/><circle cx="38.2" cy="31" r="1.4" fill="#fff"/>` +
      `<path d="M29.5 38 h5 l-2.5 4 Z" fill="#F2A33A"/>` + blush(42, 15)) },
    { id: 'penguin', name: 'Penguin', icon: svg(
      `<circle cx="32" cy="36" r="21" fill="#34445F"/>` +
      `<path d="M32 22 Q22 18 18 28 Q14 40 22 49 Q32 56 42 49 Q50 40 46 28 Q42 18 32 22 Z" fill="#FFFFFF"/>` +
      eyes(34, 6.5) + blush(41, 11) +
      `<path d="M28.5 38.5 Q32 36.5 35.5 38.5 L32 42.5 Z" fill="#FFA63D"/>` +
      `<path d="M23 15 q9 -7 18 0" stroke="#5B9BD5" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="32" cy="10" r="3" fill="#FF8FAB"/>`) }
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

  // Characters that were renamed, so older messages keep a matching animal.
  const OLD_IDS = { robot: 'bear', duck: 'chick', camel: 'penguin' };

  function character(id) {
    id = OLD_IDS[id] || id;
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
