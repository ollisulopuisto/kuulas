"""The narration script as text and Markdown (WP43).

Pure rendering of ``narration.script`` items; the labels are translated.
"""

from __future__ import annotations

from .messages import t


def _length(item: dict) -> str:
    key = ("narration_script.length_estimated" if item["estimated"]
           else "narration_script.length")
    return t(key, seconds=item["seconds"])


def to_text(items: list[dict]) -> str:
    if not items:
        return t("narration_script.empty") + "\n"
    blocks = []
    for n, i in enumerate(items, 1):
        lines = [f"{n}. {i['time']}  {_length(i)}  [{i['track_name']}]"]
        if i["before"]:
            lines.append(f"   {t('narration_script.before')}: …{i['before']}")
        lines.append(f"   {i['text']}")
        if i["after"]:
            lines.append(f"   {t('narration_script.after')}: {i['after']}…")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def to_markdown(items: list[dict]) -> str:
    out = [f"# {t('narration_script.title')}", ""]
    if not items:
        out.append(t("narration_script.empty"))
    for n, i in enumerate(items, 1):
        out.append(f"## {n}. {i['time']}")
        out.append(f"*{_length(i)} · {i['track_name']}*")
        out.append("")
        if i["before"]:
            out.append(f"> {t('narration_script.before')}: …{i['before']}")
            out.append("")
        out.append(i["text"])
        out.append("")
        if i["after"]:
            out.append(f"> {t('narration_script.after')}: {i['after']}…")
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
