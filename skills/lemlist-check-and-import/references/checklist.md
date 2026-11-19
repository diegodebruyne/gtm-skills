# The 37 checks

Apply only checks relevant to the current stage, but never silently omit one. Each result needs evidence.

## Leads and targeting

1. Exact source, view, filters and expected row count are confirmed.
2. Every lead has a stable identifier and at least one usable contact channel.
3. Required names, company fields and campaign-routing fields are present.
4. Email addresses are syntactically valid.
5. LinkedIn profile and company URLs are normalized and valid.
6. Duplicate people inside the incoming batch are detected by email, LinkedIn URL, then name + company.
7. Duplicate people across all campaigns in the Lemlist account are detected, including paused and completed campaigns.
8. People and companies are checked against the supplied blacklist before paid enrichment.
9. The maximum contacts per company is respected.
10. Personal email addresses are removed unless the campaign has documented consent and the user approves them.
11. Email domain and employer/company are coherent or explicitly reviewed.
12. Contact language is explicitly determined and matches the target campaign.
13. Job title, persona tier and qualification match the targeting rules.
14. Every variable used by the sequence exists in the lead source.
15. Empty-variable rates are measured and every incomplete variable has a truthful fallback.
16. Native Lemlist fields are used when available; custom fields are justified and consistently named.
17. Variable values are written in the same language as the message where they appear.

## Copy and sequence

18. Liquid syntax is valid and contains no orphan tag or unresolved variable.
19. Every conditional branch is reachable and tested with representative data.
20. Rendered grammar, agreements, salutations and tone are correct for each language.
21. Every subject is concise, relevant, truthful and rendered with real variable lengths.
22. Whitespace & paragraph rendering: raw HTML and every rendered Liquid branch contain no double spaces between words, spaces before commas or periods, leading/trailing whitespace, empty paragraphs, consecutive blank lines or malformed lists; exactly one blank line separates the closing phrase from the signature.
23. Links and native media resolve correctly and match what the copy promises.
24. Email and LinkedIn signatures use the correct sender and appear in the correct channel and position.
25. Unsubscribe handling uses the correct Lemlist token and appears where required by the chosen policy and applicable law.
26. The sequence architecture matches the approved plan: steps, channels and variants.
27. Delays between steps match the approved timing.
28. Conditions route leads to the intended branches and never prevent a required message from sending.

## Lemlist configuration and delivery

29. The intended senders are assigned to the correct campaign.
30. Every assigned mailbox is connected and active.
31. Mailbox reputation and daily limits meet the user's thresholds.
32. Open/click/reply tracking and stop-on-reply settings match the approved deliverability policy.
33. Schedule, sending days and timezone match the target audience.
34. Campaign labels are correct and persist after being written.
35. Sender capacity, delays, working days and holidays produce an acceptable campaign completion date.

## Import and final proof

36. Imported leads and CRM records match the approved batch, counts, routing and required fields after read-back.
37. Message previews cover every branch and a representative lead sample; launch remains blocked until the user gives a separate explicit approval.
