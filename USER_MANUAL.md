# Litigation Expert AI System User Manual

This manual explains what each major field is asking for, how to classify the information, and what data format to enter. The application is a legal operations and drafting support tool. It does not replace attorney review, court rules, or verification against official records.

## General Rules

| Input type | Use this format | Example |
| --- | --- | --- |
| Short text | Plain words or short phrase | `Sacramento Superior Court` |
| Long text | Complete factual notes, summaries, or analysis | `Officer cited driver after alleged contest...` |
| Date | Prefer `YYYY-MM-DD` | `2026-05-14` |
| Numeric ID | Digits only, copied from the app list | `3` |
| Plain list | One item per line, or comma-separated for short fields | `Offer` / `Acceptance` / `Damages` |
| URL | Full web address | `https://www.courtlistener.com/...` |
| File path | Local path on your computer | `/home/josh/Documents/export.md` |

Privacy rule: do not enter API keys, passwords, private tokens, or unrelated personal information into case narrative fields. Case-folder AI extraction reads `OPENAI_API_KEY` only from `.env` or the system environment.

## Clean Install

Double-click `START_INSTALLER.pyw` in the project root for the graphical installer. It explains the main features, requires OpenAI API key setup before startup, installs the app, initializes the database, and offers to create a Desktop shortcut. Use `INSTALL.md` for fallback Windows 11, Linux, and macOS command-line installers.

## Top Bar

| Field / control | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Active Case | Case selector | Dropdown | Select the case record currently being edited or reviewed. Many pages require this before saving. |
| Refresh Case Data | Data refresh action | Button | Reloads case lists and view contents from the database. Use after saving or importing data. |

## Case Intake

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Title | Case identifier | Short text | Use a clear matter name, not a full factual narrative. |
| Description | Case summary | Long text | High-level description of the dispute, parties, and procedural posture. |
| Procedure track | Workflow / procedure classification | Dropdown | Select the procedural path that best describes how the matter should be handled. |
| Track purpose | Reference text | Read-only | Explains what the selected procedure track is for. |
| Court name | Tribunal / venue | Short text | Enter the court name if known, such as `Sacramento County Superior Court` or `Eastern District of California`. |
| Jurisdiction | Legal forum classification | Dropdown | Select the likely court/rule system. If uncertain, use `Mixed / unclear`. |
| Judge | Judicial officer | Short text | Enter judge name if assigned. Leave blank if unknown. |
| Department | Court department / courtroom | Short text | Enter department, division, or courtroom if known. |
| Filing status | Procedural status | Short text | Examples: `pre-filing`, `filed`, `served`, `discovery`, `post-judgment`. |

## File Submission

Use this page to add a local file to the active case and route it to the topic handler that should process it. The app detects a suggested route from the file name and readable text preview, but you can override the destination before submitting. Data extraction is available only for readable text-style files: TXT, Markdown, CSV, JSON, XML, HTML, HTM, and RTF.

| Field / control | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| File | Source document path | File path text | Choose the local file to submit. The app stores a reference to the path; it does not move the original file. |
| Browse | File picker action | Button | Opens a file picker and then analyzes the selected file. |
| Title | Submission label | Short text | Clear name for the file as it should appear in the selected handler. |
| Submission notes | Routing and source context | Long text | Optional explanation, such as why the document matters, source, deadlines, or review instructions. |
| Detected topic | Routing suggestion | Read-only text | Shows the suggested handler, confidence, and keyword reasons. |
| Route to | Topic handler destination | Dropdown | Override the destination if the detected topic is wrong. Options include Evidence, Authority Validation, Legal Research, Action Items, Facts, and Draft Generator. |
| Data extraction | Structured detail extraction | Checkbox | Enable this only for compatible text-style files. It reads labeled fields such as `Title:`, `Date:`, `Citation:`, `Fact:`, `Query:`, `Action:`, `Due date:`, `Document type:`, and `Content:` into the routed handler. |
| Compatible types | Extraction guidance | Read-only text | Recommends compatible extraction file types. PDFs, images, audio, video, and Word files can still be routed and stored, but text extraction is not attempted. |
| Preview | Text preview | Long text | Auto-filled only for readable text files. You may edit it before submission. |
| Analyze File | Routing action | Button | Reads the file name and text preview, then suggests a handler. |
| Submit to Handler | Save action | Button | Creates the corresponding record in the selected handler for the active case, then opens the routed handler and surfaces the new record. |
| Open Routed Handler | Navigation action | Button | Opens the destination page after a successful submission. |

