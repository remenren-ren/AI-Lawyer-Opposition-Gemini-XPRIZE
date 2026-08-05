# AI Lawyer Opposition - New Description Draft

This software incorporates a patent-pending multi-task AI architecture that can multiply Gemini's effective legal-analysis coverage by organising one case into multiple coordinated legal dimensions within a structured model call.

Status: working draft. This file is separate from the previous web-version description files.

## Current Product Route

This version is based on the original dual-line desktop launcher:

- Offline Version: local-side workflow for sensitive or confidential matter preparation.
- Online Version: model-assisted adversarial legal-preparation workflow.

## Six Operating Modes and Product Boundary

The software offers six practical operating modes:

1. **Online with Data Redaction**: the real matter is redacted before being sent to verified model providers.
2. **Online with Original Text**: the user may authorize verified providers to process original text for low-sensitivity or already-redacted matters.
3. **Offline Client with Redacted AI Assistance**: the desktop workflow remains local while an authorized model step receives only redacted material.
4. **Offline Client with Authorized Original-Text AI Assistance**: the user expressly permits a verified provider to process original matter text from the desktop client.
5. **Fully Local Mode**: no external API is called; local functions organize the matter and perform direction-level weakness checks.
6. **Synthetic-Case Privacy Mode**: the real matter remains local, fictional analogue matters are generated locally, and only selected fictional cases may be sent to verified models. Findings from this route belong to the fictional cases and are not automatically mapped back as findings about the real matter.

Law-firm internal models, private servers, Cloud Run gateways, Vertex AI deployments, and customer OpenAI-compatible endpoints are supported deployment routes. They do not create a seventh analysis mode; the privacy classification still depends on whether original or redacted matter content is transmitted.

## Online Opposition and Single-Point AI Review

The Online Version provides both full adversarial review and focused single-point review. Full opposition examines the case through the selected legal-review dimensions using the positive and negative side frames. Single-Point AI Review allows counsel to select one argument, evidence item, attack point, or question while keeping the complete matter context available.

The single-point workflow sends the selected point, full case background, both sides' arguments, and both sides' evidence to verified providers, subject to the user's redaction choice. Each participating provider can identify:

- how the opposing side may attack the point;
- which existing arguments or evidence support, contradict, qualify, or change it;
- concrete questions counsel may ask;
- how the point-owning side may respond;
- the likely counter-response and an effective answer;
- missing facts, documents, or evidence that should be prepared.

This matters because a single proposition rarely stands alone. Another document, admission, timeline entry, legal argument, or item of opposing evidence may strengthen or defeat it. The feature gives lawyers a focused reference result without losing the relationship between the selected point and the rest of the case. All output remains advocacy-preparation and drafting reference material subject to lawyer review; it is not legal advice or a final legal determination.

The Offline Version does not present local function output as lawyer-style single-point debate. Its role is confidential matter preparation, local case organization, local weakness-direction scanning, and synthetic-case privacy workflows. Model-assisted single-point attack, defence, counter-response, and evidence-path generation belong to the Online Version.

We are no longer using the earlier web-version submission route as the main product description. Some material from previous descriptions may be migrated later, but only after review. Web login, web portal storage, and web-only deployment language should not be copied automatically.

## Core New Point: Gemini as API Configuration Assistant

This version can use Gemini as the first verified model provider and as an API configuration assistant.

After Gemini is verified, a user can enter a rough AI provider name, model name, API URL, or customer-provided endpoint. The software can ask Gemini to classify the likely API type and suggest configuration fields, including:

- provider name;
- adapter type, such as Gemini native or OpenAI-compatible;
- base URL;
- recommended model name;
- confidence level and short explanation.

This reduces the need for users to understand different API formats. For example, Gemini native APIs use a different request format from OpenAI-compatible APIs. The software can use Gemini to help identify the correct connection style before the user performs final verification.

Gemini-powered discovery is not treated as final proof that an API works. It is a setup assistant embedded into the provider verification flow. The software still requires a Verify step to confirm:

- whether the API key is valid;
- whether the model exists;
- whether the account has permission;
- whether quota is available;
- whether a private or customer endpoint actually follows the expected response format.

## API Discovery and Default Library Update

The intended workflow is not repeated guessing. The product should support a one-time discovery and verification loop:

1. The user enters a new AI provider name, API URL, model hint, or customer endpoint.
2. The user clicks Verify.
3. If the provider is not already in the local default library, the software uses Gemini and available web/API documentation lookup to identify the likely connection method before running the actual API verification.
4. Gemini helps extract the adapter type, base URL, request format, model name, and authentication style.
5. The software runs the first verification attempt against the actual API.
6. Only after the first successful verification, the software saves the provider profile into the local default library. Unverified provider inputs are not treated as reusable defaults.
7. On future use, the same provider name can be selected directly from the default library without repeating online discovery.

