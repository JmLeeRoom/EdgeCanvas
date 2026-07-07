import json, subprocess, urllib.request, collections, re, sys

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

# exclude PRs
issues = [i for i in issues if "pull_request" not in i]

by_tid = collections.defaultdict(list)
for it in issues:
    title = it["title"]
    m = re.match(r"\[(T-\d+)\]", title)
    tid = m.group(1) if m else title
    ms = it["milestone"]["title"] if it.get("milestone") else None
    by_tid[tid].append((it["number"], ms))

close_list = []
for tid, items in by_tid.items():
    if len(items) > 1:
        items.sort()
        with_ms = [i for i in items if i[1]]
        keep = with_ms[-1] if with_ms else items[-1]
        for num, ms in items:
            if num != keep[0]:
                close_list.append(num)

print("total_issues", len(issues))
print("unique_tasks", len(by_tid))
print("CLOSE:" + ",".join(str(n) for n in sorted(close_list)))
print("close_count", len(close_list))

if "--delete" in sys.argv and close_list:
    for n in sorted(close_list):
        subprocess.run([GH, "issue", "delete", str(n), "--repo", REPO, "--yes"])
        print("deleted", n)
