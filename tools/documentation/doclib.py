"""Helpers on python-docx: styles, inline markup, index entries (XE), fields (TOC, SEQ, INDEX, PAGE), tables,
figures, callouts."""
import re


def plain(text):
    """Text without the inline markup."""
    text = re.sub(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]", r"\1", text or "")
    return re.sub(r"\*\*|`|(?<!\w)\*|\*(?!\w)", "", text).strip()

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
TEAL = RGBColor(0x13, 0x8A, 0x72)
GREY = RGBColor(0x5B, 0x63, 0x70)
CODE = RGBColor(0x33, 0x3D, 0x4F)
BODY_FONT = "Calibri"
HEAD_FONT = "Calibri"
MONO = "Consolas"


class Doc:
    def __init__(self):
        self.d = Document()
        self.fig = 0
        self.fresh = False
        self.pending = []
        self.headings, self.captions, self.xe_log = [], [], []
        self.cur_heading = ''
        self.pages = None  # page numbers from an earlier rendering
        self.tab = 0
        self._styles()
        sec = self.d.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.2)
        sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
        self.width = 21.0 - 4.4

    # ------------------------------------------------------------------ styles
    def _styles(self):
        st = self.d.styles
        normal = st["Normal"]
        normal.font.name = BODY_FONT
        normal.font.size = Pt(10.5)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
        pf = normal.paragraph_format
        pf.space_after = Pt(6)
        pf.line_spacing = 1.15
        for level, size, before, after, color in ((1, 20, 6, 10, NAVY), (2, 14.5, 16, 6, NAVY), (3, 12, 12, 4, TEAL),
                                                  (4, 10.5, 10, 3, GREY)):
            h = st[f"Heading {level}"]
            h.font.name = HEAD_FONT
            h.font.size = Pt(size)
            h.font.bold = True
            h.font.italic = False
            h.font.color.rgb = color
            rpr = h.element.get_or_add_rPr()
            fonts = rpr.find(qn("w:rFonts"))
            if fonts is None:
                fonts = OxmlElement("w:rFonts")
                rpr.append(fonts)
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                fonts.set(qn(attr), HEAD_FONT)
            for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                if fonts.get(qn(attr)) is not None:
                    del fonts.attrib[qn(attr)]
            h.paragraph_format.space_before = Pt(before)
            h.paragraph_format.space_after = Pt(after)
            h.paragraph_format.keep_with_next = True
        title = st["Title"]
        title.font.name = HEAD_FONT
        title.font.size = Pt(40)
        title.font.color.rgb = NAVY
        title.font.bold = True
        cap = st["Caption"]
        cap.font.name = BODY_FONT
        cap.font.size = Pt(9)
        cap.font.italic = True
        cap.font.bold = False
        cap.font.color.rgb = GREY
        cap.paragraph_format.space_after = Pt(12)
        if "Code Char" not in [s.name for s in st]:
            cs = st.add_style("Code Char", WD_STYLE_TYPE.CHARACTER)
            cs.font.name = MONO
            cs.font.size = Pt(9)
            cs.font.color.rgb = CODE
        if "Code Block" not in [s.name for s in st]:
            cb = st.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
            cb.base_style = st["Normal"]
            cb.font.name = MONO
            cb.font.size = Pt(8.5)
            cb.font.color.rgb = CODE
            cb.paragraph_format.space_after = Pt(0)
            cb.paragraph_format.line_spacing = 1.0
        if "Formula" not in [s.name for s in st]:
            fm = st.add_style("Formula", WD_STYLE_TYPE.PARAGRAPH)
            fm.base_style = st["Normal"]
            fm.font.name = "Cambria Math"
            fm.font.size = Pt(11)
            fm.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            fm.paragraph_format.space_before = Pt(4)
            fm.paragraph_format.space_after = Pt(8)
        for name in ("List Bullet", "List Number"):
            s = st[name]
            s.font.name = BODY_FONT
            s.font.size = Pt(10.5)
            s.paragraph_format.space_after = Pt(3)

    # ------------------------------------------------------------------ fields
    @staticmethod
    def _fld(paragraph, instr, result="", bold=False, size=None):
        def run_with(tag, **attrs):
            r = paragraph.add_run()
            el = OxmlElement(tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            r._r.append(el)
            return r
        run_with("w:fldChar", **{"w:fldCharType": "begin"})
        r = paragraph.add_run()
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = f" {instr} "
        r._r.append(it)
        run_with("w:fldChar", **{"w:fldCharType": "separate"})
        res = paragraph.add_run(result)
        res.bold = bold
        if size:
            res.font.size = size
        run_with("w:fldChar", **{"w:fldCharType": "end"})
        return res

    def xe(self, paragraph, entry, shown=None):
        entry = entry.replace('"', "'")
        self.xe_log.append((entry, plain(shown or entry), len(self.headings) - 1))
        r = paragraph.add_run()
        b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin"); r._r.append(b)
        r2 = paragraph.add_run()
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f' XE "{entry}" '
        r2._r.append(it)
        r3 = paragraph.add_run()
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end"); r3._r.append(e)

    # ------------------------------------------------------------------ inline markup
    TOKEN = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[\[[^\]]+\]\])")

    def inline(self, p, text, size=None, color=None, bold=False):
        for part in self.TOKEN.split(text):
            if not part:
                continue
            if part.startswith("**"):
                r = p.add_run(part[2:-2]); r.bold = True
            elif part.startswith("`"):
                r = p.add_run(part[1:-1], style="Code Char")
                if size:
                    r.font.size = Pt(max(7, size.pt - 1))
                if bold:
                    r.bold = True
                continue
            elif part.startswith("[["):
                inner = part[2:-2]
                shown, _, entry = inner.partition("|")
                r = p.add_run(shown)
                if bold:
                    r.bold = True
                if size:
                    r.font.size = size
                if color:
                    r.font.color.rgb = color
                self.xe(p, entry or shown, shown)
                continue
            elif part.startswith("*") and len(part) > 2:
                r = p.add_run(part[1:-1]); r.italic = True
            else:
                r = p.add_run(part)
            if size:
                r.font.size = size
            if color:
                r.font.color.rgb = color
            if bold:
                r.bold = True
        return p

    # ------------------------------------------------------------------ blocks
    def h(self, level, text, index=None, page_break=False):
        if level == 1:
            self.flush()
        brk = page_break and not getattr(self, "fresh", False)
        self.fresh = False
        p = self.d.add_heading("", level)
        if brk:
            p.paragraph_format.page_break_before = True
        self.cur_heading = plain(text)
        self.headings.append((level, self.cur_heading))
        self.inline(p, text)
        if index:
            self.xe(p, index, self.cur_heading)
        return p

    def p(self, text, style=None, align=None, size=None, color=None, after=None, before=None, keep=False, italic=False):
        self.fresh = False
        p = self.d.add_paragraph(style=style)
        self.inline(p, text, Pt(size) if size else None, color)
        if italic:
            for r in p.runs:
                r.italic = True
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "right":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if after is not None:
            p.paragraph_format.space_after = Pt(after)
        if before is not None:
            p.paragraph_format.space_before = Pt(before)
        if keep:
            p.paragraph_format.keep_with_next = True
        return p

    def bullets(self, items, numbered=False):
        self.fresh = False
        for n, item in enumerate(items, start=1):
            if numbered:  # numbered by hand, so every list starts at 1
                p = self.d.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.9)
                p.paragraph_format.first_line_indent = Cm(-0.6)
                p.paragraph_format.space_after = Pt(3)
                r = p.add_run(f"{n}.	"); r.bold = True
                p.paragraph_format.tab_stops.add_tab_stop(Cm(0.9))
            else:
                p = self.d.add_paragraph(style="List Bullet")
            if isinstance(item, tuple):  # (bold lead, rest)
                r = p.add_run(item[0]); r.bold = True
                self.inline(p, " " + item[1])
            else:
                self.inline(p, item)

    def formula(self, text, note=None):
        self.fresh = False
        p = self.d.add_paragraph(style="Formula")
        p.add_run(text)
        if note:
            r = p.add_run("     " + note)
            r.font.name = BODY_FONT
            r.font.size = Pt(9)
            r.font.color.rgb = GREY
        return p

    def code(self, lines):
        self.fresh = False
        for i, line in enumerate(lines):
            p = self.d.add_paragraph(style="Code Block")
            p.add_run(line)
            self._shade(p, "F3F4F6")
            p.paragraph_format.left_indent = Cm(0.3)
            if i == len(lines) - 1:
                p.paragraph_format.space_after = Pt(8)

    def callout(self, title, text, fill="EAF2FB", edge="3B6FD8"):
        self.fresh = False
        p = self.d.add_paragraph()
        self._shade(p, fill)
        self._border(p, edge)
        p.paragraph_format.left_indent = Cm(0.25)
        p.paragraph_format.right_indent = Cm(0.25)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(10)
        r = p.add_run(title + "  ")
        r.bold = True
        r.font.color.rgb = NAVY
        self.inline(p, text)
        return p

    @staticmethod
    def _shade(p, fill):
        ppr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
        ppr.insert_element_before(shd, "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")

    @staticmethod
    def _border(p, color):
        ppr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        for side in ("top", "left", "bottom", "right"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "6"); el.set(qn("w:space"), "4")
            el.set(qn("w:color"), color if side == "left" else "D1D5DB")
            if side == "left":
                el.set(qn("w:sz"), "24")
            bdr.append(el)
        ppr.insert_element_before(bdr, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")

    def page_break(self):
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def _section(self, landscape):
        from docx.enum.section import WD_ORIENT
        sec = self.d.add_section(WD_SECTION.NEW_PAGE)
        sec.different_first_page_header_footer = False
        if landscape:
            sec.orientation = WD_ORIENT.LANDSCAPE
            sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
            sec.left_margin = sec.right_margin = Cm(2.0)
            sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.6)
        else:
            sec.orientation = WD_ORIENT.PORTRAIT
            sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
            sec.left_margin = sec.right_margin = Cm(2.2)
            sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
        return sec

    def figure(self, path, caption, width_cm=None, index=None, landscape=False):
        if landscape:  # kept for a landscape page at the end of the chapter
            self.pending.append((path, caption, index))
            return None
        return self._figure(path, caption, width_cm, index)

    def flush(self):
        """The chapter's landscape figures, one page each, then back to portrait."""
        if not self.pending:
            return
        from PIL import Image
        self._section(True)
        for n, (path, caption, index) in enumerate(self.pending):
            if n:
                self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            w, h = Image.open(path).size
            self._figure(path, caption, min(25.6, 15.0 * w / h), index)
        self.pending = []
        self._section(False)
        self.fresh = True

    def _figure(self, path, caption, width_cm=None, index=None):
        self.fresh = False
        width_cm = width_cm or self.width
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.add_run().add_picture(path, width=Cm(width_cm))
        self.fig += 1
        c = self.d.add_paragraph(style="Caption")
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.add_run("Figure ")
        self._fld(c, "SEQ Figure \\* ARABIC", str(self.fig))
        c.add_run(": ")
        self.captions.append(("Figure", self.fig, plain(caption)))
        self.inline(c, caption)
        if index:
            self.xe(c, index, f"Figure {self.fig}:")
        return self.fig

    def table(self, headers, rows, widths, size=9, mono_cols=(), header_fill="1F3A5F", zebra=True, caption=None,
              bold_first=False, header=True):
        self.fresh = False
        if caption:
            self.tab += 1
            c = self.d.add_paragraph(style="Caption")
            c.paragraph_format.keep_with_next = True
            c.paragraph_format.space_after = Pt(3)
            c.add_run("Table ")
            self._fld(c, "SEQ Table \\* ARABIC", str(self.tab))
            c.add_run(": ")
            self.captions.append(("Table", self.tab, plain(caption)))
            self.inline(c, caption)
        t = self.d.add_table(rows=1, cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        self._table_borders(t)
        hdr = t.rows[0]
        self._repeat_header(hdr)
        for i, text in enumerate(headers):
            cell = hdr.cells[i]
            cell.width = Cm(widths[i])
            self._cell_shade(cell, header_fill)
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(0)
            r = par.add_run(text)
            r.bold = True
            r.font.size = Pt(size)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        for n, row in enumerate(rows):
            cells = t.add_row().cells
            for i, text in enumerate(row):
                cell = cells[i]
                cell.width = Cm(widths[i])
                if zebra and n % 2 == 1:
                    self._cell_shade(cell, "F5F7FA")
                par = cell.paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                par.paragraph_format.line_spacing = 1.0
                text = "" if text is None else str(text)
                if i in mono_cols:
                    r = par.add_run(text)
                    r.font.name = MONO
                    r.font.size = Pt(size - 1)
                    r.font.color.rgb = CODE
                else:
                    self.inline(par, text, Pt(size), bold=(bold_first and i == 0))
        if not header:
            t._tbl.remove(t.rows[0]._tr)
        # widths on the grid too
        grid = t._tbl.tblGrid
        for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
            gc.set(qn("w:w"), str(int(widths[i] * 567)))
        self.d.add_paragraph().paragraph_format.space_after = Pt(4)
        return t

    @staticmethod
    def _cell_shade(cell, fill):
        tcpr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
        tcpr.append(shd)

    @staticmethod
    def _repeat_header(row):
        trpr = row._tr.get_or_add_trPr()
        el = OxmlElement("w:tblHeader")
        el.set(qn("w:val"), "true")
        trpr.append(el)

    @staticmethod
    def _table_borders(t):
        tblpr = t._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4"); el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "D1D5DB")
            borders.append(el)
        tblpr.insert_element_before(borders, "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption",
                                    "w:tblDescription", "w:tblPrChange")
        mar = OxmlElement("w:tblCellMar")
        for side, w in (("top", 30), ("left", 80), ("bottom", 30), ("right", 80)):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:w"), str(w)); el.set(qn("w:type"), "dxa")
            mar.append(el)
        tblpr.insert_element_before(mar, "w:tblLook", "w:tblCaption", "w:tblDescription", "w:tblPrChange")

    def _field_block(self, instr, lines):
        """A field whose result is several paragraphs: lines = [(text, page, indent_cm, bold)]."""
        from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER

        def fc(run, kind):
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind); run._r.append(el)
        first = None
        last = None
        for i, (text, page, indent, bold) in enumerate(lines or [("Right-click and choose Update Field.", "", 0, False)]):
            p = self.d.add_paragraph()
            pf = p.paragraph_format
            pf.space_after = Pt(1.5 if indent else 3)
            pf.space_before = Pt(0 if indent else 3)
            pf.left_indent = Cm(indent)
            pf.tab_stops.add_tab_stop(Cm(self.width - 0.05), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            if i == 0:
                fc(p.add_run(), "begin")
                r = p.add_run(); it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve")
                it.text = f" {instr} "; r._r.append(it)
                fc(p.add_run(), "separate")
            r = p.add_run(text + ("\t" + str(page) if page != "" else ""))
            r.font.size = Pt(10 if not indent else 9.5)
            r.bold = bold
            last = p
        fc(last.add_run(), "end")

    def toc(self, kind="toc"):
        self.fresh = False
        pages = self.pages or {}
        if kind == "toc":
            lines = [(text, pages.get("h", {}).get(n, 0), 0.6 * (level - 1), level == 1)
                     for n, (level, text) in enumerate(pages.get("headings", self.headings)) if level <= 2]
            self._field_block('TOC \\o "1-2" \\h \\z \\u', lines)
        else:
            lines = [(f"{k} {n}: {text}", pages.get("c", {}).get(f"{k} {n}", 0), 0, False)
                     for k, n, text in pages.get("captions", []) if k == kind]
            self._field_block(f'TOC \\h \\z \\c "{kind}"', lines)

    def index_field(self):
        pages = (self.pages or {}).get("index", {})
        lines = []
        letter = ""
        for entry in sorted(pages, key=lambda e: e.lower()):
            main, _, sub = entry.partition(":")
            if main[:1].upper() != letter:
                letter = main[:1].upper()
                lines.append((letter, "", 0, True))
            nums = ", ".join(str(n) for n in pages[entry])
            if sub:
                if not any(l[0] == main for l in lines[-10:]):
                    lines.append((main, "", 0.3, False))
                lines.append((sub, nums, 0.9, False))
            else:
                lines.append((main, nums, 0.3, False))
        self._field_block('INDEX \\e "\t" \\h "A" \\z "2057"', lines)

    def header_footer(self, title):
        sec = self.d.sections[-1]
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r = hp.add_run(title)
        r.font.size = Pt(8.5)
        r.font.color.rgb = GREY
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run("Page ")
        r.font.size = Pt(8.5); r.font.color.rgb = GREY
        x = self._fld(fp, "PAGE", "1"); x.font.size = Pt(8.5); x.font.color.rgb = GREY
        r = fp.add_run(" of ")
        r.font.size = Pt(8.5); r.font.color.rgb = GREY
        x = self._fld(fp, "NUMPAGES", "1"); x.font.size = Pt(8.5); x.font.color.rgb = GREY

    def save(self, path):
        self.flush()
        settings = self.d.settings.element
        upd = OxmlElement("w:updateFields"); upd.set(qn("w:val"), "true")
        settings.insert_element_before(upd, "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat",
                                       "w:docVars", "w:rsids", "m:mathPr", "w:attachedSchema", "w:themeFontLang",
                                       "w:clrSchemeMapping", "w:doNotIncludeSubdocsInStats",
                                       "w:doNotAutoCompressPictures", "w:forceUpgrade", "w:captions",
                                       "w:readModeInkLockDown", "w:smartTagType", "sl:schemaLibrary",
                                       "w:shapeDefaults", "w:doNotEmbedSmartTags", "w:decimalSymbol",
                                       "w:listSeparator")
        zoom = settings.find(qn("w:zoom"))
        if zoom is not None and zoom.get(qn("w:percent")) is None:
            zoom.set(qn("w:percent"), "100")
        self.d.save(path)
