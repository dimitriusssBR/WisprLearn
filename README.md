# WisprLearn — Wispr Flow auto-learn for Sublime Text

> **Unofficial.** Not affiliated with or endorsed by Wispr. This plugin writes directly to Wispr Flow's local database. It may break with any Wispr update. **Back up your database before using it.**

[Wispr Flow](https://wisprflow.ai) learns new words when you correct its dictation, but only in apps that expose their text through the OS accessibility APIs (Notepad, browsers, VS Code…). **Sublime Text draws its own text and exposes no accessibility tree**, so Wispr can paste into it but never sees your corrections.

WisprLearn closes that gap from inside Sublime.

## How it works

1. When something is pasted into Sublime, the plugin checks Wispr's local `History` table to see whether that text is a recent Wispr dictation. Ordinary pastes are ignored.
2. It tracks the pasted region (invisible region that Sublime keeps up to date while you edit).
3. After you stop editing that region for a few seconds, it diffs the original dictation against your edited text, word by word.
4. Replacements that look like recognition errors (spelling/phonetic similarity, accent fixes, split words merged — e.g. `sacal → cecal`, `leptomeningeo → leptomeníngeo`, `neuro forme → Neuroform`) are added to Wispr's `Dictionary` table in the same format Wispr's own auto-learn uses (`source = 'user_edits'`), so they show up with the auto-learn badge.

What it **ignores**: rewritten sentences (too many words changed), unrelated word swaps (`direito → esquerdo`), numbers, pure capitalization changes, words only added or deleted, words shorter than 3 characters, and words already in the dictionary.

Everything runs locally. Nothing is sent over the network.

## Limitations

- **New words take effect after Wispr restarts.** Wispr keeps the dictionary in memory and does not reload it when another program writes to the database. The words are saved immediately and appear (with the auto-learn badge) the next time Wispr starts.
- Tested on **Windows** with Sublime Text 4 (Python 3.8 / 3.14 plugin host) and Wispr Flow desktop. macOS path is a guess — set `db_path` if needed.
- Single-cursor pastes only.
- Database schema is Wispr's internal format and can change without notice.

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
Wispr Learn: aprendeu «cecal» (ditado: «sacal»)
```

Command palette (**Ctrl+Shift+P**):

| Command | What it does |
|---|---|
| Wispr Learn: Desfazer última palavra aprendida | Undo the last learned word (soft-delete, same as Wispr) |
| Wispr Learn: Ver log | Open the log of everything learned or ignored, and why |
| Wispr Learn: Ativar/Desativar | Turn learning on/off |

## Settings

**Preferences → Package Settings** or create `Packages/User/WisprLearn.sublime-settings`:

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Turn learning on/off |
| `dry_run` | `false` | Only log what would be learned, never write |
| `db_path` | `""` | Path to `flow.sqlite` (empty = default location) |
| `min_similarity` | `0.55` | How similar the corrected word must be to the dictated one (0–1) |
| `max_change_ratio` | `0.4` | Above this fraction of unrelated changes, the edit counts as a rewrite |
| `idle_seconds` | `12` | Seconds without editing before analysing |
| `max_track_seconds` | `600` | How long a dictation keeps being watched |
| `min_length` | `3` | Minimum length of a learned word |
| `debug` | `false` | Print messages to the Sublime console |

Tip: try `"dry_run": true` for a day and read the log before letting it write.

## Backup / restore

Wispr keeps daily backups in `%APPDATA%\Wispr Flow\backups\`. To restore manually, quit Wispr completely (tray icon → Quit) and replace `flow.sqlite` with a backup.

## Why not fix it upstream?

The ideal fix belongs in Wispr: an official way for editors to add dictionary entries (local API, CLI or `wispr://` URL) and live reload of the dictionary. This plugin is a workaround until then.

---

## Português (resumo)

Plugin **não oficial** que faz o auto-learn do Wispr Flow funcionar no Sublime Text. O Sublime não expõe o texto à acessibilidade do sistema, então o Wispr não vê suas correções. O plugin detecta os ditados do Wispr (pela tabela `History`), compara com o que você corrigiu e grava as palavras no dicionário do Wispr no mesmo formato do auto-learn. As palavras passam a valer depois de reiniciar o Wispr. Use por sua conta e risco e faça backup do `flow.sqlite`.

## License

MIT
