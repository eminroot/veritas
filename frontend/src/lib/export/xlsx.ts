/**
 * A small .xlsx writer with no dependencies: sheets of typed cells, a header row with
 * filters and a frozen pane, money and dates stored as real numbers with formats (so they
 * add up and sort), all packed into a ZIP. Excel, LibreOffice, Numbers and Google Sheets
 * open it.
 */

export type CellType = "text" | "money" | "int" | "date" | "pct" | "bold" | "muted" | "title" | "boldMoney";
export type Cell = string | number | null | undefined | { v: string | number | null; t: CellType };
export type Column = { header: string; width: number; type?: CellType };
export type Sheet = {
  name: string;
  columns: Column[];
  rows: Cell[][];
  /** Lines above the table, such as a title and a note. */
  intro?: Cell[][];
  /** false for a sheet of plain lines, without a header row or filters. */
  table?: boolean;
};

/** Indexes into cellXfs in styles.xml below. */
const STYLE: Record<CellType | "head", number> = {
  text: 0,
  head: 1,
  money: 2,
  int: 3,
  date: 4,
  pct: 5,
  title: 6,
  muted: 7,
  bold: 8,
  boldMoney: 9,
};

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="d mmm yyyy"/></numFmts>
<fonts count="4">
<font><sz val="11"/><color rgb="FF242426"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><color rgb="FF242426"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="15"/><color rgb="FF242426"/><name val="Calibri"/><family val="2"/></font>
<font><sz val="10"/><color rgb="FF7A7A7C"/><name val="Calibri"/><family val="2"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9FF5C"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top/><bottom style="thin"><color rgb="FF35363B"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="10">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf numFmtId="9" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

const NUMERIC = new Set<CellType>(["money", "int", "pct", "boldMoney"]);

/** Text that XML 1.0 accepts: its control characters dropped and its markup escaped. */
function esc(text: string): string {
  let kept = "";
  for (const ch of text) {
    const c = ch.charCodeAt(0);
    if ((c < 0x20 && c !== 0x09 && c !== 0x0a && c !== 0x0d) || c === 0xfffe || c === 0xffff) continue;
    kept += ch;
  }
  return kept.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Column letters: 0 → A, 25 → Z, 26 → AA. */
function column(n: number): string {
  let s = "";
  for (let k = n + 1; k > 0; k = Math.floor((k - 1) / 26)) s = String.fromCharCode(65 + ((k - 1) % 26)) + s;
  return s;
}

/** "2026-09-20" as Excel's day number, or null when it is not a date. */
function serial(iso: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return (Date.UTC(+m[1], +m[2] - 1, +m[3]) - Date.UTC(1899, 11, 30)) / 86_400_000;
}

function cellXml(value: Cell, ref: string, fallback: CellType): string {
  const [v, type] = value !== null && typeof value === "object" ? [value.v, value.t] : [value, fallback];
  if (v === null || v === undefined || v === "") return "";
  if (type === "date" && typeof v === "string") {
    const day = serial(v);
    if (day !== null) return `<c r="${ref}" s="${STYLE.date}"><v>${day}</v></c>`;
  }
  if (typeof v === "number" && Number.isFinite(v)) {
    return `<c r="${ref}" s="${STYLE[type === "date" ? "int" : type]}"><v>${v}</v></c>`;
  }
  const style = NUMERIC.has(type) || type === "date" ? STYLE.text : STYLE[type];
  return `<c r="${ref}" t="inlineStr" s="${style}"><is><t xml:space="preserve">${esc(String(v))}</t></is></c>`;
}

const sheetName = (name: string) => name.replace(/[[\]:*?/\\]/g, " ").slice(0, 31) || "Sheet";

function sheetXml(sheet: Sheet, first: boolean): { xml: string; filter: string | null } {
  const rows: string[] = [];
  let r = 0;
  const line = (cells: Cell[], types: (CellType | undefined)[]) => {
    r += 1;
    const body = cells.map((c, i) => cellXml(c, `${column(i)}${r}`, types[i] ?? "text")).join("");
    rows.push(`<row r="${r}">${body}</row>`);
  };
  for (const cells of sheet.intro ?? []) line(cells, []);
  const table = sheet.table !== false;
  let head = 0;
  if (table) {
    if (sheet.intro?.length) r += 1;
    r += 1;
    head = r;
    rows.push(
      `<row r="${r}">${sheet.columns
        .map((c, i) => `<c r="${column(i)}${r}" t="inlineStr" s="${STYLE.head}"><is><t xml:space="preserve">${esc(c.header)}</t></is></c>`)
        .join("")}</row>`
    );
  }
  const types = sheet.columns.map((c) => c.type);
  for (const cells of sheet.rows) line(cells, types);

  const last = column(Math.max(0, sheet.columns.length - 1));
  const filter = table && sheet.rows.length ? `A${head}:${last}${r}` : null;
  const pane = table
    ? `<pane ySplit="${head}" topLeftCell="A${head + 1}" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A${head + 1}" sqref="A${head + 1}"/>`
    : "";
  const cols = sheet.columns.map((c, i) => `<col min="${i + 1}" max="${i + 1}" width="${c.width}" customWidth="1"/>`).join("");
  const xml =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n` +
    `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
    `<sheetViews><sheetView workbookViewId="0"${first ? ' tabSelected="1"' : ""}>${pane}</sheetView></sheetViews>` +
    `<sheetFormatPr defaultRowHeight="15"/>` +
    (cols ? `<cols>${cols}</cols>` : "") +
    `<sheetData>${rows.join("")}</sheetData>` +
    (filter ? `<autoFilter ref="${filter}"/>` : "") +
    `<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>` +
    `</worksheet>`;
  return { xml, filter };
}

const CRC = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) c = CRC[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** A ZIP of stored (uncompressed) files: every .xlsx reader accepts it. */
function zip(files: { name: string; data: Uint8Array }[], when: Date, type: string): Blob {
  const encoder = new TextEncoder();
  const time = (when.getHours() << 11) | (when.getMinutes() << 5) | Math.floor(when.getSeconds() / 2);
  const date = ((when.getFullYear() - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate();
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const crc = crc32(file.data);
    const local = new Uint8Array(30 + name.length);
    const l = new DataView(local.buffer);
    l.setUint32(0, 0x04034b50, true);
    l.setUint16(4, 20, true);
    l.setUint16(6, 0x0800, true);
    l.setUint16(10, time, true);
    l.setUint16(12, date, true);
    l.setUint32(14, crc, true);
    l.setUint32(18, file.data.length, true);
    l.setUint32(22, file.data.length, true);
    l.setUint16(26, name.length, true);
    local.set(name, 30);
    parts.push(local, file.data);

    const entry = new Uint8Array(46 + name.length);
    const c = new DataView(entry.buffer);
    c.setUint32(0, 0x02014b50, true);
    c.setUint16(4, 20, true);
    c.setUint16(6, 20, true);
    c.setUint16(8, 0x0800, true);
    c.setUint16(12, time, true);
    c.setUint16(14, date, true);
    c.setUint32(16, crc, true);
    c.setUint32(20, file.data.length, true);
    c.setUint32(24, file.data.length, true);
    c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    entry.set(name, 46);
    central.push(entry);
    offset += local.length + file.data.length;
  }
  const size = central.reduce((s, e) => s + e.length, 0);
  const end = new Uint8Array(22);
  const e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true);
  e.setUint16(8, files.length, true);
  e.setUint16(10, files.length, true);
  e.setUint32(12, size, true);
  e.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end], { type });
}

