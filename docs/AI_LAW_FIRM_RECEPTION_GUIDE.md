# AI Law Firm Reception

## Product role

The client-facing `/client` page is the branded online AI reception layer in
front of the existing lawyer tools. It reduces unstructured intake time without
presenting the AI as a lawyer or allowing it to accept a legal engagement.

## Gemini Competition Positioning

AI Lawyer Opposition has evolved from a lawyer-facing analysis tool into an
AI-powered law-firm reception and matter-preparation system. Its value is not
limited to producing strong AI analysis. It automates one of the most
time-consuming parts of legal practice: turning an unstructured first client
conversation into a matter that a lawyer can understand and act on quickly.

The product creates value in three connected ways:

- The client sees one clean conversational interface and does not need to learn
  the firm's internal legal-analysis software.
- Gemini turns a fragmented story and mixed evidence into a complete matter
  record containing the factual background, both sides' positions, and the
  evidence associated with each side. A separate 18-dimension workflow then
  investigates material weaknesses across the whole matter.
- The lawyer does not begin with a blank intake call. The lawyer receives a
  prepared matter dossier resembling a structured case record, including the
  client conversation, evidence index, organised case report, weakness report,
  unresolved points, and later communications.

This makes the product easier for law firms to evaluate than a general claim
that "AI can analyse legal cases." The practical proposition is measurable:
reduce unstructured first-consultation time, improve the quality of matters
that reach a lawyer, and reserve professional time for high-value legal
judgment and client service.

### Deliberate service boundaries

The workflow keeps four responsibilities separate:

1. **Facts and material organisation** - Gemini gathers missing details and
   classifies the complete case record without attacking either side or giving
   legal advice.
2. **Systematic weakness investigation** - the separate 18-dimension workflow
   reviews the prepared matter for material vulnerabilities and evidentiary
   limits.
3. **Lawyer judgment and advice** - a human lawyer receives the complete dossier,
   contacts the client with focused questions, applies professional judgment,
   and delivers the lawyer-reviewed report.
4. **Formal legal service** - only after the final report does the client decide
   whether to enter formal human representation under the participating firm's
   engagement and charging terms.

This boundary reduces the risk that a client mistakes preliminary AI-generated
case organisation for a lawyer's formal legal opinion.

### Reliability and delivery priorities

The next phase focuses on making the workflow reliable, clear, auditable, and
deployable rather than simply adding more AI features:

1. Give the intake conversation a clear stopping rule: the record may be ready,
   incomplete but usable at the client's request, or missing a critical item
   that must be marked as unconfirmed.
2. Present a concise client summary first, with the full report available on
   demand. Show the most significant weakness findings first and allow the
   complete 18-dimension report to be expanded.
3. Triage urgent matters before ordinary intake, including imminent hearings or
   appeals, limitation periods, detention, personal safety, eviction, and
   immigration deadlines, and route them to immediate human assistance.
4. Display the participating firm's charging boundary clearly before human
   involvement: the applicable hourly or consultation rate, any initial fee,
   when time starts, and whether the action requests contact or creates a formal
   engagement.
5. Give lawyers a summary-first matter page showing the client's objective, core
   timeline, parties, key evidence, most serious weaknesses, missing material,
   urgent deadlines, and unresolved AI uncertainty before the full reports.
6. Where a client expressly consents to matter retention, preserve the required
   professional audit record only inside the participating firm's controlled
   environment, under its access, retention and deletion policy. Vendor usage
   analytics must never contain client input, uploaded files, AI questions,
   answers, report text, or the subject of the matter.
7. Add persistent accounts, matter storage, firm-level permissions, payment
   confirmation, retention controls, and secure deletion before production use.

### One-sentence competition description

> An AI-powered law-firm reception system that transforms a client's fragmented
> story and evidence into a lawyer-ready matter dossier, completes a systematic
> weakness investigation before human involvement, and lets lawyers begin with
> the complete case rather than an unstructured first conversation.

## Conversational client journey

The customer sees one clean conversation window rather than the internal lawyer
interface or a large intake form.

1. **AI intake conversation** - the client describes the matter and may attach
   evidence. The AI asks only focused follow-up questions about missing facts,
   dates, positions and material.
