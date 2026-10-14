"""Assemble manuscript.md from head.txt + body_v3.txt, converting pipe tables to LaTeX."""
import re

def col_spec(head, body, widths_text):
    return head, body

def build():
    s = open('head.txt').read() + open('body_v3.txt').read()
    blocks = re.findall(r'(Table: (.+?)\n\n((?:\|.*\|\n)+))', s)
    def tex(x):
        x = x.replace('&', r'\&'); x = re.sub(r'(?<!\\)%', r'\%', x); return x
    for full, cap, tab in blocks:
        rows = [r.strip().strip('|').split('|') for r in tab.strip().split('\n')]
        head = [c.strip() for c in rows[0]]
        body = [[c.strip() for c in r] for r in rows[2:]]
        ncol = len(head)
        # a column is "text" if any cell is long; text columns wrap, numeric columns stay right-aligned
        maxlen = [max([len(head[j])] + [len(r[j]) for r in body]) for j in range(ncol)]
        text_col = [maxlen[j] > 26 for j in range(ncol)]
        wide = ncol > 6
        if any(text_col):
            total = sum(maxlen[j] for j in range(ncol) if text_col[j])
            spec = []
            # reserve space for the short columns in proportion to their content, then share the rest
            reserved = sum(max(0.045, min(0.11, maxlen[j] * 0.013)) for j in range(ncol) if not text_col[j])
            budget = max(0.25, 0.94 - reserved)
            for j in range(ncol):
                if text_col[j]:
                    spec.append(r'>{\raggedright\arraybackslash}p{%.3f\textwidth}' % (budget * maxlen[j] / total))
                else:
                    spec.append('r' if j else 'l')
            cols = ''.join(spec)
        else:
            cols = 'l' + ('c' if wide else 'r') * (ncol - 1)
        inner = [r'\begin{tabular}{' + cols + '}', r'\toprule',
                 ' & '.join(tex(h) for h in head) + r' \\', r'\midrule']
        inner += [' & '.join(tex(c) for c in r) + r' \\' for r in body]
        inner += [r'\bottomrule', r'\end{tabular}']
        out = [r'\begin{table}[htbp]', r'\centering' + (r'\footnotesize' if wide else r'\small'),
               r'\caption{' + tex(cap) + '}'] + inner + [r'\end{table}']
        s = s.replace(full, '```{=latex}\n' + '\n'.join(out) + '\n```\n')
    open('manuscript.md', 'w').write(s)
    print(len(blocks), "tables converted")

if __name__ == '__main__':
    build()
