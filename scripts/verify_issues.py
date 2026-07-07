import json, subprocess, urllib.request, collections, re

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "JmLeeRoom/EdgeCanvas"
token = subprocess.run([GH, "auth", "token"], capture_output=True, text=True).stdout.strip()

issues = []
page = 1
while True:
    url = f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100&page={page}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "edgecanvas-script",
    })
    with urllib.request.urlopen(req) as r:
        batch = json.load(r)
    if not batch:
        break
    issues.extend(batch)
    page += 1
issues = [i for i in issues if "pull_request" not in i]

ms_count = collections.Counter((i["milestone"]["title"] if i.get("milestone") else "none") for i in issues)
label_count = collections.Counter()
for i in issues:
    for l in i["labels"]:
        label_count[l["name"]] += 1

print("total", len(issues))
print("milestones:", dict(ms_count))
print("phase labels:", {k: v for k, v in sorted(label_count.items()) if k.startswith("phase:")})
print("status labels:", {k: v for k, v in sorted(label_count.items()) if k.startswith("status:")})
print("assignee labels:", {k: v for k, v in sorted(label_count.items()) if k.startswith("assignee:")})

# every issue should have exactly phase/module/assignee/status (+ optional week)
missing = []
for i in issues:
    names = [l["name"] for l in i["labels"]]
    groups = {n.split(":")[0] for n in names}
    for g in ("phase", "module", "assignee", "status"):
        if g not in groups:
            missing.append((i["number"], i["title"], g))
print("missing_label_groups", len(missing))
for m in missing[:10]:
    print("  ", m)