This means Gemini is used as a discovery assistant only when the provider is new or unknown. Once a provider is confirmed, the software treats it as a known local profile.

The default library entry should store at least:

- provider display name;
- aliases and likely user input names;
- adapter type, such as Gemini native or OpenAI-compatible;
- base URL;
- default model name;
- verification status metadata;
- last verified time;
- whether the profile was built in, manually added, or Gemini-discovered.

This gives the software a growing practical provider library while keeping the final connection test under software control.

## Competition Demo Login and Cloud Configuration Restore

The competition build can use Google Firebase Authentication and Firestore as an optional account-and-configuration recovery layer, while keeping the user-facing login simple. The launcher shows only:

- Account: `demo`
- Password: `demo`

Firebase Authentication verifies whether the account and password are valid. After authentication, the software receives a user identity token and user ID. Firestore can then use that authenticated user ID to retrieve that user's saved provider configuration.

The Firebase project settings are not shown in the normal interface and are not hard-coded in the application code. They are supplied by an administrator deployment file:

- `admin_cloud_config.local.json` for a real deployment;
- `admin_cloud_config.example.json` as the non-secret template.

The launcher reads this deployment file if it exists. If the deployment file is absent, `demo / demo` still works as a local reviewer sign-in, but no cloud provider restore is attempted.

The Firestore document stores the user's provider configuration, such as provider names, endpoint URLs, model names, and optional saved API keys when the deployment policy allows it. Restored provider rows are always marked as not verified. The user must open Online or Offline and click Verify before any restored provider becomes an active model connection.

This adds a Google Cloud-backed configuration recovery path without asking reviewers or ordinary users to type long API strings or cloud project identifiers. It also avoids hidden hard-coded cloud settings in the codebase.

This recovery path is also useful for private law-firm model deployment. If a law firm exposes its internal model through a private endpoint, local OpenAI-compatible service, Vertex AI/Cloud Run gateway, or other approved URL, the user can add that endpoint as a provider once. After successful configuration and verification, the account configuration can remember the provider name, endpoint URL, model name, and permitted key material according to the deployment policy. When the same user signs in on another computer, the software can restore the internal model profile without requiring the user to manually remember or retype the long private URL.

## Product Value of This Point

The product is not limited to a fixed list of model providers. A law firm, individual lawyer, or customer can add new model endpoints more easily, including private endpoints, Cloud Run gateways, local OpenAI-compatible services, or new commercial AI providers.

This supports a multi-API legal workflow without forcing users to manually research each provider's API format. Gemini acts as a setup guide, while the software remains responsible for verification and structured use inside the adversarial legal-preparation process.

The desktop edition also supports side-specific model allocation through a dedicated selection dialog. After providers are verified, the user can tick which APIs should assist the positive-side lawyer role and which APIs should assist the negative-side lawyer role. A provider can be assigned to one side, both sides, or neither side. If no provider is selected for a side, that side uses "Full verified providers" by default. This is intended to reduce same-model convergence and better preserve the adversarial nature of legal preparation: each side can be represented by an independently selected model stack rather than a single model trying to persuade itself.

Each additional verified API expands the adversarial bench. Instead of treating multiple APIs as simple backups, the software can treat each connected model provider as a separate model-company perspective. For each provider, the system can apply the selected 18 attack dimensions, meaning one more verified provider effectively adds another 18-dimension lawyer set to the review.

The same route controls are present in the Offline Version. In Offline, the local opposition and weakness-scan core remains available without sending the matter to an external model. When the user authorizes external assistance, the saved positive-side and negative-side provider routes tell the software which verified model provider should assist each side or whether all verified providers should participate.

## Multilingual Intake and Client-Language Output

The product can accept multilingual case materials, including Chinese or mixed-language facts, and generate structured legal-preparation outputs in the user's preferred language.

This is not treated as simple word-for-word translation. The workflow uses verified model providers such as Gemini to understand the substance of the client's facts, separate legal issues and arguments, identify weaknesses, and then express the result in a language the lawyer or client can actually use.

This creates practical value during early case intake:

- clients can describe facts in their own language without first preparing a legal translation;
- lawyers can receive organized issue, argument, evidence, and weakness summaries without spending the first meeting only resolving language barriers;
- ordinary users can read the system's reference output in a familiar language, reducing misunderstanding and ambiguity;
- legal-aid or volunteer-lawyer settings can support more multilingual users with faster first-pass review.

