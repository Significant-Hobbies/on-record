UNVERIFIED_SPEAKER_SLUG = "speaker-unverified"


def attribution_status(speaker_raw: str) -> str:
    if speaker_raw == UNVERIFIED_SPEAKER_SLUG:
        return "speaker_unverified"
    return "verified_speaker"
