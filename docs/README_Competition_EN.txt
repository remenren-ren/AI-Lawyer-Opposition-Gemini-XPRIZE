AI Lawyer Opposition - Google Cloud Online Edition

START HERE

- START_Google_Cloud_Online.bat
- Reviewer account: demo
- Reviewer password: demo

PRODUCT ROLE

AI Lawyer Opposition is a legal-preparation and argument-expression reference
tool. It helps lawyers, legal-aid volunteers, and informed users organise a
matter, separate both sides' positions, identify weaknesses, prepare questions,
review evidence paths, and test likely attacks and rebuttals.

The software does not provide legal advice, decide a case, or replace review by
a qualified lawyer. Legal authorities, citations, translations, tactics, and
final wording must be checked before use.

ESTABLISHED ONLINE WORKFLOW

- Import PDF, Word, TXT, or JSON matter material.
- Organise positive-side and negative-side arguments and evidence.
- Add evidence manually when a recording, document, witness account, inspection,
  payment record, or other item is not already contained in the imported file.
- Allocate verified model providers to either side or allow every verified
  provider to participate.
- Review one complete matter across 18 legal and evidentiary dimensions.
- Run adversarial opposition and rebuttal preparation.
- Run single-point opposition while retaining the surrounding case arguments and
  evidence as context.
- Scan both sides for weaknesses and move selected weakness cards back into the
  opposing side's argument preparation.
- Run the optional Advanced 18-Dimension Review, where each dimension rereads
  the complete matter independently and produces a separate report.
- Export reports for lawyer review and client communication.

GOOGLE CLOUD REPLACEMENT STRATEGY

This edition keeps the established online user interface. Google Cloud products
replace the older online account, storage, logging, secret, and service
implementations behind that interface instead of creating duplicate workflows.

CUSTOMER-CONTROLLED DEPLOYMENT

Legal matters may contain privileged communications, confidential client data,
personal information, commercial records, litigation strategy, and protected
work product. For that reason, this product is supplied as software and does
not require customers to place legal data in a cloud account controlled by the
software vendor.

Each law firm, legal department, or other customer chooses and controls its own
data-security architecture. Where Google Cloud features are selected, the
customer deploys them into its own Google Cloud project and controls:

- the billing account, project, organization, deployment region, and service
  accounts;
- Firebase Authentication users and access policy;
- Firestore databases, security rules, indexes, retention, and deletion;
- Cloud Storage buckets, export policy, backup lifecycle, and recovery access;
- Cloud Logging scope, retention, monitoring, and audit access;
- Secret Manager secrets, rotation policy, and administrator permissions;
- Vertex AI location, model access, quotas, and processing policy; and
- Cloud Run deployment, ingress, identity checks, revisions, and shutdown.

The customer may instead choose direct model APIs, a private-network endpoint,
an approved internal law-firm model, or a local model. API keys, cloud
credentials, legal data, exported reports, logs, and operational costs remain
under the customer's selected account and policy. The software vendor provides
the application, deployment tooling, documentation, and optional implementation
support; it does not make the customer's professional confidentiality,
retention, disclosure, or jurisdiction decisions.

The local `demo` route exists only so competition reviewers can inspect the
software without registering or authorizing a personal cloud account. It is a
review convenience, not the production ownership or security model.

Installed or prepared integrations:

1. Gemini API
   Primary Google model route for case intake, long-context issue extraction,
   structured analysis, weakness review, and advanced 18-dimension review.

2. Firebase Authentication
   Provides configured email/password authentication and an installed
   `Sign in with Google` route. Firebase identifies the user before cloud
   settings are restored. These are alternative sign-in routes, not two
   consecutive logins.

3. Cloud Firestore
   Restores and synchronizes the provider profile assigned to the authenticated
   user. It also stores a matter index when a case is saved or loaded, while the
   full case text remains in the user-selected local file. Restored provider
   rows remain disconnected until the user presses Verify.