The target output language can therefore be part of the matter-preparation workflow. For example, Chinese source facts can be converted into English legal-preparation output for an English-speaking lawyer, or the same analysis can be expressed in the client's own language for easier client review.

## Opponent-Perspective Simulation with SWAP

The Online Version includes a SWAP workflow that can instantly reverse the positive-side and negative-side materials.

This feature is intended for opponent-perspective simulation. A lawyer or user can first enter their own arguments and evidence, then switch sides with one action to test how the matter may look from the opposing party's position. Instead of manually copying, reorganizing, and re-labeling arguments and evidence one by one, the software preserves the structured panels and allows the adversarial workflow to continue from the reversed perspective.

This is useful because legal risk is often hidden by the user's own narrative. A client may believe their position is strong, while the opposing lawyer may attack facts, causation, burden of proof, document gaps, proportionality, procedure, or legal characterization from a different angle.

The SWAP function supports:

- quick simulation of how an opposing lawyer may attack the user's position;
- faster stress-testing of arguments and evidence;
- reduced manual reorganization work during adversarial review;
- lower omission risk when switching perspectives;
- clearer client communication when explaining why an apparently strong case still has attackable weaknesses.

This makes the product different from manually asking an AI model isolated questions. The software keeps the adversarial case structure intact and lets the user move between perspectives without rebuilding the matter from scratch.

## Opponent Objective to Attack Means

The workflow can also start from a very small amount of adversarial information. The user does not need to manually list every possible opposing argument at the beginning. If the user knows only the opponent's objective, the software can use that objective as the seed for structured opponent-side construction.

For example:

- "The opposing party argues that the patent is invalid."
- "The other side denies contractual liability."
- "The respondent says the claimed loss was not caused by its conduct."

From that objective, the software can generate likely opposing methods, such as invalidity grounds, lack of support, obviousness routes, causation attacks, evidentiary gaps, procedural objections, burden-of-proof arguments, or alternative factual narratives. Those methods are then placed into the positive/negative side frames instead of being left as a free-form chat answer.

After the opponent-side means are generated, the Weakness Scan can run again against those generated routes. This creates a two-stage preparation flow:

1. The user supplies the matter text and a short opponent objective.
2. The software constructs likely opponent methods and side-specific argument frames.
3. Weakness Scan tests both the user's position and the generated opponent routes across the selected attack dimensions.
4. The lawyer can add useful weaknesses into the argument panels or tactic-combo workflow.

This is especially useful for patent, contract, and early intake matters. A user may not know how an opponent will frame the legal attack, but they often know the opponent's desired outcome. The software converts that outcome into likely legal attack means, then uses the structured workflow to test and refine them.

## Multi-Dimension Attack Search

The product does not rely on one generic "analyze this case" prompt. It uses selectable attack dimensions so that the same matter can be tested from multiple legal, factual, procedural, evidentiary, and strategic angles.

Examples include:

- factual challenge;
- legal application;
- precedent resistance;
- logic gap;
- procedural defect;
- causation and damage;
- quantum dispute;
- burden of proof;
- legal text interpretation;
- comparative fault;
- public policy;
- reverse reasoning;
- cross-domain or cross-jurisdiction weapon;
- counterfactual test;
- proportionality test;
- narrative deconstruction;
- systemic risk amplification;
- missing evidence.

Reverse Reasoning is important because it starts from the desired outcome or the opponent's strongest possible story and works backward to ask what facts, proof, and assumptions must be accepted for that story to survive. This helps expose hidden dependency points and backup-line failures.

Cross-Domain / Cross-Jurisdiction Weapon is important because some weaknesses only appear when adjacent domains are considered, such as platform rules, regulatory complaints, consumer-protection logic, administrative pressure, professional standards, or comparable approaches in another jurisdiction. The software treats these as strategic reference and pressure tools, not as automatic binding law.

This multi-dimension design helps reduce omission risk. A lawyer, legal-aid worker, or ordinary user does not have to manually remember every possible attack angle. The software provides a structured checklist of adversarial lenses and then lets useful findings flow back into the argument panels or tactic-combo workflow.

## Structured Multi-Task AI Processing

The competition build treats one legal matter as the shared target and the selected opposition dimensions as a structured set of review tasks. Instead of sending the full case again in one separate API request for every dimension, the system can submit the case context once and request multiple dimension-linked findings within the same structured model call.

