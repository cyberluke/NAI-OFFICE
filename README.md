<p align="center">
  <img src="assets/nai-office.png" alt="NAI OFFICE" width="760">
</p>

<h1 align="center">NAI OFFICE</h1>

<p align="center">
  A modern office suite built on LibreOffice — with a 2027-era Writer and AI that writes with you.
</p>

<div align="center">

[Download](#install) · [Features](#features) · [Build](#building-from-source) · [Donate](https://revolut.me/lukalita) · [License](#license)

</div>

NAI OFFICE is a complete office suite: **Writer**, **Calc**, **Impress**, **Draw**, **Base**
and **Math**, compatible with Microsoft Office and OpenDocument formats. It is built on the
LibreOffice engine and ships a redesigned Writer, a dark interface, and an AI assistant that
works inside your documents.

---

## Install

**Windows x86-64** — [download the latest installer](https://nanotrik.ai/office/) or take it from the [latest GitHub release](https://github.com/cyberluke/NAI-OFFICE/releases/latest). It installs to `C:\Program Files\NAI_OFFICE 27`
and includes the AI assistant and its Chromium runtime, so there is nothing else to set up.

**Linux and macOS** — build from source with the instructions below.

---

## Features

### Writer 2027

A redesigned writing environment on the same standards-based document format — no
conversion, no proprietary container.

- **Typography Browser** — curated font and typography controls built for large, high-DPI displays.
- **Type System** — pick typographic roles; they are applied as real Writer styles.
- **Document Kits and Editorial Blocks** — title pages, sidebars, pull quotes and editorial
  layouts you compose into your document as native Writer structures.
- **Style Gallery** — browse and apply styles with live previews.
- **Digital canvas** — a workspace-around-page view made for 4K and OLED screens.
- **Web publication export** — publish your document as semantic HTML and CSS.
- **Preflight** — catch publication problems before you export, using the same rules the
  exporter applies.

### NAI Assistant

An AI assistant that lives in the sidebar and understands the document you are editing.

- Writer, Calc, Draw and Impress support.
- Reads and edits real content: text, styles, formatting, images, navigation.
- Spreadsheet functions `=PROMPT()` and `=PYTHON()`.
- Bring your own AI provider — configure it in the assistant settings.

### Creator Studio

**Your AI co-writer does not just autocomplete. It performs.**

ChatGPT is helping you write. Fine. Every assistant can suggest the next sentence.
Creator Studio puts a *writer's room* inside your document — and then it hires a critic
with a taste for blood.

- **It types into the live document.** Not a chat bubble, not a preview pane: the agent
  writes into your open Writer document, paragraph by paragraph, while you watch. Edit
  beside it. Take the wheel mid-sentence.
- **Your story stays yours.** Outline, characters, scene notes and continuity live in a
  structured Author IR that is two-way synced with the document. Close the file, reopen
  it, and the studio still remembers who is lying to whom.
- **You direct. It drafts.** Pause the stream, resume it, restyle the page, drop in an
  image, or hand a stubborn paragraph to a second agent for a rewrite — without stopping
  the session. One undo step per chapter, so a bad idea is exactly one Ctrl+Z away.
- **Meet the Adversarial Joker Agent (AJA).** From the third chapter onward, a second
  agent reads over your shoulder and plays the reader who *wants to spoil the ending*: it
  tries to guess **who the murderer is**. One accusation per chapter. If AJA is right, the
  draft is dead — you or your AI Writer Agent rewrite that chapter (or the whole book)
  until the reveal survives a mind that is actively hunting it.

  Write a mystery that cannot be guessed. Or at least one that survives the joker.

> **Kind Reminder:** NAI OFFICE Writer 2027 does not support "writer's block".

### Interface

- Dark mode by default, with dark-mode-correct colors across every application.
- Writer 2027 toolbars are available in all applications.
- High-DPI layout tuned for 4K displays.
- Multiple icon themes, including the AI icon set.

### Platform

- Windows x86-64 installers with every runtime dependency bundled.
- AVX2-optimized Windows builds.
- UI languages: English, Czech, Slovak, Vietnamese and Qt translations.

---

## Building from source

NAI OFFICE uses the LibreOffice build system.

```sh
./autogen.sh --help          # list configure options

./configure \
  --enable-officelabs-ai \
  --with-cef=<path-to-cef-distribution> \
  --with-package-format=msi \
  --enable-python=internal \
  --with-lang="cs en-US qtz sk vi" \
  --enable-naioffice-cpu-opt

make                         # build the suite
make instsetoo               # build the installers
```

Installers are produced in `workdir/installation/`.

### Layout

| Path | Contents |
|---|---|
| `sw/`, `sc/`, `sd/` | Writer, Calc, Draw/Impress |
| `svx/` | shared drawing code and Writer 2027 UI and catalogs |
| `vcl/`, `framework/`, `sfx2/` | toolkit, UNO framework, application framework |
| `officelabs/` | CEF integration, sidebar host and the bundled AI extension |
| `officelabs/writeragent/` | the AI extension: tools, MCP server and Creator Studio |
| `instsetoo_native/`, `scp2/` | installer packaging and file lists |
| `writer2027/` | Writer 2027 client stack, tests and build drivers |

---

## ❤️ Support Independent Development

NAI OFFICE is independently developed and open source.

If you enjoy my projects and would like to support their continued development, voluntary donations are always appreciated.

[☕ Donate via Revolut](https://revolut.me/lukalita)

<a href="https://revolut.me/lukalita">
  <img src="assets/revolut-qr.png" width="160" alt="Scan to donate via Revolut">
</a>

Scan the QR code or use the link above to make a one-time donation.

Every contribution helps. Thank you for your support! 🧪

---

## License

NAI OFFICE is distributed under the **Mozilla Public License 2.0**, with portions under the
**LGPLv3**. See [`COPYING.MPL`](COPYING.MPL), [`COPYING`](COPYING) and
[`COPYING.LGPL`](COPYING.LGPL).

It is derived from LibreOffice and OpenOffice.org, and includes third-party components and
icon sets listed with their licenses in the source tree and in
[`THIRD_PARTY_ICONS.md`](THIRD_PARTY_ICONS.md).

"LibreOffice" and "The Document Foundation" are trademarks of their respective owners.