export function workbook(sheets: Sheet[], meta: { title: string; author: string }): Blob {
  const encoder = new TextEncoder();
  const now = new Date();
  const names = sheets.map((s) => sheetName(s.name));
  const built = sheets.map((s, i) => sheetXml(s, i === 0));
  const quote = (name: string) => `'${name.replace(/'/g, "''")}'`;
  const absolute = (range: string) => range.replace(/([A-Z]+)(\d+)/g, "$$$1$$$2");
  const defined = built
    .map((b, i) => (b.filter ? `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">${esc(quote(names[i]))}!${absolute(b.filter)}</definedName>` : ""))
    .join("");

  const files: { name: string; data: string }[] = [
    {
      name: "[Content_Types].xml",
      data:
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
        `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
        `<Default Extension="xml" ContentType="application/xml"/>` +
        `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
        sheets.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("") +
        `<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>` +
        `<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>` +
        `</Types>`,
    },
    {
      name: "_rels/.rels",
      data:
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
        `<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>` +
        `</Relationships>`,
    },
    {
      name: "docProps/core.xml",
      data:
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">` +
        `<dc:title>${esc(meta.title)}</dc:title><dc:creator>${esc(meta.author)}</dc:creator>` +
        `<dcterms:created xsi:type="dcterms:W3CDTF">${now.toISOString().replace(/\.\d+Z$/, "Z")}</dcterms:created>` +
        `</cp:coreProperties>`,
    },
    {
      name: "xl/workbook.xml",
      data:
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
        `<bookViews><workbookView activeTab="0"/></bookViews>` +
        `<sheets>${names.map((n, i) => `<sheet name="${esc(n)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets>` +
        (defined ? `<definedNames>${defined}</definedNames>` : "") +
        `</workbook>`,
    },
    {
      name: "xl/_rels/workbook.xml.rels",
      data:
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        sheets.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("") +
        `<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>` +
        `</Relationships>`,
    },
    { name: "xl/styles.xml", data: STYLES },
    ...built.map((b, i) => ({ name: `xl/worksheets/sheet${i + 1}.xml`, data: b.xml })),
  ];
  return zip(
    files.map((x) => ({ name: x.name, data: encoder.encode(x.data) })),
    now,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  );
}
