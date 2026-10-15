const fs = require('fs');
const {
  Document,
  Packer,
  PageBreak,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  BorderStyle,
  WidthType,
  AlignmentType,
  UnderlineType,
  ExternalHyperlink,
  ShadingType,
  VerticalAlign,
} = require('docx');

const args = process.argv.slice(2);
if (args.length < 2) {
  console.error('Usage: node diagnostico_word.js <input.json> <output.docx>');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(args[0], 'utf-8'));
const USABLE_WIDTH = 10538; // DXA

const COLOR_NAVY = '1F3A5F';
const COLOR_RED = 'CC0000';
const COLOR_GRAY = '666666';
const COLOR_AMBER_BG = 'FFF6E5';
const COLOR_AMBER_BORDER = 'E3B341';
const COLOR_ZEBRA = 'F5F5F5';

// Parse markup: <b>bold</b> and <link href="url">text</link>
function parseMarkup(text) {
  const parts = [];
  let last = 0;

  // Match both patterns
  const regex = /<b>([^<]*)<\/b>|<link href="([^"]+)">([^<]*)<\/link>|([^<]+)/g;
  let match;

  while ((match = regex.exec(text))) {
    if (match[1]) {
      // Bold text
      parts.push(new TextRun({ text: match[1], bold: true }));
    } else if (match[2] && match[3]) {
      // Link
      parts.push(new ExternalHyperlink({
        children: [new TextRun({ text: match[3], color: '0563C1', underline: { type: UnderlineType.SINGLE } })],
        url: match[2],
      }));
    } else if (match[4]) {
      // Plain text
      parts.push(new TextRun(match[4]));
    }
  }

  return parts.length > 0 ? parts : [new TextRun('')];
}

function percentToDxa(pct) {
  return Math.round((USABLE_WIDTH * pct) / 100);
}

// Build document
const sections = [];

for (const block of data.bloques) {
  if (block.k === 'titulo') {
    sections.push(new Paragraph({ text: block.t[0], size: 32, bold: true, alignment: AlignmentType.CENTER, spacing: { after: 100 } }));
    sections.push(new Paragraph({ text: block.t[1], size: 20, color: COLOR_GRAY, alignment: AlignmentType.CENTER, spacing: { after: 400 } }));
  } else if (block.k === 'p') {
    sections.push(new Paragraph({
      children: parseMarkup(block.t),
      size: block.nota ? 18 : 22,
      color: block.gris ? COLOR_GRAY : undefined,
      spacing: { after: 200 },
      alignment: AlignmentType.JUSTIFIED,
    }));
  } else if (block.k === 'h') {
    sections.push(new Paragraph({ text: block.t, size: 26, bold: true, color: COLOR_NAVY, spacing: { before: 200, after: 200 } }));
  } else if (block.k === 'kpis') {
    const cells = block.v.map(item =>
      new TableCell({
        children: [
          new Paragraph({ text: item[0], size: 32, bold: true, color: COLOR_RED, alignment: AlignmentType.CENTER }),
          new Paragraph({ text: item[1], size: 18, alignment: AlignmentType.CENTER }),
        ],
        shading: { fill: COLOR_ZEBRA, type: ShadingType.CLEAR },
        borders: { top: { style: BorderStyle.SINGLE, size: 6 }, bottom: { style: BorderStyle.SINGLE, size: 6 }, left: { style: BorderStyle.SINGLE, size: 6 }, right: { style: BorderStyle.SINGLE, size: 6 } },
        verticalAlign: VerticalAlign.CENTER,
      })
    );
    sections.push(new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, rows: [new TableRow({ children: cells })] }));
    sections.push(new Paragraph({ text: '', spacing: { after: 200 } }));
  } else if (block.k === 'tabla') {
    const rows = block.filas.map((fila, idx) => {
      const isHeader = idx === 0;
      const isRojo = block.rojos && block.rojos[idx - 1];
      const widths = block.anchos.map(p => ({ size: percentToDxa(p), type: WidthType.DXA }));

      return new TableRow({
        children: fila.map((cell, cidx) => {
          let text = '';
          let link = null;
          if (typeof cell === 'object' && cell.link) {
            text = 'Ver en SECOP';
            link = cell.link;
          } else {
            text = String(cell || '');
          }

          const isBold = block.negrita_col === cidx;
          const isRed = block.rojo_col === cidx && isRojo;
          const bg = isHeader ? COLOR_NAVY : idx % 2 === 0 ? COLOR_ZEBRA : 'FFFFFF';
          const color = isHeader ? 'FFFFFF' : isRed ? COLOR_RED : undefined;

          let children;
          if (link) {
            children = [new Paragraph({ children: [new ExternalHyperlink({ children: [new TextRun({ text, bold: isBold, color: '0563C1', underline: { type: UnderlineType.SINGLE } })], url: link })], size: 18 })];
          } else {
            children = [new Paragraph({ children: [new TextRun({ text, bold: isBold, color })], size: 18 })];
          }

          return new TableCell({
            children,
            width: widths[cidx],
            shading: bg !== 'FFFFFF' ? { fill: bg, type: ShadingType.CLEAR } : undefined,
            borders: { top: { style: BorderStyle.SINGLE, size: 6 }, bottom: { style: BorderStyle.SINGLE, size: 6 }, left: { style: BorderStyle.SINGLE, size: 6 }, right: { style: BorderStyle.SINGLE, size: 6 } },
            margins: { top: 60, bottom: 60, left: 60, right: 60 },
            verticalAlign: VerticalAlign.CENTER,
          });
        }),
      });
    });

    sections.push(new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, rows }));
    sections.push(new Paragraph({ text: '', spacing: { after: 200 } }));
  } else if (block.k === 'caja') {
    sections.push(new Table({
      width: { size: 100, type: WidthType.PERCENTAGE },
      rows: [new TableRow({
        children: [new TableCell({
          children: [new Paragraph({ children: parseMarkup(block.t), size: 20 })],
          shading: { fill: COLOR_AMBER_BG, type: ShadingType.CLEAR },
          borders: {
            top: { style: BorderStyle.SINGLE, size: 12, color: COLOR_AMBER_BORDER },
            bottom: { style: BorderStyle.SINGLE, size: 12, color: COLOR_AMBER_BORDER },
            left: { style: BorderStyle.SINGLE, size: 12, color: COLOR_AMBER_BORDER },
            right: { style: BorderStyle.SINGLE, size: 12, color: COLOR_AMBER_BORDER },
          },
          margins: { top: 160, bottom: 160, left: 160, right: 160 },
        })],
      })],
    }));
    sections.push(new Paragraph({ text: '', spacing: { after: 200 } }));
  } else if (block.k === 'salto') {
    sections.push(new PageBreak());
  } else if (block.k === 'firma') {
    sections.push(new Paragraph({ text: '', spacing: { after: 200 } }));
    sections.push(new Paragraph({ text: block.autor, size: 20, bold: true, spacing: { after: 80 } }));
    block.titulos.forEach(t => sections.push(new Paragraph({ text: t, size: 18, spacing: { after: 40 } })));
    sections.push(new Paragraph({ text: '', spacing: { after: 120 } }));
    sections.push(new Paragraph({ text: block.contacto, size: 18, spacing: { after: 200 } }));
  }
}

const doc = new Document({
  sections: [{
    properties: {
      page: {
        width: 12240,
        height: 15840,
        margins: { top: 851, bottom: 851, left: 851, right: 851 },
      },
    },
    children: sections,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(args[1], buffer);
  console.log(`✓ Written to ${args[1]}`);
});