4. Cloud Run
   A deployable online orchestration and final-review service is included under
   `cloud_service`. Actual deployment is performed in the customer's selected
   Google Cloud project and requires that project to have billing enabled.

5. Cloud Storage
   Receives user-exported Markdown and HTML reports and completed advanced
   18-dimension reports through Cloud Run when a bucket is configured.

6. Cloud Logging
   Records sanitized provider, workflow, failure, case-file, and report events.
   Matter text, arguments, evidence, API keys, and tokens are excluded from
   routine operational logs.

7. Secret Manager
   Supplies the deployed Cloud Run session and vault secrets. Customer model
   keys remain subject to the selected deployment and account policy.

8. Vertex AI
   Provides an installed optional managed enterprise Gemini review route. The
   existing multi-provider architecture is not limited to one model company.

PINCH EVENT-BASED BILLING

The primary reception workflow uses Pinch for two client-authorised billing
events. Platform licence billing is not mixed into the client's legal-service
payments.

1. The first case-material organisation report remains free. Before the paid
   18-dimension review starts, the client sees the fixed report fee and
   authorises a Pinch payment source. Nothing is collected at authorisation.
   Successful generation and registration of the completed 18-dimension report
   is the event that submits the disclosed fixed charge.
2. Before entering the human-lawyer queue, the client sees and authorises the
   firm's hourly rate, billing increment, and maximum automatic amount. The
   timer starts only when the firm accepts the prepared matter. Delivery of the
   final lawyer-reviewed report ends the session, calculates billable time, and
   submits the authorised Pinch collection.

Every charge uses a stable nonce so retries cannot create a duplicate payment.
The audit trail records authorisation, timer start, timer end, amount, Pinch
payment identifier, and status. A failed collection is marked for attention; it
does not delete the report or silently issue a second charge.

Card details are tokenised in the client's browser by Pinch CaptureJS. The
application receives only a short-lived token and retains only Pinch payer,
source, and payment identifiers. It never receives or stores raw card details,
and no case narrative or report text is sent to Pinch. The local competition
launcher shows this workflow in the Pinch test environment and does not move
real money. Production requires the participating firm's approved Pinch
merchant route, activated payment-source permissions, signed webhook handling,
and its disclosed client engagement terms.

The separate desktop Payment Centre is retained as an earlier milestone-payment
prototype; the reception-first competition story uses the event-based workflow
above.

AI LAW FIRM RECEPTION - PRIMARY GEMINI COMPETITION ENTRY

The reusable Gemini competition positioning, one-sentence submission text, and
short video narration are stored in `GEMINI_COMPETITION_PRODUCT_POSITIONING.md`.

The competition copy now includes a client-facing conversational AI reception
layer at the Cloud service `/client` route. The client sees one clean chat box,
describes the matter and attaches available evidence. The AI asks focused
questions until the factual record and evidence inventory are sufficiently
complete. With explicit online-AI consent, the hidden case-classification engine
then organises the complete background, positive-side arguments and evidence,
and negative-side arguments and evidence. It does not conduct opposition or
weakness analysis at this stage, and the client may add or correct information.

If the client continues, registration or login is required. The hidden
18-dimension engine then reads the complete
intake, evidence context and first report to produce a whole-case weakness
review. The participating firm decides whether either AI stage is free,
token-funded, fixed-fee, subscription-funded or covered by another approved
arrangement. No product price is hardcoded.

After reviewing the reports, the client may expressly consent to human transfer.
The prepared dossier then appears in the authenticated `/lawyer/intake-queue`.
The interface explains that human contact now follows the firm's disclosed
hourly charging standard. The lawyer reads the complete dossier before using
the same conversation for focused questions, then delivers a final reviewed
report. Only after that delivery does the client decide whether to request
formal human legal service under the firm's own terms.

The primary competition launcher is `START_GEMINI_RECEPTION_DEMO.bat`, which
opens only the client reception at `http://127.0.0.1:8770/client`. The internal
dual-line lawyer interface is opened separately during the recording only to
explain the workbench behind the customer experience. The reception's case
organisation and 18-dimension review directly use `lawyer_software_bridge.py`,
which imports the existing online lawyer core and its verified provider routes,
dimension definitions, prompts, capacity splitting, and final display filter.

