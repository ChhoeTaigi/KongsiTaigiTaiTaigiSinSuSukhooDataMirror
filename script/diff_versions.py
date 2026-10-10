"""Compare two versions of KongsiTaigiTaiTaigiSinSuSukhooData.json.

Entries are matched by their site id. Writes VERSION_DIFF.md listing added,
removed and modified entries.
"""

import json
from pathlib import Path


def _entry_label(entry):
    readings = "/".join(r.get("KPL", "") for r in entry.get("音讀", []))
    label = f"{entry.get('id')} {entry.get('漢字', '')}"
    if readings:
        label += f" ({readings})"
    huagi = entry.get("對應華語", "")
    if huagi:
        label += f" → {huagi}"
    return label


def _fmt(val):
    if val is None or val == "" or val == []:
        return "(empty)"
    if isinstance(val, list):
        if val and isinstance(val[0], dict):
            if "KPL" in val[0]:
                s = "/".join(f"{r.get('KPL', '')} ({r.get('POJ', '')})" for r in val)
            else:
                s = json.dumps(val, ensure_ascii=False)
        else:
            s = ", ".join(str(v) for v in val)
    else:
        s = str(val)
    return s[:117] + "..." if len(s) > 120 else s


def diff_versions(old_json_path, new_json_path):
    with open(old_json_path, encoding="utf-8") as f:
        old_entries = json.load(f)
    with open(new_json_path, encoding="utf-8") as f:
        new_entries = json.load(f)

    old_map = {e["id"]: e for e in old_entries}
    new_map = {e["id"]: e for e in new_entries}
    old_keys, new_keys = set(old_map), set(new_map)

    added = [{"id": k, "label": _entry_label(new_map[k])} for k in sorted(new_keys - old_keys)]
    removed = [{"id": k, "label": _entry_label(old_map[k])} for k in sorted(old_keys - new_keys)]

    modified = []
    for k in sorted(old_keys & new_keys):
        old_e, new_e = old_map[k], new_map[k]
        if old_e == new_e:
            continue
        field_changes = []
        for field in sorted(set(old_e) | set(new_e)):
            ov, nv = old_e.get(field), new_e.get(field)
            if ov != nv:
                field_changes.append(f"  - `{field}`: {_fmt(ov)} → {_fmt(nv)}")
        modified.append({"id": k, "label": _entry_label(new_e), "field_changes": field_changes})

    return {
        "old_count": len(old_entries),
        "new_count": len(new_entries),
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def write_diff_md(diff, old_version, new_version, out_path):
    lines = [
        f"# Version Diff: {old_version} → {new_version}",
        "",
        f"- Previous: **{old_version}** ({diff['old_count']} entries)",
        f"- Current: **{new_version}** ({diff['new_count']} entries)",
        f"- Added: **{len(diff['added'])}** | Removed: **{len(diff['removed'])}** | Modified: **{len(diff['modified'])}**",
        "",
    ]
    for title, key in (("Added Entries", "added"), ("Removed Entries", "removed")):
        if diff[key]:
            lines += [f"## {title}", ""]
            lines += [f"- {e['label']}" for e in diff[key]]
            lines.append("")
    if diff["modified"]:
        lines += ["## Modified Entries", ""]
        for e in diff["modified"]:
            lines += [f"### {e['label']}", ""]
            lines += e["field_changes"]
            lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print("Usage: diff_versions.py OLD_JSON NEW_JSON OLD_VERSION NEW_VERSION")
        sys.exit(1)
    old_json, new_json, old_version, new_version = sys.argv[1:]
    out = Path(__file__).resolve().parent.parent / "VERSION_DIFF.md"
    write_diff_md(diff_versions(old_json, new_json), old_version, new_version, str(out))
