# Classroom Wall

A live message wall for the classroom. The projector shows a cosy classroom scene where each student's
character stands under a speech bubble with their message. Students scan the QR code (or tap the desk's
NFC tag) and send a short note from their phone, in English or Arabic.

## Pages

| Link | Who it's for |
| --- | --- |
| `index.html` | Wall and phone form side by side (demo view) |
| `index.html?screen` | **Projector**: the wall only, sized for a big screen |
| `index.html?join` | **Students**: the phone form only. The QR code points here, so use this URL for NFC tags too |
| `admin.html` | **Teacher**: moderation controls (default PIN `1234`, change it on first use) |

## Teacher controls (`admin.html`)

- **Delete** any message with one tap, or **Clear all**.
- **Review before posting**: new messages wait in a queue until you tap Approve.
- **Wall open** switch: close the wall so nobody can post.
- **Blocked words** (English and Arabic): messages containing them can't be sent, and older posts that
  contain them are flagged in red.
- **Today's question**: shown on the chalkboard and on students' phones.
- **Student link**: the address the QR code points to. Leave it empty to use the live site
  (`https://lamiyayousuf-dot.github.io/classroom-wall/?join`).
- **Sample messages**: fills a quiet wall with example notes. They're only shown on screen and never saved.
- Once you've unlocked `admin.html` in a browser, the wall in that same browser shows a ✕ on every bubble
  so you can remove a message straight from the projector.

Students can send one message every 15 seconds. Messages disappear after 30 minutes.

The QR code is drawn in the page by `qrcode.js` (MIT, Kazuhiko Arase), so it works without any outside QR service.

## Live sync

Messages sync through Firebase Realtime Database (`wall-store.js`, `FIREBASE_CONFIG`). If Firebase can't
be reached, the wall falls back to this browser only (handy for trying it out) and the teacher page
shows a warning.

`database.rules.json` has suggested rules that limit message size and shape. Paste them into
Firebase console → Realtime Database → Rules.

**Security note:** the PIN, blocked words and send limit run in the browser. They keep a classroom
honest, but they aren't real security: someone technical could still write to the database directly.
For that you'd add Firebase Authentication and restrict deletes and settings to the teacher's account.
