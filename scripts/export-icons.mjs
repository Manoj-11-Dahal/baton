import fs from 'node:fs';
import path from 'node:path';
import { Resvg } from '@resvg/resvg-js';

const root = path.resolve(__dirname, '..');
const render = (svg, width) => new Resvg(svg, { fitTo: { mode: 'width', value: width } }).render().asPng();

const appIcon = fs.readFileSync(path.join(root, 'assets/icon.svg'), 'utf8');
fs.writeFileSync(path.join(root, 'assets/icon.png'), render(appIcon, 1024));
console.log('assets/icon.png');

if (process.argv.includes('--sheet')) {
  const dir = path.join(root, 'assets/icons');
  const names = fs.readdirSync(dir).filter((f) => f.endsWith('.svg')).sort();
  const cols = 10;
  const cell = 96;
  const rows = Math.ceil(names.length / cols);
  const escape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const cells = names.map((file, i) => {
    const inner = fs.readFileSync(path.join(dir, file), 'utf8').replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
    const x = (i % cols) * cell;
    const y = Math.floor(i / cols) * cell;
    return (
      `<g transform="translate(${x + 30} ${y + 14}) scale(1.5)" fill="none" stroke="#e8e8ee" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" color="#e8e8ee">${inner}</g>` +
      `<text x="${x + cell / 2}" y="${y + 76}" font-family="sans-serif" font-size="10" fill="#8b8b96" text-anchor="middle">${escape(file.replace('.svg', ''))}</text>`
    );
  });
  const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="${cols * cell}" height="${rows * cell}" viewBox="0 0 ${cols * cell} ${rows * cell}"><rect width="100%" height="100%" fill="#111114"/>${cells.join('')}</svg>`;
  fs.mkdirSync(path.join(root, 'docs'), { recursive: true });
  fs.writeFileSync(path.join(root, 'docs/icons.png'), render(sheet, cols * cell * 2));
  console.log(`docs/icons.png (${names.length} icons)`);
}
