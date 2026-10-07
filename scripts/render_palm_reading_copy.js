const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const docsDir = path.join(root, 'docs', 'workshops', 'neurips-2026');
const mainPath = path.join(docsDir, 'PALM_PROPOSAL_DRAFT.md');
const supplementPath = path.join(docsDir, 'PALM_SUPPLEMENTARY_MATERIAL.md');
const outputPath = path.join(docsDir, 'PALM_COMPLETE_READING_COPY.html');

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function latexToHtml(source) {
  let text = escapeHtml(source.trim())
    .replace(/^\\\[|\\\]$/g, '')
    .replace(/\\begin\{aligned\}|\\end\{aligned\}/g, '')
    .replace(/\\operatorname\{([^}]+)\}/g, '<span class="roman">$1</span>')
    .replace(/\\mathrm\{([^}]+)\}/g, '<span class="roman">$1</span>')
    .replace(/\\text\{([^}]+)\}/g, '<span class="roman">$1</span>')
    .replace(/\\left|\\right|\\!|\\,|\\;/g, '')
    .replace(/\\qquad/g, '&emsp;')
    .replace(/\\bigsqcup/g, '⨆')
    .replace(/\\iota/g, 'ι')
    .replace(/\\sigma/g, 'σ')
    .replace(/\\preceq/g, '≼')
    .replace(/\\exists/g, '∃')
    .replace(/\\notin/g, '∉')
    .replace(/\\in/g, '∈')
    .replace(/\\lor/g, '∨')
    .replace(/\\land/g, '∧')
    .replace(/\\cup/g, '∪')
    .replace(/\\subseteq/g, '⊆')
    .replace(/\\to/g, '→')
    .replace(/\\leq/g, '≤')
    .replace(/\\max/g, '<span class="roman">max</span>')
    .replace(/\\lceil/g, '⌈')
    .replace(/\\rceil/g, '⌉')
    .replace(/\\\{/g, '〈SETOPEN〉')
    .replace(/\\\}/g, '〈SETCLOSE〉')
    .replace(/&amp;/g, '')
    .replace(/\\\\/g, '<br>');

  text = text.replace(/_\{([^{}]+)\}/g, (_, value) =>
    `<sub>${value.replaceAll('_', ',')}</sub>`);
  text = text.replace(/\^\{([^{}]+)\}/g, '<sup>$1</sup>');
  text = text.replace(/_([A-Za-z0-9]+)/g, '<sub>$1</sub>');
  text = text.replace(/\^([A-Za-z0-9]+)/g, '<sup>$1</sup>');
  text = text
    .replaceAll('〈SETOPEN〉', '{')
    .replaceAll('〈SETCLOSE〉', '}')
    .replace(/[{}]/g, '')
    .replace(/\\/g, '')
    .replace(/\s*<br>\s*/g, '<br>')
    .trim();
  return `<span class="math">${text}</span>`;
}

function inlineMarkdown(text) {
  const math = [];
  const withoutMath = text.replace(/\$([^$]+)\$/g, (_, source) => {
    const token = `PALMINLINEMATH${math.length}TOKEN`;
    math.push(latexToHtml(source));
    return token;
  });
  let html = escapeHtml(withoutMath);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  math.forEach((value, index) => {
    html = html.replace(`PALMINLINEMATH${index}TOKEN`, value);
  });
  return html;
}

function isTableDivider(line) {
  return /^\|(?:\s*:?-+:?\s*\|)+$/.test(line.trim());
}

function tableCells(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
}

function renderTable(lines, start) {
  const rows = [];
  let index = start;
  while (index < lines.length && lines[index].trim().startsWith('|')) {
    rows.push(lines[index]);
    index += 1;
  }
  const header = tableCells(rows[0]);
  const body = rows.slice(isTableDivider(rows[1] || '') ? 2 : 1);
  let html = '<table><thead><tr>';
  html += header.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('');
  html += '</tr></thead><tbody>';
  for (const row of body) {
    html += '<tr>' + tableCells(row).map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('') + '</tr>';
  }
  html += '</tbody></table>';
  return { html, index };
}

function isBlockStart(line) {
  const text = line.trim();
  return !text || /^#{1,3}\s/.test(text) || text.startsWith('>') ||
    text.startsWith('\\[') || text.startsWith('|') ||
    /^[-*]\s+/.test(text) || /^\d+[.)]\s+/.test(text);
}

function renderList(lines, start, ordered) {
  const pattern = ordered ? /^\d+[.)]\s+(.*)$/ : /^[-*]\s+(.*)$/;
  const items = [];
  let index = start;
  while (index < lines.length) {
    const match = lines[index].trim().match(pattern);
    if (!match) break;
    const parts = [match[1]];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) {
      parts.push(lines[index].trim());
      index += 1;
    }
    items.push(parts.join(' '));
  }
  const tag = ordered ? 'ol' : 'ul';
  return {
    html: `<${tag}>${items.map(item => `<li>${inlineMarkdown(item)}</li>`).join('')}</${tag}>`,
    index,
  };
}