COMPETITION VIDEO SCOPE

The submitted video intentionally focuses on the competition-relevant client
reception, matter-organisation, online 18-dimension weakness-review, report
delivery, and human-transfer path. It is not a demonstration of the complete
lawyer platform. Major functions not shown include the full two-sided opposition
and rebuttal workflows, single-point opposition in whole-matter context, and the
offline/local system. A fuller technical demonstration can be provided on
request.

Production still requires activated Firebase client
authentication, Pinch webhook confirmation, and firm-controlled persistent
storage. See `AI_LAW_FIRM_RECEPTION_GUIDE.md`.

The software vendor does not receive the legal-service fee and does not sell or
monetise confidential legal-matter data. Production settlement requires the
participating firm's own Pinch merchant account or an approved managed-merchant
route.

CURRENT ACTIVATION BOUNDARY

- The Google Cloud CLI account is authenticated locally.
- Cloud Run deployment is prepared but not currently deployed because billing
  activation was deliberately deferred.
- Firebase Google sign-in is installed but requires a configured Firebase web
  application before it becomes active.
- Firestore synchronization requires the same Firebase project, Firestore
  database, and security rules.
- Cloud Storage, Cloud Logging, Secret Manager, and Vertex AI server routes are
  implemented and activate after Cloud Run is deployed with the required
  project services, bucket, and permissions.
- The local reviewer account remains available so competition judges do not need
  to register before inspecting the software.

COMPETITION SIGN-IN ROUTES

The normal competition route is `Sign in with Google`. It demonstrates Firebase
Authentication and allows the authenticated user's Firestore provider profile
to be restored on another computer when the Google Cloud deployment is active.

Competition reviewers are not required to create an account or authorize a
personal Google account. They may instead use the local software-review route:

- Account: `demo`
- Password: `demo`

The Google button and the software-account button are alternatives. A reviewer
uses one route, not both. Each new launcher session begins signed out. Provider
keys are hidden until one of these routes succeeds. Closing the launcher clears
the local session gate. Signing in restores provider configuration only; every
provider still requires an explicit Verify action before it can process data.

ACCOUNT AND PROVIDER SAFETY

Signing in restores settings; it does not automatically connect a model or
upload a matter. A restored provider must still be verified inside the online
application. Local files containing API keys, sessions, drafts, cases, or run
reports are excluded from distribution and source-control packaging.

When several APIs are connected, one provider reaching its quota or request-rate
limit does not prevent other verified providers from continuing when the
selected workflow supports provider failover or multi-provider review.

CONFIDENTIALITY

The online edition may transmit matter content to verified external model
providers. Data Redaction should be enabled for sensitive matters unless the
user has authority to send original text. A separately distributed private or
offline edition may later be recombined with this online edition after the
Google Cloud online workflow is complete.

PRIVACY-SAFE USAGE METRICS

The public competition service uses Google Cloud Firestore to retain aggregate,
deduplicated evidence of product use. Analytics events contain only an event
type, a server timestamp, and a one-way anonymous key. They do not contain a
name, email address, case narrative, legal category, evidence, arguments,
report text, uploaded documents, or any description of what the matter was.

These totals can show anonymous browser visits and progression through product
stages such as matter organisation, advanced review, PDF download, or lawyer
handoff. They are not claimed as verified people, customers, endorsements, or
proof of any confidential matter. The inability to reconstruct the submitted
case from analytics is a deliberate confidentiality safeguard, not a missing
feature.

The public competition deployment also defaults to privacy-first processing.
Case narratives, evidence, conversations and reports remain available only in
the active processing session and are not written to Firestore or local
persistent matter storage. The user must keep the page open and download the
report before leaving; cross-session matter recovery is intentionally disabled.
Any later production retention must be expressly consented to and remain under
the participating law firm's own access, retention and deletion controls. It is
never reused as vendor analytics.