## Case Folder Intake

When a case is saved, the app creates a case directory with section folders that mirror the major review pages. You can copy or paste files into the matching folder in File Explorer/Finder. On startup, and when you click a scan button, the app indexes new files without deleting or moving originals.

Typical folder path:

```text
cases/<case_id>_<safe_case_title>/
```

If you use a custom database path, the folder root is created next to that database unless `LEGAL_AGENT_CASES_DIR` is set.

| Field / control | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Case folder | Case file location | Read-only file path | Shows the folder where section-drop files should be placed. |
| Scan Active Case Folder | Intake action | Button | Scans the active case folder for new files, hashes them, records metadata, and runs AI extraction when available. |
| Scan All Case Folders | Startup/intake action | Button | Re-runs the same scan across all known case folders. |
| Manual Case Data | User-entered records | Read-only text | Shows manually saved parties, facts, claims, evidence, and action items. AI extraction does not overwrite these records. |
| AI extraction list | AI-derived records | List | Shows source file name, source section folder, extraction status, confidence score, and whether review is needed. |
| AI extraction detail | AI-derived structured data | Read-only text | Shows summary, key facts, parties, dates, evidence references, claims/defenses, jurisdiction clues, procedural issues, authorities, action items, warnings, and destination recommendations. |

Folder placement is treated as the primary intent signal. For example, a file placed in `05_evidence` is attached to the Evidence section first even if it also mentions parties, dates, or claims. If AI suggests a better folder, the app logs that recommendation and leaves the original file in place.

If `OPENAI_API_KEY` is missing, the app still creates folders, scans files, calculates SHA256 hashes, records manifest metadata, and marks compatible files as `pending_extraction`.

### Procedure Track Choices

| Procedure track | Use when | Calls for this information |
| --- | --- | --- |
| California Superior Court - state civil procedure track | The matter is in California state trial court. | State civil procedure, California Rules of Court, venue, filing status. |
| Federal Eastern District of California - federal civil procedure track | The matter is in federal court in E.D. California. | FRCP, E.D. Cal. local rules, federal jurisdiction, federal venue. |
| Local law enforcement / local government civil dispute - civil rights and government-claim review | The matter involves local agencies, police, public officials, municipal liability, immunity, exhaustion, or government-claim notice issues. | Agency identity, claim notice facts, civil-rights theory, immunity/exhaustion details. |
| Mixed / unclear - determine court, venue, and procedure before filing | The correct forum or procedural track is not yet clear. | More court, party, venue, claim, and filing facts before drafting. |

## Parties

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Name | Party identity | Short text | Person, business, agency, or entity name. |
| Role | Litigation role | Short text | Examples: `plaintiff`, `defendant`, `petitioner`, `respondent`, `witness`, `agency`. |
| Type | Party category | Short text | Examples: `individual`, `corporation`, `LLC`, `public entity`, `officer`, `department`. |
| Notes | Party-specific facts | Long text | Capacity, relationship to dispute, service details, or role-specific concerns. |

## Facts

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Date | Event date | Date text | Prefer `YYYY-MM-DD`. Use approximate text only if the exact date is unknown. |
| Fact text | Material fact | Long text | One concrete factual assertion or event. Avoid mixing legal argument into fact entries. |
| Linked evidence | Evidence reference | Dropdown | Select evidence that supports the fact, if already entered. |
| Relevance | Legal or practical significance | Short text | Explain why the fact matters, such as `element: damages`, `impeachment`, `notice`, or `deadline`. |

## Claims / Defenses

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Claim name | Cause of action or defense | Short text | Examples: `Breach of Contract`, `Section 1983 violation`, `Affirmative defense - statute of limitations`. |
| Claim type | Claim classification | Short text | Examples: `cause of action`, `affirmative defense`, `counterclaim`, `procedural objection`. |
| Jurisdiction basis | Legal basis / authority | Short text | Statute, constitutional provision, contract basis, or rule source. |
| Required elements | Element checklist source | Plain list | Enter one element per line, such as `Duty`, `Breach`, `Causation`, and `Damages`. |
| Status | Workflow status | Short text | Examples: `draft`, `needs evidence`, `ready for review`, `dismissal risk`. |
| Notes | Claim analysis | Long text | Element concerns, missing facts, pleading risks, or strategy notes. |

