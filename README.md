# Classroom Wall

A live message wall for the classroom. The projector shows a cosy classroom scene where each student's
character stands under a speech bubble with their message. Students scan the QR code (or tap the desk's
NFC tag) and send a short note from their phone, in English or Arabic.

## Pages

| Link | Who it's for |
| --- | --- |
| `index.html` | Wall and phone form side by side (demo view) |
| `index.html?screen` | **Projector**: the wall only, sized for a big screen |
| `index.html?join` | **Students**: the phone form, plus a **See the wall** tab to read messages and give hearts (one per message per phone). The QR code points here, so use this URL for NFC tags too |
| `admin.html` | **Teacher**: moderation controls. Sign in with your teacher account (see *Teacher sign-in*) |

## Teacher controls (`admin.html`)

- **Delete** any message with one tap, or **Clear all**.
- **Review before posting**: new messages wait in a queue until you tap Approve.
- **Wall open** switch: close the wall so nobody can post.
- **Close automatically**: set a timer (5, 10, 15 or 30 minutes) or a closing time. Students and the
  chalkboard show a countdown, and the form closes when time is up. Turn "Wall open" back on to reopen.
- **Blocked words** (English and Arabic): messages containing them can't be sent, and older posts that
  contain them are flagged in red.
- **Today's question**: shown on the chalkboard and on students' phones.
- **Student link**: the address the QR code points to. Leave it empty to use the live site
  (`https://lamiyayousuf-dot.github.io/classroom-wall/?join`).
- **Sample messages**: fills a quiet wall with example notes. They're only shown on screen and never saved.
- Once you've signed in on `admin.html`, the wall in that same browser shows a ✕ on every bubble
  so you can remove a message straight from the projector.

Students can send one message every 15 seconds. Messages disappear after 30 minutes.

The QR code is drawn in the page by `qrcode.js` (MIT, Kazuhiko Arase), so it works without any outside QR service.

## Live sync

Messages sync through Firebase Realtime Database (`wall-store.js`, `FIREBASE_CONFIG`). If Firebase can't
be reached, the wall falls back to this browser only (handy for trying it out) and the teacher page
shows a warning.

The wall footer shows **● Live** when phones and the screen are connected. If it says
**● Not connected**, open the teacher page: it explains why.

### Setting up the database (one time)

1. Go to <https://console.firebase.google.com> and open (or create) your project.
2. **Build → Realtime Database → Create database**. Pick a location and start in **test mode**.
3. Copy the database URL shown at the top of the Data tab (e.g. `https://my-project-default-rtdb.firebaseio.com`
   or `https://my-project-default-rtdb.europe-west1.firebasedatabase.app`).
4. Put that URL in `wall-store.js` as `databaseURL`.
5. Under **Rules**, paste the contents of `database.rules.json` and click **Publish**.

### Teacher sign-in (one time)

Teacher actions (settings, deleting, approving, clearing) are only allowed for a signed-in teacher.
This is checked by the database itself, not just the web page.

1. **Get the web app key.** Firebase console → ⚙️ **Project settings** → **Your apps**. If there is no
   web app, click **</>** to add one (any nickname, no hosting). Copy the `apiKey` value and put it in
   `wall-store.js` → `FIREBASE_CONFIG.apiKey`. It is not a secret; it only identifies the project.
2. **Turn on email sign-in.** **Build → Authentication → Get started → Sign-in method → Email/Password →
   Enable**.
3. **Allow the website.** **Authentication → Settings → Authorized domains → Add domain** →
   `lamiyayousuf-dot.github.io`.
4. **Create the teacher account.** **Authentication → Users → Add user** with your email and a strong
   password.
5. **Make it a teacher.** Open `admin.html` and sign in. It shows your **user ID**. In **Realtime Database →
   Data**, add a key `admins` with a child `<your user ID>` set to `true` (boolean). Refresh the page.
6. **Publish the rules.** Paste `database.rules.json` into **Realtime Database → Rules** and click **Publish**.

To add another teacher, repeat steps 4–5 for their account. Teachers can only be added from the
Firebase console, never from the app.

### What the database rules enforce

- Anyone can read the wall and post a new message, but only while the wall is open and before the
  closing time, with the right size and shape, a current timestamp and 0 hearts.
- When **Review before posting** is on, new messages must arrive as *pending*; only a teacher can approve.
- Hearts can only go up by exactly one at a time.
- Only a signed-in teacher (listed under `admins`) can change settings, approve, delete or clear.
- Nobody can make themselves a teacher from the app.

The rules are tested against the Firebase emulator (34 checks, including every case above).

**Remaining limits:** blocked words and the 15-second send limit still run in the browser, so a
technical student could bypass them by writing to the database directly. Use **Review before posting**
when you need to be certain nothing appears without your approval.