function sectionNeedsResults(title) {
  return title === 'Abstract' || title.startsWith('7.2 Planned twelve-chain analysis') || title.startsWith('9. Conclusion');
}

function renderMarkdown(markdown, supplement = false) {
  const lines = markdown.replaceAll('\r\n', '\n').split('\n');
  const output = [];
  let index = 0;
  let highlighted = false;
  let highlightedLevel = 0;

  if (supplement) output.push('<div class="page-break"></div><article class="supplement">');

  while (index < lines.length) {
    const raw = lines[index];
    const line = raw.trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const title = heading[2];
      if (!supplement && highlighted && level <= highlightedLevel) {
        output.push('</section>');
        highlighted = false;
        highlightedLevel = 0;
      }
      if (!supplement && sectionNeedsResults(title)) {
        if (highlighted) output.push('</section>');
        highlighted = true;
        highlightedLevel = level;
        output.push('<section class="needs-results">');
      }
      const headingLevel = supplement && level === 1 ? 1 : level;
      output.push(`<h${headingLevel}>${inlineMarkdown(title)}</h${headingLevel}>`);
      index += 1;
      continue;
    }

    if (line.startsWith('>')) {
      const quote = [];
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        quote.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      output.push(`<div class="draft-note">${inlineMarkdown(quote.join(' '))}</div>`);
      continue;
    }

    if (line.startsWith('\\[')) {
      const math = [raw];
      index += 1;
      while (index < lines.length && !lines[index].trim().endsWith('\\]')) {
        math.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        math.push(lines[index]);
        index += 1;
      }
      output.push(`<div class="display-math">${latexToHtml(math.join('\n'))}</div>`);
      continue;
    }

    if (line.startsWith('|')) {
      const table = renderTable(lines, index);
      output.push(table.html);
      index = table.index;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const list = renderList(lines, index, false);
      output.push(list.html);
      index = list.index;
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const list = renderList(lines, index, true);
      output.push(list.html);
      index = list.index;
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (index < lines.length && !isBlockStart(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    const content = inlineMarkdown(paragraph.join(' '));
    let meta = '';
    if (/^<strong>Anonymous/.test(content)) meta = ' class="subtitle"';
    if (supplement && content.includes('must be reconciled with the protocol')) {
      meta = ' class="needs-results"';
    }
    output.push(`<p${meta}>${content}</p>`);
  }

  if (highlighted) output.push('</section>');
  if (supplement) output.push('</article>');
  return output.join('\n');
}

const main = renderMarkdown(fs.readFileSync(mainPath, 'utf8'));
const supplement = renderMarkdown(fs.readFileSync(supplementPath, 'utf8'), true);

const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PALM Complete Reading Copy</title>
  <style>
    @page { size: A4; margin: 20mm 18mm 20mm 18mm; }
    * { box-sizing: border-box; }
    body {
      max-width: 850px;
      margin: 36px auto;
      padding: 0 28px;
      color: #17202a;
      font: 10.8pt/1.48 Georgia, "Times New Roman", serif;
    }
    h1, h2, h3, h4 { color: #111827; line-height: 1.2; break-after: avoid; }
    h1 { font-size: 23pt; margin: 0 0 12px; }
    h2 { font-size: 16pt; margin: 28px 0 10px; }
    h3 { font-size: 12.8pt; margin: 21px 0 8px; }
    h4 { font-size: 11.3pt; margin: 17px 0 7px; }
    p { margin: 8px 0 11px; }
    .subtitle { color: #4b5563; margin-top: -4px; }
    .draft-note {
      border-left: 4px solid #64748b;
      background: #f8fafc;
      padding: 10px 14px;
      margin: 17px 0;
    }
    .needs-results {
      background: #fff3a3;
      border: 1px solid #e0b500;
      border-radius: 5px;
      margin: 22px -12px;
      padding: 0 12px 10px;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .legend {
      background: #fff3a3;
      border: 1px solid #e0b500;
      padding: 9px 12px;
      margin: 18px 0 24px;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 9.2pt; }
    th, td { border: 1px solid #9ca3af; padding: 6px; vertical-align: top; }
    th { background: #edf1f5; text-align: left; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    code { font: 9pt "DejaVu Sans Mono", Consolas, monospace; overflow-wrap: anywhere; }
    .math { font: italic 11.3pt "Cambria Math", "STIX Two Math", Georgia, serif; }
    .math .roman { font-style: normal; }
    .display-math { text-align: center; margin: 15px 0; line-height: 1.65; break-inside: avoid; }
    li { margin: 4px 0; }
    .page-break { break-before: page; page-break-before: always; }
    .supplement { border-top: 2px solid #334155; padding-top: 18px; }
    a { color: #1d4ed8; text-decoration: none; }
    @media print {
      body { max-width: none; margin: 0; padding: 0; }
      a { color: inherit; }
    }
  </style>
</head>
<body>
  <div class="legend"><strong>Yellow highlight:</strong> pending or requires revision. The abstract, planned twelve-chain analysis, and conclusion await confirmatory results; the supplementary warning awaits protocol reconciliation.</div>
  ${main}
  ${supplement}
</body>
</html>`;

fs.writeFileSync(outputPath, html);
