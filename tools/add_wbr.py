# index.html の本文の日本語に、BudouXの文節の切れ目で <wbr> を入れる（何度実行しても同じ結果）
# 使い方：pip install budoux のあと python tools/add_wbr.py index.html（文を直したら実行し直す）
import re, sys, budoux
p = budoux.load_default_japanese_parser()
path = sys.argv[1]
s = open(path, encoding='utf-8').read()
head, body = s.split('<body>', 1)
JA = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
SKIP = {'script','style','svg','select','option','h1','title'}
out = []; stack = []
for tok in re.split(r'(<[^>]+>)', body):
    if tok.startswith('<'):
        m = re.match(r'<(/?)([a-zA-Z0-9]+)', tok)
        if m:
            name = m.group(2).lower()
            if name in SKIP and not tok.endswith('/>'):
                if m.group(1): 
                    if stack and stack[-1] == name: stack.pop()
                else: stack.append(name)
        out.append(tok); continue
    if stack or not JA.search(tok):
        out.append(tok); continue
    t = tok.replace('<wbr>', '').replace('&#8288;', '\u2060')
    lead = t[:len(t)-len(t.lstrip())]; trail = t[len(t.rstrip()):]; core = t.strip()
    chunks = p.parse(core)
    res = chunks[0]
    for c in chunks[1:]:
        res += ('' if res.endswith('\u2060') or c.startswith('\u2060') else '<wbr>') + c
    out.append(lead + res.replace('\u2060', '&#8288;') + trail)
open(path, 'w', encoding='utf-8', newline='').write(head + '<body>' + ''.join(out))
