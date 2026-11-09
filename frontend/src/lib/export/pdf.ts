/**
 * A small PDF writer for the console's exports, with no dependencies: A4 pages, text in an
 * embedded TrueType font (so ə, ş, ğ and the manat sign print exactly as on screen, and the
 * text can be selected and searched), filled and rounded shapes, lines and clipping. The
 * browser's CompressionStream deflates the streams. Positions are points from the top-left
 * corner of the page; text is placed by its baseline.
 */

export type Rgb = readonly [number, number, number];

/** What the writer needs from a TrueType font: its glyphs, their widths and its metrics. */
export class TrueType {
  readonly bytes: Uint8Array;
  readonly name: string;
  readonly unitsPerEm: number;
  readonly ascent: number;
  readonly descent: number;
  readonly capHeight: number;
  readonly italicAngle: number;
  readonly bbox: [number, number, number, number];
  private readonly advances: Uint16Array;
  private readonly cmap = new Map<number, number>();

  constructor(bytes: Uint8Array, name: string) {
    this.bytes = bytes;
    this.name = name;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const tables = new Map<string, number>();
    const count = view.getUint16(4);
    for (let i = 0; i < count; i++) {
      const at = 12 + i * 16;
      tables.set(String.fromCharCode(bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]), view.getUint32(at + 8));
    }
    const table = (tag: string) => {
      const at = tables.get(tag);
      if (at === undefined) throw new Error(`The font has no ${tag} table`);
      return at;
    };

    const head = table("head");
    this.unitsPerEm = view.getUint16(head + 18);
    this.bbox = [view.getInt16(head + 36), view.getInt16(head + 38), view.getInt16(head + 40), view.getInt16(head + 42)];
    const hhea = table("hhea");
    this.ascent = view.getInt16(hhea + 4);
    this.descent = view.getInt16(hhea + 6);
    const metrics = view.getUint16(hhea + 34);
    const glyphs = view.getUint16(table("maxp") + 4);
    const hmtx = table("hmtx");
    this.advances = new Uint16Array(glyphs);
    let advance = 0;
    for (let g = 0; g < glyphs; g++) {
      if (g < metrics) advance = view.getUint16(hmtx + g * 4);
      this.advances[g] = advance;
    }
    const os2 = tables.get("OS/2");
    this.capHeight = os2 !== undefined && view.getUint16(os2) >= 2 ? view.getInt16(os2 + 88) : Math.round(this.ascent * 0.7);
    const post = tables.get("post");
    this.italicAngle = post !== undefined ? view.getInt32(post + 4) / 65536 : 0;
    this.readCmap(view, table("cmap"));
  }

  private readCmap(view: DataView, at: number) {
    let bmp = -1;
    let full = -1;
    for (let i = 0; i < view.getUint16(at + 2); i++) {
      const platform = view.getUint16(at + 4 + i * 8);
      const encoding = view.getUint16(at + 6 + i * 8);
      const sub = at + view.getUint32(at + 8 + i * 8);
      const format = view.getUint16(sub);
      const unicode = platform === 0 || (platform === 3 && (encoding === 1 || encoding === 10));
      if (unicode && format === 12) full = sub;
      if (unicode && format === 4 && bmp < 0) bmp = sub;
    }
    if (full >= 0) {
      const groups = view.getUint32(full + 12);
      for (let i = 0; i < groups; i++) {
        const g = full + 16 + i * 12;
        const start = view.getUint32(g);
        const end = Math.min(view.getUint32(g + 4), 0x10ffff);
        const first = view.getUint32(g + 8);
        for (let c = start; c <= end; c++) this.cmap.set(c, first + (c - start));
      }
      return;
    }
    if (bmp < 0) throw new Error("The font has no Unicode character map");
    const twice = view.getUint16(bmp + 6);
    const ends = bmp + 14;
    const starts = ends + twice + 2;
    const deltas = starts + twice;
    const offsets = deltas + twice;
    for (let s = 0; s < twice / 2; s++) {
      const start = view.getUint16(starts + s * 2);
      const end = view.getUint16(ends + s * 2);
      const delta = view.getInt16(deltas + s * 2);
      const offset = view.getUint16(offsets + s * 2);
      for (let c = start; c <= end && c !== 0xffff; c++) {
        let g = offset === 0 ? (c + delta) & 0xffff : view.getUint16(offsets + s * 2 + offset + (c - start) * 2);
        if (offset !== 0 && g !== 0) g = (g + delta) & 0xffff;
        if (g) this.cmap.set(c, g);
      }
    }
  }

  glyph(codePoint: number): number {
    return this.cmap.get(codePoint) ?? 0;
  }

  advance(glyph: number): number {
    return this.advances[Math.min(glyph, this.advances.length - 1)];
  }

  /** The width of a line of text, in points. */
  width(text: string, size: number, spacing = 0): number {
    let units = 0;
    let count = 0;
    for (const ch of text) {
      units += this.advance(this.glyph(ch.codePointAt(0) as number));
      count += 1;
    }
    return (units * size) / this.unitsPerEm + spacing * Math.max(0, count - 1);
  }
}

