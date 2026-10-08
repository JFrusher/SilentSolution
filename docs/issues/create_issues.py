"""Create the labels, milestones, issues and Project board for these drafts on GitHub, using the gh CLI.

    gh auth login                 # once
    gh auth refresh -s project    # once, for the Project board
    uv run docs/issues/create_issues.py

Safe to re-run: labels are upserted, existing milestones and issues (matched by title) are reused, and only
issues still carrying cross-reference placeholders are edited. Drafts with `fixed_in: <commit>` are created and
then closed as completed with a comment naming the commit."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = "JFrusher/SilentSolution"
OWNER = REPO.split("/")[0]
PROJECT_TITLE = "Silent Solution Roadmap"
HERE = os.path.dirname(os.path.abspath(__file__))

LABELS = {  # name: (colour, description)
    "bug": ("d73a4a", "Something isn't working"),
    "enhancement": ("a2eeef", "Improvement to something that exists"),
    "feature": ("0e8a16", "New capability"),
    "tech-debt": ("fbca04", "Code health; no player-visible change"),
    "chore": ("c5def5", "Repository housekeeping"),
    "good first issue": ("7057ff", "Small, well-scoped, a good way in"),
    "priority:high": ("b60205", "Do soon"),
    "priority:medium": ("d93f0b", "Normal priority"),
    "priority:low": ("fef2c0", "When convenient"),
    "area:ai": ("5319e7", "Ship, escort and submarine behaviour; wave director"),
    "area:sim": ("1d76db", "World model: vessels, ocean, physics"),
    "area:sensors": ("0052cc", "Sonar, periscope, radar"),
    "area:fire-control": ("006b75", "TDC, TMA, torpedoes"),
    "area:damage": ("e99695", "Damage control"),
    "area:ui": ("bfdadc", "Workstation, CRT pages, input"),
    "area:audio": ("c2e0c6", "Procedural sound"),
    "area:settings": ("d4c5f9", "Settings page and persistence"),
    "area:campaign": ("f9d0c4", "Campaign, career, debrief, scores"),
    "area:tutorial": ("fad8c7", "Training patrol"),
    "area:content": ("bfd4f2", "Scenarios, missions, campaigns"),
    "area:repo": ("ededed", "CI, licence, tooling"),
}
MILESTONES = {
    "v0.2.1 Fixes": "Bugs found in the v0.2.0 scan, plus licence, CI and lint.",
    "v0.3 Polish & UX": "Pause menu, objectives, save/load, after-action replay, quality of life.",
    "v0.4 Deeper Realism": "Acoustics, sensors, weapons and the physical world.",
    "v0.5 More Content": "Scenarios, missions, campaigns, neutrals.",
}
REF = re.compile(r"\[\[(\d\d)\]\]")
PENDING = "⟦draft {}⟧"  # left in a body until the referenced issue exists; pass 2 replaces it


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        sys.exit(f"gh {' '.join(args[:3])} failed:\n{r.stderr.strip()}")
    return r


def drafts():
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "[0-9][0-9]-*.md"))):
        text = open(path, encoding="utf-8", newline="").read().replace(chr(13) + chr(10), chr(10))
        _, head, body = text.split("---\n", 2)
        meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
        title = meta["title"]
        if title.startswith("'") and title.endswith("'"):
            title = title[1:-1].replace("''", "'")
        out.append(dict(key=os.path.basename(path)[:2], title=title, body=body.strip() + "\n",
                        labels=[s.strip() for s in meta["labels"].split(",")], milestone=meta["milestone"],
                        fixed_in=meta.get("fixed_in")))
    return out


def render(body, numbers):
    return REF.sub(lambda m: f"#{numbers[m.group(1)]}" if m.group(1) in numbers else PENDING.format(m.group(1)), body)


def body_file(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


def main():
    if not shutil.which("gh"):
        sys.exit("gh is not installed: winget install --id GitHub.cli -e  (then reopen the terminal)")
    status = gh("auth", "status", check=False)
    if status.returncode:
        sys.exit("gh is not logged in: run  gh auth login")
    want_project = "project" in (status.stdout + status.stderr)
    if not want_project:
        print("note: token lacks the 'project' scope; skipping the board. Run  gh auth refresh -s project  and re-run.")

    items = drafts()
    print(f"{len(items)} drafts -> {REPO}")

    for name, (colour, desc) in LABELS.items():
        gh("label", "create", name, "--repo", REPO, "--color", colour, "--description", desc, "--force")
    print(f"labels: {len(LABELS)} upserted")

    have = {m["title"] for m in json.loads(gh("api", f"repos/{REPO}/milestones?state=all&per_page=100").stdout)}
    for title, desc in MILESTONES.items():
        if title not in have:
            gh("api", f"repos/{REPO}/milestones", "-X", "POST", "-f", f"title={title}", "-f", f"description={desc}")
    print(f"milestones: {len(set(MILESTONES) - have)} created, {len(set(MILESTONES) & have)} existing")

    existing = {i["title"]: i for i in json.loads(gh("issue", "list", "--repo", REPO, "--state", "all", "--limit",
                                                     "1000", "--json", "number,title,url,state").stdout)}
    numbers, urls = {}, {}
    for d in items:
        if d["title"] in existing:
            numbers[d["key"]], urls[d["key"]] = existing[d["title"]]["number"], existing[d["title"]]["url"]
    created = 0
    for d in items:  # pass 1: create; references to issues not made yet stay as placeholders
        if d["key"] in numbers:
            continue
        path = body_file(render(d["body"], numbers))
        args = ["issue", "create", "--repo", REPO, "--title", d["title"], "--body-file", path,
                "--milestone", d["milestone"]]
        for label in d["labels"]:
            args += ["--label", label]
        url = gh(*args).stdout.strip().splitlines()[-1]
        os.unlink(path)
        numbers[d["key"]], urls[d["key"]] = int(url.rstrip("/").split("/")[-1]), url
        created += 1
        print(f"  #{numbers[d['key']]:<4} {d['title']}")
    print(f"issues: {created} created, {len(items) - created} already existed")

    fixed = 0
    for d in items:  # pass 2: fill placeholders now every issue has a number (never touches finished bodies)
        if not REF.search(d["body"]):
            continue
        current = json.loads(gh("issue", "view", str(numbers[d["key"]]), "--repo", REPO, "--json", "body").stdout)
        if "⟦draft" not in current["body"]:
            continue
        path = body_file(render(d["body"], numbers))
        gh("issue", "edit", str(numbers[d["key"]]), "--repo", REPO, "--body-file", path)
        os.unlink(path)
        fixed += 1
    print(f"cross-references: {fixed} issues linked")

    closed = 0
    for d in items:  # drafts already fixed: create-then-close, so the record lives on GitHub
        state = existing.get(d["title"], {}).get("state", "OPEN")
        if d["fixed_in"] and state == "OPEN":
            gh("issue", "close", str(numbers[d["key"]]), "--repo", REPO, "--reason", "completed",
               "--comment", f"Fixed in {d['fixed_in']}.")
            closed += 1
    print(f"closed as fixed: {closed}")

    if want_project:
        boards = json.loads(gh("project", "list", "--owner", OWNER, "--format", "json").stdout)["projects"]
        board = next((b for b in boards if b["title"] == PROJECT_TITLE), None)
        if board is None:
            board = json.loads(gh("project", "create", "--owner", OWNER, "--title", PROJECT_TITLE,
                                  "--format", "json").stdout)
        num = str(board["number"])
        gh("project", "link", num, "--owner", OWNER, "--repo", REPO.split("/")[1], check=False)
        for d in items:
            gh("project", "item-add", num, "--owner", OWNER, "--url", urls[d["key"]])
        print(f"project: '{PROJECT_TITLE}' (#{num}) holds all {len(items)} issues -> {board.get('url', '')}")


if __name__ == "__main__":
    main()