2. **Case-material organisation** - once the record is sufficiently complete,
   the classification engine returns the complete background, positive-side
   arguments and evidence, and negative-side arguments and evidence. It does
   not attack either side, scan weaknesses, assess merits, recommend strategy
   or predict an outcome. The client may correct or supplement the record.
3. **Client account boundary** - a client who chooses deeper analysis registers
   or logs in before the 18-dimension workflow begins.
4. **18-dimension weakness review** - the first report, conversation and
   evidence are passed to the whole-case diagnostic engine. The participating
   firm decides whether this stage is free, token-funded or paid and configures
   its own amount and wording.
5. **Human lawyer contact** - after the weakness report, the client may request
   human involvement. The interface warns that lawyer contact now follows the
   firm's disclosed hourly charging standard. The lawyer receives the complete
   dossier before asking targeted questions in the same conversation.
6. **Final report and formal-service decision** - the lawyer delivers the final
   reviewed report. Only then is the client asked whether to enter formal human
   legal service. All later pricing and engagement terms remain controlled by
   the participating firm.

The customer never sees the internal classification, weakness-scan or lawyer
working interfaces. Those engines run behind the branded conversation page.

## Firm-configurable commercial policy and Pinch events

The workflow defines service stages, not mandatory prices. The demonstration
uses a free first case-material report and two Pinch-authorised events. The
client authorises the fixed 18-dimension report fee before analysis, but the
charge is submitted only after the complete report is successfully generated.
Before human contact, the client authorises the disclosed hourly rate, billing
increment, and maximum amount. The timer starts when the firm accepts the
prepared matter and stops when the final lawyer-reviewed report is delivered.
The calculated amount is then submitted to Pinch. Firms may configure the
amounts, but the trigger, authorisation, cap, and audit boundaries remain.

## Local competition demonstration

Use `START_GEMINI_RECEPTION_DEMO.bat`. It starts the reception-only local service
at `http://127.0.0.1:8770/client`. The dual-line lawyer interface is not part of
this customer-facing launcher; it is opened separately only when the recording
needs to explain the internal workbench. The local competition mode has a
clearly labelled Pinch Sandbox authorisation before the detailed scan, an
automatic report-delivery billing event, and an hourly timer that ends when the
lawyer delivers the final report. It moves no real money.

The case-material report and 18-dimension review are routed through
`lawyer_software_bridge.py`. The bridge directly imports the existing online
lawyer core, verified provider configuration, dimension definitions, structured
weakness prompt, capacity splitting, and final no-material-weakness filter.

The launcher routes intake analysis to the first locally verified Gemini
provider, then to another verified provider if Gemini is not configured. If no
provider is available, it returns a labelled local structured preview rather
than falsely claiming semantic AI analysis succeeded.

### Scope of the competition video

The submitted video deliberately demonstrates only the functions directly
relevant to this competition: the client-facing AI reception journey, matter
organisation, the online 18-dimension weakness review, report delivery, and the
transition to human legal service. The internal lawyer workbench is shown only
briefly to establish that the reception page is connected to a purpose-built
legal workflow rather than a general question-and-answer chatbot.

The video is not a demonstration of the complete AI Lawyer Opposition platform.
Major capabilities outside the recording include the full two-sided opposition
and rebuttal workflows, single-point opposition in whole-matter context, and the
offline/local system for firms that require a different confidentiality and
deployment model. A fuller technical demonstration of these capabilities can be
provided on request.

Edit `law_firm_reception.local.json` or set `NIDO_LAW_FIRM_NAME` to display the
participating firm's name on the welcome and reception screens.

## Production boundaries

### Matter storage responsibility

The current public and competition version is a temporary processing service,
not a legal file-management or archival service. AI Lawyer Opposition does not
undertake to preserve a client's case narrative, uploaded evidence,
conversation, intermediate analysis or generated reports. The user must review
and download every required report before leaving the active session.

If the browser is closed, the connection is lost, the active session expires,
or the service instance is recycled, the matter and report might no longer be
available and cannot be restored by the software vendor. Account sign-in does
not create a vendor-held case archive in privacy-first mode. The vendor is not
responsible for preserving or reconstructing material that the user did not
download.

