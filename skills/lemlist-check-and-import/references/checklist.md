# The 40 checks

One numbering only: **L** (leads), **C** (sequence and copy), **E** (senders), **D** (draft and live campaign settings), **P** (post-import). A report never uses any other number. `scripts/report_manifest.py` is the executable source of this list and says exactly which IDs are expected at each moment.

Apply only the checks expected at the current moment, but never silently omit one. Every result needs evidence.

## Leads (L)

- **L1 Variables and fallbacks.** Every variable used by the sequence exists in the lead source. Empty-variable rates are measured and every variable that can be empty has a truthful fallback.
- **L2 Available channels and routing.** Every lead has at least one usable channel (email and/or LinkedIn) and is routed to the right campaign or branch.
- **L3 Duplicates inside the batch.** Detected by email, normalized LinkedIn URL (percent-encoding decoded, accents stripped), then full name + company. The same person under two addresses counts.
- **L4 Leads already in Lemlist.** Scan every campaign of the account, including paused and finished ones, by email, normalized LinkedIn URL, then name + company. A "probable duplicate" (same full name, same job title, same city, different company) is listed for a human decision and is never kept silently. Company-level matches follow the company policy chosen at setup (`all`, `replied`, `interested`, `none`; see `scripts/company_dedupe.py`).
- **L5 Email addresses.** Syntactically valid; belong to the company (domain coherent with the employer, or explicitly reviewed); personal addresses (webmail) removed unless the campaign has documented consent and the user approves.
- **L6 Identity quality.** Names in the right order and case, no title or company in a name field, salutation consistent, and a "colleague" variable never equals the lead itself.
- **L7 Language of lead, campaign and variables.** The language is determined explicitly, matches the target campaign, and variable values are in the language of the message where they appear.
- **L8 Contacts per company.** The maximum contacts per company chosen at setup is respected.
- **L9 Blacklist.** People and companies checked against the supplied blacklist before any paid enrichment, with the date of the last pass.
- **L10 Required extra fields.** Every extra field the campaign requires is present on every lead.
- **L11 Native company fields.** Native Lemlist fields are used whenever one exists (see `native-fields.md`); custom fields are justified and consistently named; company-field coverage is complete.

## Sequence and copy (C)

- **C1 Architecture and email threads.** Steps, channels, variants and conditions match the approved plan; conditions never prevent a required message from sending; follow-up emails stay in the thread of email 1.
- **C2 Delays.** Delays between steps match the approved timing, with a minimum gap between messages.
- **C3 Liquid syntax, fallbacks and agreements.** Every `{% if %}` has its `{% endif %}`, no orphan tag or unresolved variable, every branch rendered with representative and empty values, grammatical agreements correct (gender, plural, salutation).
- **C4 LinkedIn continuity.** Invitation, acceptance wait and follow-up messages are chained so that a lead who accepts receives the next message, and a lead without email still gets a complete path.
- **C5 Personalized content composition.** Personalized fragments (generated or variable) join the fixed text into correct sentences, with no repetition and no claim the data does not support.
- **C6 Signatures per channel and spacing.** The right sender signature appears in the right channel and position; exactly one blank line separates the closing phrase from the signature.
- **C7 Unsubscribe.** Uses the correct Lemlist token, resolves to a clickable link at preview time, and appears where the chosen policy and the applicable law require it.
- **C8 Whitespace and paragraph rendering.** Raw HTML and every rendered Liquid branch contain no double spaces between words, no space before commas or periods, no leading or trailing whitespace, no empty paragraphs, no consecutive blank lines, no malformed list.
- **C8bis LinkedIn media.** A GIF, image or video never appears after a sign-off or a sender first name, and arrives as an attachment rather than a plain-text link (only a real LinkedIn test confirms the latter).
- **C9 Email 1 A/B.** If email 1 has variants, both are complete and differ only by the intended element; variant A is never rewritten without approval.
- **C10 Hard-coded links.** Detect every fixed URL, test it (HTTP 200, content type), and only fall back to a human check when it cannot be tested.
- **C11 Register and cross-language consistency.** Same register (formal or informal) across the whole email, same meaning and same figures in every language version.
- **C12 Subject quality.** Concise, relevant, truthful, personalized where useful, and rendered with real variable lengths.
- **C13 Spelling and typography.** No typo, no mixed apostrophes, no space before punctuation, no stray HTML.

## Senders (E)

- **E1 Sending mailbox health.** Each mailbox is connected, warmed, with an acceptable reputation score and spam rate and a daily limit within the user's threshold; DNS and blacklist status are clean.
- **E2 Mailbox coverage per sender.** Assigned mailboxes versus connected mailboxes: no dead mailbox still attached, and a question to the user when the pool is under-used.
- **E3 Capacity available before the draft.** Estimated with the compliant mailboxes and the load of campaigns already running, without choosing a date for the user.

## Draft and live settings (D)

When the target campaign already exists, D2, D5 and D7 are read live and required in the pre-check; D1 is not applicable (nothing is written), D3 = E1 + E2, D4 = E3, D6 = C7.

- **D1 Source / Lemlist match.** The structure read back from Lemlist equals the approved plan.
- **D2 Reply, tracking and stop settings.** Open/click/reply tracking and stop-on-reply (including propagation to the whole company where intended) match the approved policy.
- **D3 Senders and connections.** The intended senders are attached to the right campaign and connected.
- **D4 Schedule and capacity.** Schedule, sending days, timezone, holidays and sender capacity give an acceptable completion date, computed with the real senders and the real schedule.
- **D5 Labels.** Campaign labels are correct and persist after being written.
- **D6 Real signatures and unsubscribe.** Signature and unsubscribe resolve correctly in the created draft.
- **D7 Lemlist readiness.** Lemlist's own readiness validation reports no blocking step error.

## After the import (P)

- **P1 Complete import.** Requested, added, removed and found-again volumes reconcile; every required field read back equals the approved source after Lemlist's known normalizations (see `scripts/import_leads.py`).
- **P2 Variables on 100% of the batch.** Every value used without a fallback is present on every imported lead.
- **P3 Lemlist renders.** Previews of every email, every A/B variant and every branch on a representative sample (at least 25 leads, more for large batches), covering leads with and without a colleague, generic and personal addresses. Also check that the company name looks like what the copy says (an email about "your hotel" must not go to a bakery).
- **P4 Real routing.** Leads sit in the right campaigns and branches; none is paused by mistake; none came from another path.
- **P5 CRM sync.** Only when expected at this stage.
The optional reply test is described in `SKILL.md`. It is a final recommendation, not one of the 40 checks.
