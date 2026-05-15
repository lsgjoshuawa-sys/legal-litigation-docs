from __future__ import annotations

TRACK_STATE_CIVIL = "California Superior Court - state civil procedure track"
TRACK_FEDERAL_EDCA = "Federal Eastern District of California - federal civil procedure track"
TRACK_LOCAL_GOVERNMENT = "Local law enforcement / local government civil dispute - civil rights and government-claim review"
TRACK_MIXED_UNCLEAR = "Mixed / unclear - determine court, venue, and procedure before filing"

LEGAL_TRACK_CHOICES = [
    "",
    TRACK_STATE_CIVIL,
    TRACK_FEDERAL_EDCA,
    TRACK_LOCAL_GOVERNMENT,
    TRACK_MIXED_UNCLEAR,
]

TRACK_PURPOSES = {
    TRACK_STATE_CIVIL: "Use for California Superior Court matters governed primarily by California civil procedure and California Rules of Court.",
    TRACK_FEDERAL_EDCA: "Use for federal civil matters in the Eastern District of California governed by FRCP and local federal rules.",
    TRACK_LOCAL_GOVERNMENT: "Use for disputes involving local agencies, law enforcement, civil-rights theories, immunity, exhaustion, or government-claim notice issues.",
    TRACK_MIXED_UNCLEAR: "Use when the correct court or procedure path is not clear yet and the case needs classification before drafting or filing.",
}

LEGACY_TRACK_ALIASES = {
    "A": TRACK_STATE_CIVIL,
    "B": TRACK_FEDERAL_EDCA,
    "C": TRACK_LOCAL_GOVERNMENT,
    "California Superior Court": TRACK_STATE_CIVIL,
    "Federal Eastern District of California": TRACK_FEDERAL_EDCA,
    "Local law enforcement / local government civil dispute": TRACK_LOCAL_GOVERNMENT,
    "Mixed / unclear": TRACK_MIXED_UNCLEAR,
}

TRACK_TO_JURISDICTION = {
    TRACK_STATE_CIVIL: "California Superior Court",
    TRACK_FEDERAL_EDCA: "Federal Eastern District of California",
    TRACK_LOCAL_GOVERNMENT: "Local law enforcement / local government civil dispute",
    TRACK_MIXED_UNCLEAR: "unclear",
}


def normalize_legal_track(value: str | None) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return ""
    return LEGACY_TRACK_ALIASES.get(text, text)


def jurisdiction_for_track(value: str | None) -> str | None:
    track = normalize_legal_track(value)
    return TRACK_TO_JURISDICTION.get(track)


def purpose_for_track(value: str | None) -> str:
    track = normalize_legal_track(value)
    return TRACK_PURPOSES.get(track, "")


def is_local_government_track(value: str | None) -> bool:
    return normalize_legal_track(value) == TRACK_LOCAL_GOVERNMENT
