# WisprLearn — Wispr Flow auto-learn for Sublime Text

> **Unofficial.** Not affiliated with or endorsed by Wispr. By default it only **reads** Wispr Flow's local database and writes learned words to a CSV that you import through Wispr's own **Dictionary → Import**. An optional `"database"` mode writes straight into Wispr's database — Wispr does not support that, so avoid it unless you understand the risk.

[Wispr Flow](https://wisprflow.ai) learns new words when you correct its dictation, but only in apps that expose their text through the OS accessibility APIs (Notepad, browsers, VS Code…). **Sublime Text draws its own text and exposes no accessibility tree**, so Wispr can paste into it but never sees your corrections.

WisprLearn closes that gap from inside Sublime.

## How it works

1. When something is pasted into Sublime, the plugin checks Wispr's local `History` table to see whether that text is a recent Wispr dictation. Ordinary pastes are ignored.
2. It tracks the pasted region (invisible region that Sublime keeps up to date while you edit).
3. After you stop editing that region for a few seconds, it diffs the original dictation against your edited text, word by word.
4. Replacements that look like recognition errors (spelling/phonetic similarity, accent fixes, split words merged — e.g. `sacal → cecal`, `leptomeningeo → leptomeníngeo`, `neuro forme → Neuroform`) are saved:
   - **`csv` mode (default):** appended to `Documents\WisprLearn-dicionario.csv`, one word per line. Import it in Wispr (**Dictionary → Import**) whenever you like; entries already in your dictionary are skipped, so you can keep appending and re-importing. Imported words sync to your account normally and need no restart.
   - **`database` mode (unsupported):** inserted into Wispr's `Dictionary` table in the same format as Wispr's own auto-learn (`source = 'user_edits'`). Words appear after Wispr restarts. Wispr support warns that a database Flow considers corrupted is reset on restart, losing local-only content (history, notes, meetings), and that directly-written rows may not survive a resync.

Only the corrected word is written (single column = vocabulary). It deliberately does **not** write `misspelling,correction` rules, because a rule like `Real,Realce` would replace *every* "Real".

What it **ignores**: rewritten sentences (too many words changed), unrelated word swaps (`direito → esquerdo`), numbers, pure capitalization changes, words only added or deleted, words shorter than 3 characters, and words already in the dictionary.

Everything runs locally. Nothing is sent over the network.

## Limitations

- Not real-time: in `csv` mode words reach Wispr when you import the file; in `database` mode, after Wispr restarts. (Wispr has no API for adding dictionary words from outside the app yet — requested.)
- The CSV can keep growing and be re-imported as often as you like: Wispr skips entries already in your dictionary, and the 1,000-entry import cap only counts genuinely new words. Re-importing also restores entries that were deleted (e.g. by a resync). The real limit is **3 MB per file**; the status bar warns at 2.5 MB, then run **Wispr Learn: Arquivar CSV** to start a fresh file.
- Tested on **Windows** with Sublime Text 4 and Wispr Flow desktop. macOS path is a guess — set `db_path` if needed.
- Single-cursor pastes only. Relies on Wispr's internal `History` table, which can change without notice.

## Install

1. In Sublime: **Preferences → Browse Packages…**
2. Copy this folder there as `WisprLearn` (or `git clone` it there).
3. Check the console (**Ctrl+`**) for `reloading plugin WisprLearn.wispr_learn`.

Default database location:

- Windows: `%APPDATA%\Wispr Flow\flow.sqlite`
- macOS (untested): `~/Library/Application Support/Wispr Flow/flow.sqlite`

## Usage

Just dictate with Wispr into Sublime and fix words as usual. About 12 s after you move the cursor away from the dictated text, the status bar shows:

```
Wispr Learn: «cecal» adicionada ao CSV (14 palavras)
```

Then, now and then: Wispr → **Dictionary → Import** → pick `WisprLearn-dicionario.csv`.

Command palette (**Ctrl+Shift+P**):

| Command | What it does |
|---|---|
| Wispr Learn: Abrir CSV de palavras | Open the CSV to review/edit before importing |
| Wispr Learn: Arquivar CSV e começar um novo | Rename the current CSV with a date and start a new one (only needed near 3 MB) |
| Wispr Learn: Desfazer última palavra aprendida | Undo the last learned word |
| Wispr Learn: Ver log | Open the log of everything learned or ignored, and why |
| Wispr Learn: Ativar/Desativar | Turn learning on/off |

## Settings

**Preferences → Package Settings** or create `Packages/User/WisprLearn.sublime-settings`:

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Turn learning on/off |
| `mode` | `"csv"` | `"csv"` (safe, import manually) or `"database"` (unsupported direct write) |
| `csv_path` | `""` | CSV location (empty = `Documents\WisprLearn-dicionario.csv`) |
| `csv_warn_mb` | `2.5` | Warn when the CSV reaches this size (Wispr limit: 3 MB per file) |
| `csv_backup` | `true` | In `database` mode, also append each word to the CSV as a backup you can import if a resync drops them |
| `dry_run` | `false` | Only log what would be learned, never write |
| `db_path` | `""` | Path to `flow.sqlite` (empty = default location) |
| `min_similarity` | `0.55` | How similar the corrected word must be to the dictated one (0–1) |
| `max_change_ratio` | `0.4` | Above this fraction of unrelated changes, the edit counts as a rewrite |
| `idle_seconds` | `12` | Seconds without editing before analysing |
| `max_track_seconds` | `600` | How long a dictation keeps being watched |
| `min_length` | `3` | Minimum length of a learned word |
| `debug` | `false` | Print messages to the Sublime console |

Tip: try `"dry_run": true` for a day and read the log before letting it write.

## Backup / restore (database mode)

Wispr keeps daily backups in `%APPDATA%\Wispr Flow\backups\`. To restore manually, quit Wispr completely (tray icon → Quit) and replace `flow.sqlite` with a backup.

## Why not fix it upstream?

The ideal fix belongs in Wispr: an official way for editors to add dictionary entries (local API, CLI or `wispr://` URL) and live reload of the dictionary. This plugin is a workaround until then.

---

## Português (resumo)

Plugin **não oficial** que faz o auto-learn do Wispr Flow funcionar no Sublime Text. O Sublime não expõe o texto à acessibilidade do sistema, então o Wispr não vê suas correções. O plugin detecta os ditados do Wispr (lendo a tabela `History`), compara com o que você corrigiu e salva as palavras corrigidas em `Documentos\WisprLearn-dicionario.csv`. De tempos em tempos, importe o arquivo no Wispr em **Dictionary → Import**. O modo `"database"` (gravar direto no banco do Wispr) existe, mas não é suportado pelo Wispr.

## License

MIT