When the system is later deployed for a participating law firm, any authorised
matter retention must occur only inside that firm's controlled environment.
The law firm—not AI Lawyer Opposition—must determine and administer what is
retained, client consent, access control, confidentiality, encryption, backup,
retention periods, legal holds, export and secure deletion. AI Lawyer
Opposition supplies the software and computation workflow; it is not the
custodian of the law firm's retained client files.

### Privacy-preserving usage evidence

The competition service uses a separate Google Cloud Firestore analytics
collection to count anonymous, deduplicated product events. The retained event
record is limited to the event type, server timestamp, and a one-way anonymous
key. It does not store names, email addresses, case narratives, legal categories,
evidence, arguments, reports, or uploaded documents.

Accordingly, usage totals may demonstrate that browsers reached the service and
that non-demo workflows progressed through stages such as matter organisation,
advanced review, PDF download, or lawyer handoff. They do not identify a person
or disclose what legal problem was submitted. This limitation is intentional:
client confidentiality takes priority over stronger but intrusive proof of use.

Anonymous product analytics and legal-matter records are separate concerns.
The public competition deployment sets `NIDO_PRIVACY_FIRST_MODE=true`. Case
narratives, evidence, conversations and reports remain only in the active
server process long enough to perform the requested workflow; they are not
written to Firestore or the local session-state file. Background review is run
inside the active request rather than through a persistent queued matter. The
page tells the user to remain connected and download the report before leaving.

Any later production matter retention must be expressly consented to and
controlled by the participating law firm, not collected or repurposed by the
software vendor as marketing analytics. A firm-controlled deployment may set
`NIDO_PRIVACY_FIRST_MODE=false` only after its storage, access, retention,
deletion and professional-confidentiality controls have been approved.

- Firebase client authentication still needs an activated Firebase web app.
- Production must use Pinch CaptureJS, an approved reusable Source or direct
  debit Agreement, and verified Pinch webhooks. Test-mode approval is not proof
  of final settlement.
- Client evidence should be retained only under the firm's approved storage,
  retention, access-control and deletion policies.
- The privacy-first public intake and conversation state is temporary and is
  intentionally lost when the active service process ends. A production firm
  may retain consented structured intake state only in its own approved
  Firestore project and evidence only in its controlled storage environment.
- Urgent or high-risk matters must be routed to immediate human assistance.
- AI output is preliminary information and case organisation, not a legal
  opinion or acceptance of an attorney-client relationship.

## Deployment

The client router is included in `cloud_service/app.py`. The Docker image copies
the reception router, event-billing adapter, Pinch API adapter, and client page.
Deploying the Cloud Run service therefore publishes both the existing provider
portal and the new `/client` route. Pinch credentials must be supplied through
deployment secrets or environment variables, never baked into the image.

## Public launch review tiers — 22 July 2026

**Major update — 22 July 2026:** independent deep scanning has been added,
advanced analysis access is now open to public testers, and all rapid and
advanced review fees are waived during the competition and early public-testing
period.

The public prototype now exposes two consecutive review depths after the free
case-material organisation report:

1. **Rapid 18-angle review — normally AUD 5, currently free.** One contextual
   model review reads the organised facts, both sides' positions and available
   evidence through all 18 angles. It is designed for a fast first map of the
   client's weak points and gaps in the other side's position.
2. **Independent 18-dimension deep review — normally AUD 88, currently free.**
   After the rapid report, the client may choose a second layer in which every
   dimension independently rereads the complete matter and produces its own
   self-contained report. The 18 reports are combined into one browser report
   and one downloadable PDF.

Both fees are waived during the competition and early public-testing period;
no card or payment authorisation is requested. Before the independent review
starts, the interface warns that it normally takes about 10–15 minutes. In the
privacy-first public deployment the page must remain open, because case content
and reports are not written to persistent matter storage.

The designated competition account is the sole exception to the public payment
waiver. It displays one **Pinch Sandbox AUD 5 authorisation and post-delivery
payment event** so judges can verify the event-based payment integration. The
screen states that this is a sandbox demonstration and no real money is charged.
Ordinary public accounts continue to receive both tiers free during the offer.

The production law-firm edition may later enable either tier, change its price,
bundle the deep review with lawyer engagement, or omit it entirely. Pricing and
retention remain law-firm-controlled deployment settings rather than fixed
legal-service terms imposed by the software vendor.