export type TextOptions = {
  font?: string;
  size?: number;
  color?: Rgb;
  align?: "left" | "right" | "center";
  /** Extra space between letters, in points. */
  spacing?: number;
};

const A4: [number, number] = [595.28, 841.89];
const f = (n: number) => String(Math.round(n * 100) / 100);
const rgb = (c: Rgb) => c.map((v) => f(v / 255)).join(" ");

/** A string as a PDF text object: literal when plain ASCII, UTF-16 otherwise. */
function pdfString(text: string): string {
  if (/^[\x20-\x7e]*$/.test(text)) return "(" + text.replace(/[\\()]/g, (m) => "\\" + m) + ")";
  let hex = "FEFF";
  for (let i = 0; i < text.length; i++) hex += text.charCodeAt(i).toString(16).padStart(4, "0");
  return `<${hex}>`;
}

function utf16Hex(codePoint: number): string {
  return String.fromCodePoint(codePoint)
    .split("")
    .map((c) => c.charCodeAt(0).toString(16).padStart(4, "0"))
    .join("");
}

async function deflate(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data]).stream().pipeThrough(new CompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

type FontSlot = { key: string; tag: string; font: TrueType; used: Map<number, number> };

export class PdfDoc {
  readonly width = A4[0];
  readonly height = A4[1];
  private readonly pages: string[][] = [];
  private current = -1;
  private readonly fonts = new Map<string, FontSlot>();

  constructor(fonts: Record<string, TrueType>) {
    Object.entries(fonts).forEach(([key, font], i) => this.fonts.set(key, { key, tag: `F${i + 1}`, font, used: new Map() }));
  }

  get pageCount(): number {
    return this.pages.length;
  }

  addPage(): number {
    this.pages.push([]);
    this.current = this.pages.length - 1;
    return this.current;
  }

  /** Draw on an earlier page, for the footers that need the page count. */
  onPage(index: number) {
    this.current = index;
  }

  private slot(key = "regular"): FontSlot {
    const slot = this.fonts.get(key) ?? this.fonts.values().next().value;
    if (!slot) throw new Error("No font");
    return slot;
  }

  private ops(...lines: string[]) {
    this.pages[this.current].push(...lines);
  }

  measure(text: string, opts: TextOptions = {}): number {
    return this.slot(opts.font).font.width(text, opts.size ?? 10, opts.spacing ?? 0);
  }

  text(x: number, y: number, text: string, opts: TextOptions = {}) {
    if (!text) return;
    const size = opts.size ?? 10;
    const slot = this.slot(opts.font);
    const width = slot.font.width(text, size, opts.spacing ?? 0);
    const left = opts.align === "right" ? x - width : opts.align === "center" ? x - width / 2 : x;
    let hex = "";
    for (const ch of text) {
      const cp = ch.codePointAt(0) as number;
      const g = slot.font.glyph(cp);
      if (!slot.used.has(g)) slot.used.set(g, cp);
      hex += g.toString(16).padStart(4, "0");
    }
    this.ops(
      "BT",
      `/${slot.tag} ${f(size)} Tf`,
      `${f(opts.spacing ?? 0)} Tc`,
      `${rgb(opts.color ?? [36, 36, 38])} rg`,
      `1 0 0 1 ${f(left)} ${f(this.height - y)} Tm`,
      `<${hex}> Tj`,
      "ET"
    );
  }

  /** Lines of at most `width` points, broken at spaces (or inside a word too long for one). */
  wrap(text: string, width: number, opts: TextOptions = {}): string[] {
    const lines: string[] = [];
    for (const paragraph of text.split("\n")) {
      let line = "";
      for (const word of paragraph.split(/\s+/).filter(Boolean)) {
        const next = line ? `${line} ${word}` : word;
        if (this.measure(next, opts) <= width) {
          line = next;
          continue;
        }
        if (line) lines.push(line);
        line = word;
        while (this.measure(line, opts) > width && line.length > 1) {
          let cut = line.length - 1;
          while (cut > 1 && this.measure(line.slice(0, cut), opts) > width) cut--;
          lines.push(line.slice(0, cut));
          line = line.slice(cut);
        }
      }
      lines.push(line);
    }
    return lines;
  }

  /** The text cut to fit `width`, ending in "…" when it had to be cut. */
  fit(text: string, width: number, opts: TextOptions = {}): string {
    if (this.measure(text, opts) <= width) return text;
    let end = text.length;
    while (end > 0 && this.measure(text.slice(0, end) + "…", opts) > width) end--;
    return text.slice(0, end).trimEnd() + "…";
  }

  private path(x: number, y: number, w: number, h: number, r = 0): string {
    const X = x;
    const Y = this.height - y - h;
    const rad = Math.max(0, Math.min(r, w / 2, h / 2));
    if (!rad) return `${f(X)} ${f(Y)} ${f(w)} ${f(h)} re`;
    const k = rad * 0.5523;
    return [
      `${f(X + rad)} ${f(Y)} m`,
      `${f(X + w - rad)} ${f(Y)} l`,
      `${f(X + w - rad + k)} ${f(Y)} ${f(X + w)} ${f(Y + rad - k)} ${f(X + w)} ${f(Y + rad)} c`,
      `${f(X + w)} ${f(Y + h - rad)} l`,
      `${f(X + w)} ${f(Y + h - rad + k)} ${f(X + w - rad + k)} ${f(Y + h)} ${f(X + w - rad)} ${f(Y + h)} c`,
      `${f(X + rad)} ${f(Y + h)} l`,
      `${f(X + rad - k)} ${f(Y + h)} ${f(X)} ${f(Y + h - rad + k)} ${f(X)} ${f(Y + h - rad)} c`,
      `${f(X)} ${f(Y + rad)} l`,
      `${f(X)} ${f(Y + rad - k)} ${f(X + rad - k)} ${f(Y)} ${f(X + rad)} ${f(Y)} c`,
      "h",
    ].join("\n");
  }

  rect(x: number, y: number, w: number, h: number, o: { fill?: Rgb; stroke?: Rgb; lineWidth?: number; radius?: number }) {
    if (w <= 0 || h <= 0) return;
    const paint = o.fill && o.stroke ? "B" : o.fill ? "f" : "S";
    this.ops(
      "q",
      o.fill ? `${rgb(o.fill)} rg` : "",
      o.stroke ? `${rgb(o.stroke)} RG ${f(o.lineWidth ?? 0.75)} w` : "",
      this.path(x, y, w, h, o.radius),
      paint,
      "Q"
    );
  }

  line(x1: number, y1: number, x2: number, y2: number, o: { color?: Rgb; width?: number } = {}) {
    this.ops(
      "q",
      `${rgb(o.color ?? [229, 229, 229])} RG ${f(o.width ?? 0.75)} w`,
      `${f(x1)} ${f(this.height - y1)} m ${f(x2)} ${f(this.height - y2)} l S`,
      "Q"
    );
  }

  /** Draw inside a rounded rectangle only, for bars with rounded ends. */
  clip(x: number, y: number, w: number, h: number, radius: number, draw: () => void) {
    this.ops("q", this.path(x, y, w, h, radius), "W n");
    draw();
    this.ops("Q");
  }

  async toBlob(info: { title: string; author: string; subject?: string }): Promise<Blob> {
    const encoder = new TextEncoder();
    const chunks: Uint8Array[] = [];
    const offsets: number[] = [0];
    let size = 0;
    let next = 1;
    const put = (part: Uint8Array | string) => {
      const bytes = typeof part === "string" ? encoder.encode(part) : part;
      chunks.push(bytes);
      size += bytes.length;
    };
    const id = () => next++;
    const obj = (n: number, body: string) => {
      offsets[n] = size;
      put(`${n} 0 obj\n${body}\nendobj\n`);
    };
    const stream = async (n: number, dict: string, data: Uint8Array) => {
      const packed = await deflate(data);
      offsets[n] = size;
      put(`${n} 0 obj\n<< ${dict} /Length ${packed.length} /Filter /FlateDecode >>\nstream\n`);
      put(packed);
      put("\nendstream\nendobj\n");
    };

    put(new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37, 0x0a, 0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

    const catalog = id();
    const pagesId = id();
    const infoId = id();
    const fontIds = [...this.fonts.values()].map((slot) => ({ slot, type0: id(), cid: id(), descriptor: id(), file: id(), unicode: id() }));
    const pageIds = this.pages.map(() => ({ page: id(), content: id() }));

    obj(catalog, `<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
    obj(pagesId, `<< /Type /Pages /Kids [${pageIds.map((p) => `${p.page} 0 R`).join(" ")}] /Count ${pageIds.length} >>`);
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const zone = -now.getTimezoneOffset();
    const stamp =
      `D:${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}` +
      `${zone >= 0 ? "+" : "-"}${pad(Math.floor(Math.abs(zone) / 60))}'${pad(Math.abs(zone) % 60)}'`;
    obj(
      infoId,
      `<< /Title ${pdfString(info.title)} /Author ${pdfString(info.author)}${info.subject ? ` /Subject ${pdfString(info.subject)}` : ""} /Creator (Veritas) /Producer (Veritas) /CreationDate (${stamp}) >>`
    );

    const fontRefs = fontIds.map((x) => `/${x.slot.tag} ${x.type0} 0 R`).join(" ");
    for (let i = 0; i < this.pages.length; i++) {
      obj(
        pageIds[i].page,
        `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${f(this.width)} ${f(this.height)}] /Resources << /Font << ${fontRefs} >> >> /Contents ${pageIds[i].content} 0 R >>`
      );
      await stream(pageIds[i].content, "", encoder.encode(this.pages[i].filter(Boolean).join("\n")));
    }

    for (const { slot, type0, cid, descriptor, file, unicode } of fontIds) {
      const font = slot.font;
      const scale = 1000 / font.unitsPerEm;
      const glyphs = [...slot.used.keys()].sort((a, b) => a - b);
      const widths = glyphs.map((g) => `${g} [${Math.round(font.advance(g) * scale)}]`).join(" ");
      await stream(file, `/Length1 ${font.bytes.length}`, font.bytes);
      obj(
        descriptor,
        `<< /Type /FontDescriptor /FontName /${font.name} /Flags 32 /FontBBox [${font.bbox.map((v) => Math.round(v * scale)).join(" ")}] ` +
          `/ItalicAngle ${f(font.italicAngle)} /Ascent ${Math.round(font.ascent * scale)} /Descent ${Math.round(font.descent * scale)} ` +
          `/CapHeight ${Math.round(font.capHeight * scale)} /StemV 80 /FontFile2 ${file} 0 R >>`
      );
      obj(
        cid,
        `<< /Type /Font /Subtype /CIDFontType2 /BaseFont /${font.name} /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> ` +
          `/FontDescriptor ${descriptor} 0 R /W [${widths}] /CIDToGIDMap /Identity >>`
      );
      const pairs = glyphs.filter((g) => g !== 0).map((g) => `<${g.toString(16).padStart(4, "0")}> <${utf16Hex(slot.used.get(g) as number)}>`);
      const blocks: string[] = [];
      for (let i = 0; i < pairs.length; i += 100) {
        const part = pairs.slice(i, i + 100);
        blocks.push(`${part.length} beginbfchar\n${part.join("\n")}\nendbfchar`);
      }
      const cmap = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
        ...blocks,
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
      ].join("\n");
      await stream(unicode, "", encoder.encode(cmap));
      obj(type0, `<< /Type /Font /Subtype /Type0 /BaseFont /${font.name} /Encoding /Identity-H /DescendantFonts [${cid} 0 R] /ToUnicode ${unicode} 0 R >>`);
    }

    const xref = size;
    const lines = [`xref`, `0 ${next}`, `0000000000 65535 f `];
    for (let n = 1; n < next; n++) lines.push(`${String(offsets[n]).padStart(10, "0")} 00000 n `);
    put(lines.join("\n") + "\n");
    put(`trailer\n<< /Size ${next} /Root ${catalog} 0 R /Info ${infoId} 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    return new Blob(chunks, { type: "application/pdf" });
  }
}