Where provider capacity permits, one API call can process all 18 dimensions. Each dimension returns its own weakness conclusion, relevant facts, evidence requirements, questions, defence preparation, and result position. Where a provider requires smaller batches because of account quota or service capacity, the workflow still groups dimensions into substantially fewer calls than the number of review tasks and can continue through other verified APIs.

This provides several practical advantages:

- the case background, evidence context, and legal setting do not need to be repeated for every dimension;
- repeated token consumption is reduced;
- API round-trip latency is reduced;
- each weakness remains linked to the dimension that produced it;
- lawyers receive a coordinated multi-angle review rather than a collection of unrelated generic answers;
- when multiple APIs are connected, one provider reaching its computation or quota limit does not prevent other verified providers from continuing the remaining analysis.

Competition-facing summary:

> Our system analyses one legal case across multiple opposition dimensions in a single structured AI call, instead of sending one request per dimension. This reduces repeated context, lowers token use, avoids repeated API latency, and keeps each weakness result linked back to its corresponding legal dimension.

Patent pending. Patent applications have been filed for the underlying multi-task AI processing architecture. The competition materials describe the product-level benefit and implementation outcome without disclosing internal patent-sensitive mechanisms. This architecture is intended to create a technical barrier against direct copying.

## Intellectual Property and Licence Notice

Copyright (c) 2026. All rights reserved. Except as permitted by applicable law or an express written licence, unauthorized copying, redistribution, modification, reverse engineering, or commercial use of this software is prohibited.

## Weakness Scan Scope

The Offline Version currently represents the more complete weakness-scan workbench. It includes local weakness candidate review, single-point attack/rebuttal use, and tactic-package style preparation.

The local function scan is deliberately an issue-finding layer rather than a semantic adjudication layer. Without sending the matter to a large model, it checks the local case skeleton across the selected 18 dimensions and identifies possible proof, rule, causation, procedure, and evidence gaps. The same local issue can therefore appear in both side panels where it may be relevant to either position. This does not mean the software has decided that both parties made the same argument or bear the same responsibility. The lawyer or user reviews the full card and assigns the useful issue to the appropriate argument panel. More case-specific party attribution belongs to a separately authorized model-assisted workflow.

The Online Version currently includes weakness analysis inside the model-assisted workflow, including judge-side weakness extraction after the opposition run and blind positive/negative-side testing. However, the Online Version should still be expanded if the product route requires full feature parity with the Offline weakness workbench.

The intended competition direction is:

- Online keeps the multi-API opposition workflow.
- Gemini can perform first-pass intake and issue/argument separation.
- Verified model providers can perform multi-angle weakness scanning across the selected attack dimensions.
- Weakness scan results can be fed back into the positive-side and negative-side argument panels as reference points for lawyers.
- Offline retains confidential local use for sensitive matters.

## Privacy-Preserving Simulated-Case Weakness Discovery

The Offline Version includes a privacy-preserving simulated-case weakness discovery workflow through the **Synthetic Analogue** control.

The Offline Version deliberately keeps two separate weakness controls rather than combining them. **Scan Weaknesses** is the highest-confidentiality route: local functions review the real matter directly and no case material or weakness operation is sent to a model. **Synthetic Case Scan** is the fictionalized route: local functions first create similar fictional matters, and the user may separately authorize a verified model to scan only that fictional pack. The resulting cards describe the fictional matters directly and are not mapped back to the real matter. This separation lets each customer choose a route according to the sensitivity of the matter and the level of external-model assistance they are prepared to authorize.

The software keeps the real case on the local machine and first extracts a structural case skeleton. This skeleton can include issues, evidence objects, timeline points, causation links, legal elements, and adversarial dimensions, while avoiding direct disclosure of the client's real facts.

For highly confidential matters, this decomposition step is intentionally local-only. The system does not ask Gemini, DeepSeek, or any other external large model to read the original matter merely to create the skeleton. Local functions perform the initial split into issue frames, side positions, timeline markers, evidence-object categories, legal-element slots, causation links, and selected attack dimensions. This keeps the original case text and the skeleton on the user's machine.

The competition edition then generates 20 similar fictional matters locally from that skeleton by default. This batch size preserves cross-case pattern coverage while reducing oversized or malformed model responses. This Synthetic Analogue step does not call Gemini, DeepSeek, private endpoints, Cloud Run, Vertex AI, or any other external model. It is a local-function privacy workflow, not a cloud-generation workflow. The feature is intentionally not a self-growth or reusable training module; it creates a case-specific synthetic analogue pack for the current lawyer review session.

