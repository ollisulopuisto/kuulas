# kuulas

kuulas is a multitrack editor for spoken word (podcasts, interviews, radio).
It is modelled on Hindenburg PRO: keyboard-first, with the transcript and the
audio as one thing. Its signal processing comes from the podcast repo's
`speechmix` and `nhsx` packages.

## Running the tests

kuulas needs the podcast repo checked out next to it, at `../podcast`, because
`speechmix` and `nhsx` are path dependencies.

```
uv sync
uv run pytest -q
uv run ruff check .
```

Audio decoding uses ffmpeg. Install it first (`brew install ffmpeg` on a Mac).

## Projects

A project is a `Name.kuulas` folder (format: `docs/FORMAT.md`). To see what
is in one:

```
uv run kuulas info Interview.kuulas
```

## Where to read next

- `ROADMAP.md`: what kuulas must do, what is done, and what is next.
- `docs/PLAN.md`: how it is built, in work packages, with the ground rules.