## Evidence

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Title | Evidence label | Short text | Name the item clearly, such as `Citation`, `Bodycam transcript`, `Contract`, `Email from May 14`. |
| Evidence type | Evidence category | Short text | Examples: `document`, `photo`, `video`, `testimony`, `record`, `notice`, `citation`. |
| Description | Evidence summary | Long text | What the item shows, proves, or contradicts. |
| File path | Local file reference | File path text | Local path to the source file if stored on your computer. |
| Date obtained | Acquisition date | Date text | Prefer `YYYY-MM-DD`. |
| Supported claims | Claim linkage | Plain list | Enter one supported claim or defense per line, such as `Breach of Contract`. |
| Admissibility notes | Evidence rule concerns | Long text | Authentication, hearsay, foundation, relevance, privilege, chain of custody. |
| Weakness notes | Reliability or use limits | Long text | Missing foundation, contradictory evidence, unclear source, incomplete copy, credibility issues. |

## Action Items & Due Dates

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Action text | Task description | Long text | Specific task to complete, such as `Request certified docket` or `Draft opposition outline`. |
| Category | Task category | Short text | Examples: `filing`, `service`, `discovery`, `research`, `evidence`, `deadline`. |
| Due date | Deadline | Date text | Prefer `YYYY-MM-DD`. Leave blank if unknown, then use due-date review. |
| Dependency | Blocking condition | Short text | What must happen first, such as `need police report` or `await court notice`. |
| Status | Task progress | Dropdown | `open`, `in progress`, or `complete`. |
| Notes | Task details | Long text | Instructions, status details, or source of deadline. |

## Legal Research

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Query | Research question | Short text | The legal issue or search question. |
| Source | Research source | Short text | Examples: `CourtListener`, `official court site`, `statute`, `secondary source`. |
| Result summary | Research result | Long text | Summarize the answer or useful authority without pasting unnecessary full text. |
| Authority IDs | Link to stored authorities | Plain ID list | IDs from the Authority Validation list, separated by commas or spaces, such as `1, 2`. |

## CourtListener Research

Use this page for public legal research and citation checks. The structured fields build a CourtListener query. Keep legal issue text separate from location and court filters.

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Legal issue / citation text | Research issue or citation text | Long text | For Search: plain issue text. For Citation Lookup: formal citation text. |
| Location preset | Location / court filter preset | Dropdown | Select a known location group, such as Sacramento/E.D. California. |
| Location terms | Geographic relevance terms | Short text | City, county, state, or regional terms, such as `Sacramento California`. |
| Court IDs | CourtListener court identifiers | Comma-separated short text | Use CourtListener IDs like `caed`, `ca9`, `cal`, `calctapp3d`. Do not enter statutes here. |
| Statute / code section | Legal code reference | Short text | Statute or code, such as `Cal. Veh. Code 23109(a)`. |
| Required terms | Must-include search terms | Comma-separated text | Terms the search should emphasize, such as `driver rights, evidence`. |
| Exclude terms | Terms to avoid | Comma-separated text | Terms to subtract from the search, such as `DUI`. |
| Filed after | Date filter lower bound | Date text | `YYYY-MM-DD`. |
| Filed before | Date filter upper bound | Date text | `YYYY-MM-DD`. |
| Precedential status | Opinion publication/status filter | Dropdown | Select published, unpublished, errata, separate opinion, etc. |
| CourtListener data type | CourtListener record type | Dropdown | Usually `Case law opinions`; other options include docket metadata, filing documents, judges, oral arguments. |
| Search mode | Search behavior | Dropdown | Use Keyword/Boolean for strict court/date/status filters. Use Semantic for broad natural-language discovery without strict filters. |
| Query preview | Built API query | Read-only | Shows what the app will send as a search query. |

### CourtListener Buttons

| Button | Use when |
| --- | --- |
| Search CourtListener | You have a legal issue, statute, topic, or natural-language query. |
| Citation Lookup | You have formal citations to validate, such as `576 U.S. 644`. It is not for broad questions. |
| Find Similar Cases | You want public cases similar to the query. |
| Validate Determined Case | You want to check whether a presented citation/title has public metadata suggesting an indexed public record. |
| Save to Matter Notes | Save the selected CourtListener result into the case research log. |

## Authority Validation

