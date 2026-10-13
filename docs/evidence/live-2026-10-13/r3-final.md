# Pocket List
One self-contained HTML file, including QR encoding/decoding: no build, packages, account or login. List data stays on the two phones; no server receives it.

Open at a stable static HTTPS address for camera access. The host serves code only. Offer home-screen installation and request persistent storage where supported; neither guarantees against data loss.

Type an item and press Enter. Tap to tick, with 5-second undo. Ticked items move to ‘got it’; ‘Clear got it’ deletes them. Duplicate names stay separate, with an option to combine.

Before either person leaves, swap: both tap Swap, freezing their outgoing snapshots, then scan each other’s codes using the embedded scanner. Finish both directions before editing again. Use compressed, numbered QR parts; merge only a complete snapshot. Codes contain data, never URLs. No system-camera or messaging transport.

Items have random IDs. Each edit uses a logical counter above every counter seen; device ID breaks ties. Highest version wins, so concurrent edits to one item can lose one change. Keep deletion records permanently so older snapshots and backups cannot resurrect items.

Show ‘last update received’ and ‘local edits since outgoing snapshot’, never ‘live’ or an unverified sync claim.

When apart, phones cannot exchange updates: each shows only what it already holds. Immediate remote updates are unavailable under these constraints.

Export/import local backup files, merging by the same rules. Keep backups on these devices, outside cloud-synced storage.

---

Rally: 4/4 hits between Claude Code and Codex.

Owner brief (authoritative, as given):

# Idea to refine: a shared grocery list for a two-person household

One list, two phones, no friction: either person adds an item in a couple of taps,
and whoever is in the shop sees it immediately and can tick it off.

Non-negotiables (do not design these away):
- It must work with no account, no login and no sign-up of any kind.
- It must stay a single HTML file with no build step and no package install.
- It must never send the list to a server; the data stays on the two devices.

What I want from the refinement: make this genuinely usable for two people who
shop separately, while keeping all three non-negotiables intact.

Size limit retries that remained over budget: 1.

Questions the last hit still leaves open:
- Is exchanging updates only when together acceptable for your separate shopping trips?

Questions raised earlier that the last hit no longer asks. Check the final version, the owner notes and the ledger before relisting them; do not invent answers:
- Is it acceptable for the update link to go through a messaging app like WhatsApp or Signal, or should sync happen only with the phones together (QR code)?
- Would you accept a 'last synced' time instead of truly immediate updates?
- Is exchanging updates in person before separate shopping acceptable, given that immediate remote updates remain unavailable in this design?
- Which two phone/browser combinations must support the HTML file?
- Is a swap only when both people are together acceptable? Items added while you are apart can't reach the shopper. Doing that would need a network relay, which O-3 forbids.
- Who hosts the static HTTPS file: the owner, or a free static host?
- Should quantities or notes per item be in scope?

Owner requirements agents proposed changing:
- Brief: 'whoever is in the shop sees it immediately': O-3 and O-1 rule out a relay server, so live updates between phones that are apart aren't possible. The closest honest option is fast manual sync plus a visible 'last synced' time.
- O-3: never send the list to a server: Sending the update link through a messaging app means the list passes through that app's servers. The app itself never contacts a server, but the owner should confirm this is acceptable.

Status: done.

Decisions standing at the end of the rally:
- O-1 (owner non-negotiable): It must work with no account, no login and no sign-up of any kind.
- O-2 (owner non-negotiable): It must stay a single HTML file with no build step and no package install.
- O-3 (owner non-negotiable): It must never send the list to a server; the data stays on the two devices.
- P-3 (Codex): Exchange snapshots directly through two-way QR scanning; support numbered chunks and prohibit server-mediated sharing.
- P-4 (Codex): Merge per-item logical versions with deterministic device-ID ties and retained deletion records.
- P-5 (Codex): Show last received update and local changes since exchange; never claim live synchronization.
- P-6 (Claude Code): QR codes are scanned only with the in-app scanner, never the system camera; the list is never put in a URL.
- P-7 (Claude Code): Served from a static HTTPS address and installed to the home screen; the app asks for permanent storage.
- P-9 (Claude Code): Local file export and import as a backup, merged like a swap.
- P-10 (Codex): P-10: Freeze both outgoing snapshots before scanning; complete both directions before further edits.
- P-11 (Codex): P-11: Each local edit advances beyond every observed logical counter.
- P-12 (Codex): P-12: Storage persistence is best effort; backups must remain outside cloud-synced storage on the two devices.

Decisions dropped during the rally:
- P-1 (Claude Code): P-1: Sync goes through a link with the list after the # (QR code when together, any messaging app when apart). Edits merge per item, the newest edit wins, and deletions are remembered. — dropped because: Messaging transports violate O-3; one-way snapshots do not ensure convergence, and wall-clock ordering is unreliable.
- P-2 (Claude Code): P-2: The app never claims to be live and always shows the last time it synced with the partner. — dropped because: ‘Last synced with partner’ overstates what an unacknowledged snapshot proves; retain the prohibition on claiming live updates.
- P-8 (Claude Code): A deletion record is removed once the partner's swap shows they have it too. — dropped because: Partner acknowledgement does not prevent an older backup from resurrecting a deleted item; retain tombstones.
