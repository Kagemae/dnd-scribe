# dnd-scribe / dnd-session-wiki Interface Contract

**Version:** 1.0
**Owner:** dnd-scribe (producer)
**Consumer:** dnd-session-wiki

This document defines the data format used when dnd-scribe pushes a completed session transcript to the wiki.

## Endpoint

```
POST /api/sessions/ingest
Content-Type: application/json
Authorization: Bearer <api_key>  (optional)
```

## Payload

```json
{
  "interface_version": "1.0",
  "session": {
    "name": "Witchlight 2026-02-10",
    "date": "2026-02-20",
    "speakers": {
      "SPEAKER_00": "Thistle",
      "SPEAKER_01": "Mr Mistoffelees",
      "SPEAKER_02": "Wanderpaw",
      "SPEAKER_03": "DM"
    },
    "status": "completed",
    "created_at": "2026-02-20T22:22:27.598483"
  },
  "transcript": {
    "segments": [
      {
        "start": 0.284,
        "end": 2.707,
        "text": "I know it's there.",
        "speaker": "SPEAKER_03",
        "speaker_name": "DM"
      }
    ],
    "duration": 9517.753,
    "segment_count": 2672
  }
}
```

## Field Reference

### Top-level

| Field | Type | Description |
|-------|------|-------------|
| `interface_version` | string | Contract version (e.g. `"1.0"`). Reject unknown versions. |
| `session` | object | Session metadata. |
| `transcript` | object | Transcript data with segments. |

### `session`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable session name (e.g. "Witchlight 2026-02-10"). |
| `date` | string | Date the session was processed (YYYY-MM-DD). |
| `speakers` | object | Map of speaker IDs to human names (`SPEAKER_00` -> `"DM"`). |
| `status` | string | Always `"completed"` when pushed. |
| `created_at` | string | ISO 8601 timestamp of when the session was created. |

### `transcript`

| Field | Type | Description |
|-------|------|-------------|
| `segments` | array | Ordered array of speech segments. |
| `duration` | float | Total audio duration in seconds. |
| `segment_count` | int | Number of segments (convenience field). |

### `transcript.segments[]`

| Field | Type | Description |
|-------|------|-------------|
| `start` | float | Segment start time in seconds from audio start. |
| `end` | float | Segment end time in seconds from audio start. |
| `text` | string | Transcribed text for this segment. |
| `speaker` | string | Raw speaker ID from diarization (e.g. `"SPEAKER_03"`). |
| `speaker_name` | string | Human name assigned by the DM (e.g. `"DM"`). |

### What's NOT included

- **Word-level timing** (`words[]` arrays) — stripped to reduce payload size (~5MB -> ~1MB). Full data remains in the local `transcript.json`.
- **Recap** — the wiki generates its own recap after the DM reviews and cleans up the transcript.
- **Whisper confidence scores** (`avg_logprob`, `compression_ratio`, `no_speech_prob`) — not useful for the wiki.

## Recap Generation

The wiki is responsible for generating session recaps from the transcript. dnd-scribe originally used the following system prompt, which can serve as a starting point:

```
You are a D&D session scribe. Given a transcript of a tabletop RPG session,
create comprehensive session notes including:

- **Session Summary**: A brief overview of what happened
- **Key Events**: Major plot points, discoveries, and decisions
- **Combat Encounters**: Brief summaries of any battles
- **NPC Interactions**: Notable conversations and new NPCs met
- **Character Moments**: Memorable roleplaying or character development
- **Loot & Rewards**: Items found, gold earned, etc.
- **Cliffhangers & Hooks**: Unresolved plot threads for next session

Write in a narrative style that captures the adventure's tone.
Use the speaker names provided to attribute actions and dialogue.
```

The transcript should be formatted as `Speaker Name: text` lines (one per segment) before being sent to the LLM. The `speaker_name` field on each segment provides the human-readable name.

## Typical payload size

A 2.5-hour session with ~2,700 segments produces a payload of roughly 1-1.5 MB.

## Versioning

- The `interface_version` field is included in every push.
- dnd-scribe is the source of truth for the contract.
- When the format changes, bump the version here and in `wiki_push.py`.
- The wiki should validate the version and reject payloads with unknown versions.

## Changelog

### 1.0 (2026-02-21)
- Initial version.
- Session metadata + transcript segments (without word-level data).
- No recap included (wiki handles recap generation).