Authority Validation stores case law, statutes, rules, and other legal authorities. Only mark an authority verified after you have checked it against a reliable source.

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Authority type | Authority category | Short text | Examples: `case`, `statute`, `rule`, `regulation`, `secondary source`. |
| Title | Authority name | Short text | Case name, statute title, rule title, or source title. |
| Citation | Citation string | Short text | Formal legal citation if available. |
| Jurisdiction | Legal jurisdiction | Short text | Examples: `California`, `Ninth Circuit`, `Federal`, `Sacramento County`. |
| Court | Issuing court | Short text | Examples: `California Supreme Court`, `E.D. Cal.`, `Ninth Circuit`. |
| Year | Publication / decision year | Number | Four-digit year if known. |
| Source URL | Source link | URL | Prefer official or reliable public source. |
| Excerpt | Supporting passage | Long text | Short excerpt that proves relevance. Do not paste full copyrighted materials unnecessarily. |
| Treatment status | Citation treatment | Dropdown | Use `controlling`, `persuasive`, `distinguished`, `criticized`, `overruled`, etc. |
| Notes | Verification notes | Long text | Why it matters, how it was verified, limits, treatment concerns. |

## Citation Treatment Checker

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Authority ID | Stored authority reference | Numeric ID | Enter the authority ID from Authority Validation. |
| Treatment status | Legal treatment classification | Dropdown | Select current treatment: `unknown`, `controlling`, `persuasive`, `distinguished`, `criticized`, `overruled`, `partially overruled`, `superseded`, or `vacated`. |
| Notes | Treatment explanation | Long text | Explain the source and reason for the treatment status. |

## Claim Element Checklist

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Claim selector | Stored claim reference | Dropdown | Select a claim/defense to compare required elements against stored evidence. |

## Evidence Sufficiency Review

This view is read-only. It compares claims, required elements, and evidence entries. Improve the output by adding clean claim elements and linking evidence to claims.

## Document Strategy

This view is read-only. It summarizes case records into document strategy. Improve the output by completing Case Intake, Claims, Evidence, Authorities, and Action Items.

## Draft Generator

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Document type | Draft category | Short text | Examples: `complaint`, `answer`, `opposition`, `declaration`, `motion outline`, `filing checklist`. |

## AI Argument Analysis

| Control | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Generate AI Analysis | AI analysis action | Button | Uses the stored case profile and verified authorities. Do not rely on it without legal review. |
| Refresh Case Profile | Data refresh action | Button | Reloads the case profile used for analysis. |
| Case profile list | Stored profile items | Read-only list | Shows facts, claims, evidence, authorities, and documents available for analysis. |

## Vulnerability / Demurrer-Proofing Review

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Document ID | Stored document reference | Numeric ID | Optional. Enter a draft document ID if reviewing a specific draft. Leave blank for general case vulnerability review. |

## Filing Readiness Checklist

This view is read-only. It checks whether the case has enough structured information for filing preparation. Missing fields should be fixed in Case Intake, Claims, Evidence, Authority Validation, and Action Items.

## Export Center

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| Export format | Output type | Dropdown | Choose `markdown` for readable review or `json` for structured data transfer. |
| Output path | File destination | File path text | Optional. If blank, output displays in the app. If filled, export saves to that file. |

## Settings

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| OpenAI API key | Secret credential | Password text | Store only your OpenAI API key. Do not place case facts here. |
| Model selection | AI model setting | Dropdown | Select model used by AI features. |
| Temperature | AI randomness control | Decimal number | Use `0.0` for conservative deterministic output. Higher values are less predictable. |
| Citation strictness | Citation verification behavior | Dropdown | `High` is safest for legal drafting. |
| Verification strictness | Authority/fact checking behavior | Dropdown | `High` is safest when preparing filing material. |
| Database location | Database path reference | File path text | Currently informational in the settings view. The app usually uses the configured startup database path. |
| Export folder | Default export destination | Folder path text | Folder where exports should be saved by default. |

## Audit Log / Verification History

| Field | Information classification | Data type | Correct use |
| --- | --- | --- | --- |
| New audit event | Manual verification event | Short text | Record concise workflow events, such as `Verified citation against official opinion` or `Updated evidence source`. |

## Data Quality Checklist

Before generating drafts, exports, or AI analysis, confirm:

1. Case Intake has a title, procedure track, jurisdiction, court, and filing status.
2. Parties identify each person/entity and role.
3. Facts are separated into specific factual assertions.
4. Claims list required elements as plain text, one element per line.
5. Evidence entries explain what each item proves and which claims it supports.
6. Authorities include citation, jurisdiction, court, year, source URL, excerpt, and treatment status.
7. Important authorities are marked verified only after manual verification.
8. CourtListener research uses court IDs only in the Court IDs field, not statute numbers.
9. Action items include due dates or notes explaining why a due date is unknown.
10. Exports and drafts are reviewed before use.
