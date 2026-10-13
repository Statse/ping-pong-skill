# Pocket List: a shared grocery list for two phones, with no server

**The idea.** One list, two phones. Either person adds an item in a couple of
taps; the list lives on both devices and never leaves them.

**Your three non-negotiables, intact.** No account, no login, no sign-up of any
kind. One self-contained HTML file — QR encoding and decoding included — with no
build step and no package install. The list data is never sent to a server; it
stays on the two phones.

**How you use it.** Type an item, press Enter. Tap to tick it off, with a
five-second undo. Ticked items move to a "got it" group; "Clear got it" deletes
them. Two items with the same name stay separate unless you choose to combine
them.

**How the two phones agree.** Before either of you leaves, you swap: both tap
Swap, which freezes each phone's outgoing snapshot, then each scans the other's
QR codes with the app's own scanner. Finish both directions before editing again.
Large lists use compressed, numbered QR parts, and a snapshot merges only when
complete. The codes carry data, never links — there is no system-camera path and
no messaging transport to leak the list through.

**How conflicts resolve.** Every item has a random ID. Each edit takes a logical
counter above every counter the phone has seen, with the device ID breaking ties;
the highest version wins. This means two concurrent edits to the *same* item can
lose one of the two changes. Deletion records are kept permanently, so an older
snapshot or backup can never resurrect an item you removed.

**What the app promises.** It shows "last update received" and "local edits since
your outgoing snapshot". It never says "live" and never implies a sync it cannot
verify.

**Backups.** Export and import a local backup file, merged by the same rules.
Keep backups on these devices, outside cloud-synced storage. The app can request
persistent storage and offer home-screen installation where supported; neither
guarantees against data loss.

**The honest limitation.** While you are apart, the phones cannot exchange
anything — each shows only what it already holds. Your brief imagined "whoever is
in the shop sees it immediately"; that is not achievable without a server, and
the non-negotiables win.

## Open question for you

Is exchanging updates only when you are together acceptable for shopping trips
you make separately? If not, something has to give — and it would have to be the
no-server rule.