PATENT AND LICENCE NOTICE

This software incorporates a patent-pending multi-task AI processing
architecture that organises a matter across coordinated legal dimensions while
preserving the relationship between each task and its result. Commercial use,
copying, redistribution, or derivative deployment requires permission from the
author and remains subject to the applicable licence and patent rights.

MAIN FILES

- Google_Cloud_Online_Launcher.py
- Nido_StrikeOver_Online_EN.py
- Nido_Advanced_18D_Review_EN.py
- Nido_Advanced_Single_Point_2R_EN.py
- Nido_Advanced_Main_Opposition_2R_EN.py
- firebase_google_login_bridge.py
- cloud_service/app.py
- ONLINE_CLOUD_REPLACEMENT_MAP.md
- CLOUD_INTEGRATION_STATUS.md

ADVANCED SINGLE-POINT TWO-ROUND REVIEW

The existing Standard Single-Point Review remains available without changing
its established workflow. The Single-Point AI Review control now also offers an
Advanced 18-Dimension Two-Round Review for difficult or high-value issues.

In Round 1, each of the 18 legal review dimensions independently rereads the
complete prepared matter, including both sides' arguments and evidence, and
attacks the selected point from that dimension's own perspective. In Round 2,
each dimension rereads the complete matter again together with the complete
Round-1 attack dossier, then prepares the strongest fact-aware response for the
side that owns the selected point. This prevents the point from being debated in
isolation when another argument, document, timeline fact, or evidentiary gap may
support or defeat it.

The reasoning prompts do not force the model into a rigid card schema. Each
model is instructed to write natural, concrete advocacy analysis first. The
desktop software then preserves and organises the resulting work into 18
Round-1 attack memoranda, 18 Round-2 response memoranda, a Round-1 attack
dossier, and one combined HTML report with locally highlighted key passages.
The full workflow therefore uses 36 review calls and maintains a separate
failure boundary and source record for every dimension.

This feature is a lawyer-assistance and drafting-reference workflow. It helps a
lawyer inspect how an opponent may challenge one point and how that point may be
answered using the complete matter. It does not make a final legal decision or
replace qualified lawyer review. External calls follow the privacy and
redaction mode selected by the user before the review begins.

ADVANCED MAIN OPPOSITION TWO-ROUND REVIEW

Start Opposition now preserves the established Standard Opposition and offers
an optional Advanced Main Opposition 2R route for difficult or high-value
matters. The standard route is not replaced or internally changed.

In Round 1, negative-side counsel is instantiated across 18 independent legal
dimensions. Every dimension rereads the complete prepared matter, including
both sides' arguments and evidence, then develops the strongest whole-case
attack supported by its own perspective. In Round 2, positive-side counsel is
instantiated across the same 18 dimensions. Every dimension rereads the complete
matter and the complete Round-1 attack dossier before preparing its response,
qualification, evidentiary answer, or justified counterattack.

The model is allowed to write natural advocacy rather than fill a rigid form.
The software then preserves 18 attack memoranda, 18 response memoranda, the
complete Round-1 attack dossier, a source manifest, and a combined HTML report
with locally selected key passages. The 36-call workflow maintains an
independent failure boundary for every dimension and remains lawyer-preparation
reference material rather than a final legal conclusion.
MATTER STORAGE NOTICE

The current public competition service processes material temporarily and is
not a legal file-storage or archival service. AI Lawyer Opposition does not
undertake to preserve case narratives, uploaded evidence, conversations or
reports. Download required reports before leaving the active session. If the
page is closed, connectivity is lost, the session expires or the service is
recycled, the material may no longer be available and cannot be restored by the
software vendor.

In a future participating-law-firm deployment, any authorised matter retention
will occur inside the firm's controlled environment. The law firm is
responsible for client consent, access control, professional confidentiality,
backup, retention periods, legal holds and secure deletion. AI Lawyer
Opposition supplies the software and computation workflow; it is not the
custodian of the firm's retained client files.
