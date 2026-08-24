# Failed approaches

- Whisper-in-V1: rejected. Adds an audio pipeline and cannot run on Workers.
- Direct Python D1 access: rejected. One write path through the API worker.
- Vectorize in V1: deferred. FTS5 plus person/topic/type filters cover the
  first slice; empty results are "insufficient evidence".
