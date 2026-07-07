import sys, collections, re

rows = []
for l in sys.stdin:
    l = l.rstrip("\n")
    if not l.strip():
        continue
    parts = l.split("\t", 2)
    if len(parts) < 3:
        continue
    num, ms, title = parts
    m = re.match(r"\[(T-\d+)\]", title)
    tid = m.group(1) if m else title
    rows.append((int(num), ms, tid, title))

by_tid = collections.defaultdict(list)
for num, ms, tid, title in rows:
    by_tid[tid].append((num, ms))

close_list = []
for tid, items in by_tid.items():
    if len(items) > 1:
        items.sort()
        with_ms = [i for i in items if i[1] not in ("null", "none", "")]
        keep = with_ms[-1] if with_ms else items[-1]
        for num, ms in items:
            if num != keep[0]:
                close_list.append(num)

print("total_issues", len(rows))
print("unique_tasks", len(by_tid))
print("CLOSE:" + ",".join(str(n) for n in sorted(close_list)))
print("close_count", len(close_list))