The fictional analogue output is not treated as a decision on the real case. It is a privacy-reduced working object. Once the synthetic analogue pack has been created locally, the user can authorize a verified model provider to scan that fictional pack for stronger weakness discovery. In that model-assisted step, Gemini, DeepSeek, or another verified provider receives the synthetic analogue only, not the original client matter or the local skeleton.

The fictional-case directory contains 20 generated matters by default. For each model scan, the user selects between 1 and 5 fictional matters. The user can also delete matters or add a manually written fictional matter. A visible progress indicator remains active during model review.

Selected fictional matters are reviewed sequentially. Within each matter, every enabled dimension independently rereads the complete fictional matter and writes a natural free-form internal analysis. A short second pass reads only that completed analysis to extract the affected side, a concise outside-card title, and a one-sentence preview. The extraction pass does not rewrite the analysis: opening a card displays the original free-form dimension report.

Within each fictional-matter call, every enabled attack dimension independently reviews both fictional sides through separate result slots. Each dimension may return zero or one supported weakness for each side. The workflow does not impose a fixed two-to-six-card total: with 18 enabled dimensions, a fictional side may receive up to 18 distinct cards when the fictional facts support them. Local deduplication merges only genuinely identical findings from the same dimension.

The fictional-pack model response is therefore not forced into a plain-language card package, checklist, or fixed series of headings. The model is free to follow the dimension's reasoning in connected professional prose. Only the outside title and short preview are extracted afterward. Local functions do not replace the free report with a generic explanation and do not map it to the real matter. Each card remains identified as a fictional-case finding and names the fictional source case and review dimension that produced it.

In short: local functions create and manage the fictional case pack. After user authorization, the model directly analyses only the selected 1 to 5 fictional matters. The output remains a fictional-case weakness report for lawyer reference; the real case is neither transmitted nor automatically altered.

### Synthetic Case Directory Controls and Demo Explanation

The Synthetic Analogue Case Directory uses one gold weakness-investigation control so that the user does not have to choose between overlapping single-case and multi-case routes.

**18D Weakness Scan for Selected Cases (Max 5)** supports multiple selection: on Windows, hold **Ctrl** while clicking separate matters, or hold **Shift** to select a continuous range. A normal click selects one matter and clears the earlier selection. Between one and five fictional matters may be queued in one scan, and every selected matter is always reviewed through all 18 dimensions.

The selected matters are not combined into one oversized model request. The software processes them sequentially by matter and dimension. Each enabled dimension uses one free-form analysis call and one short title-extraction call. With all 18 dimensions enabled, this is approximately 36 provider calls per fictional matter; five selected matters may therefore require approximately 180 calls. The confirmation dialog states the estimated call count before work starts. The five-matter ceiling limits the duration, provider cost, rate-limit exposure, and size of one user-controlled batch. It also isolates a failed dimension response instead of destroying every completed report. Completed titles are locally deduplicated only when they are genuinely repeated within the same dimension.

Every dimension independently rereads the complete fictional matter and writes a free-form weakness report. A short second pass extracts only the outside card title and affected-side label; it does not create a rebuttal, rewrite the report, or start an attack-and-defence round. Only the selected fictional matters are transmitted to the verified provider. The original real matter and the locally retained skeleton are not included.

Suggested narration for a recorded demonstration: "The gold button lets us select up to five fictional analogues. Every selected analogue is independently reviewed by all 18 dimensions. Each dimension writes freely, and a short second pass extracts only the title shown on the outside card. It is a weakness investigation, not an attack-and-defence round, and the original client matter remains local."

This design is important for legal use because the real matter and skeleton remain local during the confidentiality-critical stage. The model is used only after the matter has been fictionalized, so the system can use model-level legal reasoning without sending the original case file.

For customers, this is a deliberate offline safety measure. The simulated-case function is not a shortcut for sending original case material to a model; it is the opposite. It gives the user a way to create a fictional analogue locally, then optionally use model-level weakness scanning on that fictional analogue through a separate authorization prompt and verified provider route.

## Migration Notes

Can migrate later:

- lawyer-assistance positioning;
- adversarial positive/negative-side output;
- weakness scan explanation;
- argument-expression reference for lawyers;
- ordinary-user legal-reference positioning;
- legal aid / intake efficiency use case.

Do not migrate without review:

- old web portal as the main product route;
- self-growth or training-system language;
- internal patent-sensitive mechanisms;
- any wording that implies the software gives final legal advice;
- embedded real API keys or provider secrets.

## Next Fill-In Items

- Product name and one-sentence positioning.
- Competition-oriented short description.
- Demo workflow.
- Safety and legal-use disclaimer.
- Gemini integration description.
- Multi-API architecture description.
- Weakness scan and argument-expression reference description.
