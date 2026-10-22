"""TASKS.md を工程表（gantt.html）が読める形になっているか確かめ、今の状況をまとめて表示する。

使い方：python tools/check_tasks.py
問題があれば「エラー」を出して終了コード1で終わる。gantt.html の読み込み処理と同じ決まりで見ている。
"""
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATES = {"未着手", "作業中", "確認待ち", "完了", "保留"}
W1 = date(2026, 10, 19)  # W1 の月曜
JUN = {"上旬": (1, 10), "中旬": (11, 20), "下旬": (21, 0)}

errors, warnings = [], []


def cells(line):
    return [c.strip() for c in line.split("|")[1:-1]]


def year_of(m):
    return 2026 if m >= 4 else 2027


def last_day(y, m):
    return ((date(y, m % 12 + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(days=1)).day


def week_no(d):
    return (d - W1).days // 7 + 1


def parse_period(label):
    """gantt.html の parsePeriod と同じ。週の番号（開始, 終了）を返す。"""
    m = re.search(r"(\d+)月(上旬|中旬|下旬)(?:〜(上旬|中旬|下旬))?", label)
    if not m:
        return None
    mon = int(m.group(1))
    y = year_of(mon)
    s = JUN[m.group(2)][0]
    e = JUN[m.group(3) or m.group(2)][1] or last_day(y, mon)
    start, end = date(y, mon, s), date(y, mon, e)
    ex = re.search(r"[（(]\s*(?:(\d+)/(\d+))?\s*〜\s*(\d+)/(\d+)\s*[)）]", label)
    if ex:
        if ex.group(1):
            start = date(year_of(int(ex.group(1))), int(ex.group(1)), int(ex.group(2)))
        end = date(year_of(int(ex.group(3))), int(ex.group(3)), int(ex.group(4)))
    ws = week_no(start + timedelta(days=3))
    we = max(ws, week_no(end - timedelta(days=3)))
    return ws, we


def expand_ids(text):
    ids = []
    for a, b in re.findall(r"T-(\d+)(?:〜T-(\d+))?", text):
        ids.extend(range(int(a), int(b or a) + 1))
    return ids


def main():
    md = (ROOT / "TASKS.md").read_text(encoding="utf-8")
    sec, group = "", None
    tasks, phases, week, done = {}, [], [], []
    updated = None

    for n, line in enumerate(md.splitlines(), 1):
        h = re.match(r"^##\s+(.*)", line)
        if h:
            sec = h.group(1).strip()
            group = sec if re.match(r"^[A-Z]\.", sec) else None
            continue
        u = re.match(r"^最終更新：\s*(\S+)", line)
        if u:
            updated = u.group(1)
            continue
        if re.match(r"^\|\s*-", line):
            continue
        if sec.startswith("スケジュール") and line.startswith("|"):
            c = cells(line)
            if c[0] == "時期":
                if c[:4] != ["時期", "週", "ゴール", "主なタスク"]:
                    errors.append(f"{n}行目：スケジュールの列が「時期｜週｜ゴール｜主なタスク」になっていない")
                continue
            r = parse_period(c[0])
            if not r:
                errors.append(f"{n}行目：時期「{c[0]}」を工程表が読めない（例：11月上旬（11/1〜11/15））")
                continue
            phases.append({"label": c[0], "weeks": r, "ids": expand_ids(c[3] if len(c) > 3 else ""), "line": n})
        elif sec.startswith("今週"):
            w = re.match(r"^\d+\.\s+(.*)", line)
            if w:
                week.append(w.group(1))
        elif sec.startswith("完了") and line.startswith("|"):
            c = cells(line)
            if c[0] != "タスク":
                if len(c) != 3:
                    errors.append(f"{n}行目：「完了したもの」の列が3つ（タスク｜完了日｜成果物）になっていない")
                done.append(c[0])
        elif group and re.match(r"^\|\s*T-\d+", line):
            c = cells(line)
            if len(c) != 5:
                errors.append(f"{n}行目：列が5つ（ID｜タスク｜担当｜状態｜成果物・メモ）になっていない")
                continue
            if not re.fullmatch(r"T-\d+", c[0]):
                errors.append(f"{n}行目：番号「{c[0]}」が T-数字 の形でない")
                continue
            tid = int(c[0][2:])
            if tid in tasks:
                errors.append(f"{n}行目：{c[0]} が重複している")
            if c[3] not in STATES:
                errors.append(f"{n}行目：{c[0]} の状態「{c[3]}」が決まった言葉でない（{'/'.join(sorted(STATES))}）")
            if c[3] == "完了":
                warnings.append(f"{c[0]} は完了なので「完了したもの」に移す")
            tasks[tid] = {"label": c[0], "name": c[1], "who": c[2], "st": c[3], "group": group}

    if not updated:
        errors.append("「最終更新：」の行がない")
    if not phases:
        errors.append("「## スケジュール」の表が読めない")

    for p in phases:
        for i in p["ids"]:
            if i not in tasks:
                warnings.append(f"{p['line']}行目：スケジュールの T-{i:02d} が台帳の表にない（完了して移したなら外す）")
            else:
                ws, we = tasks[i].get("weeks", (99, 0))
                tasks[i]["weeks"] = (min(ws, p["weeks"][0]), max(we, p["weeks"][1]))

    # 公開リポジトリなので、メールアドレスらしきものがあれば止める
    for n, line in enumerate(md.splitlines(), 1):
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", line):
            errors.append(f"{n}行目：メールアドレスらしきものがある（公開されるので書かない）")

    today = date.today()
    now_w = week_no(today)
    late = [t for t in tasks.values() if "weeks" in t and t["weeks"][1] < now_w and t["st"] not in ("完了", "保留")]
    nodate = [t for t in tasks.values() if "weeks" not in t]
    this_w = [t for t in tasks.values() if "weeks" in t and t["weeks"][0] <= now_w <= t["weeks"][1] and t["st"] != "完了"]

    print(f"台帳の最終更新：{updated}　今日：{today}（W{now_w}）")
    counts = {s: sum(1 for t in tasks.values() if t["st"] == s) for s in ["未着手", "作業中", "確認待ち", "保留"]}
    print("残りの作業：" + "、".join(f"{k} {v}" for k, v in counts.items()) + f"（計 {len(tasks)}）／完了 {len(done)}")

    def show(title, ts):
        if ts:
            print(f"\n■ {title}")
            for t in sorted(ts, key=lambda t: int(t["label"][2:])):
                wk = f"W{t['weeks'][0]}〜W{t['weeks'][1]}" if "weeks" in t else "時期未定"
                print(f"  {t['label']} [{t['st']}] {wk} {t['who']}：{t['name'][:40]}")

    show("目安を過ぎている", late)
    show("今週が目安に入っている", this_w)
    show("確認待ち（永井さんの確認が必要）", [t for t in tasks.values() if t["st"] == "確認待ち"])
    show("時期未定（工程表で「時期未定」になる）", nodate)

    for w in warnings:
        print(f"\n注意：{w}")
    for e in errors:
        print(f"\nエラー：{e}")
    if errors:
        sys.exit(1)
    print("\n工程表が読める形になっています。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
