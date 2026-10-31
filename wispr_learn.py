# -*- coding: utf-8 -*-
"""
WisprLearn - ensina o dicionario do Wispr Flow com as correcoes feitas no Sublime.

Fluxo:
  1. Detecta um "paste" no Sublime.
  2. Confere na tabela History do Wispr se aquele texto e um ditado recente
     (colas que nao vieram do Wispr sao ignoradas).
  3. Acompanha o trecho colado (regiao invisivel que o Sublime ajusta sozinho).
  4. Quando voce para de mexer no trecho, compara palavra a palavra com o
     original e grava no Dictionary do Wispr as trocas que parecem erro de
     reconhecimento (mesmo formato do auto-learn: source = 'user_edits').
"""
import sublime
import sublime_plugin

import csv
import datetime
import difflib
import os
import re
import sys
import threading
import time
import traceback
import unicodedata
import uuid

try:
    import sqlite3
    SQLITE_ERROR = None
except Exception as _e:  # pragma: no cover
    sqlite3 = None
    SQLITE_ERROR = repr(_e)

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(PKG_DIR, "wispr_learn.log")
STATUS_PATH = os.path.join(PKG_DIR, "wispr_learn_status.txt")
TEAM = "00000000-0000-0000-0000-000000000000"
WORD_RE = re.compile(r"\w+(?:[-'’]\w+)*", re.UNICODE)
PASTE_COMMANDS = ("paste", "paste_and_indent")

TRACKED = {}          # view_id -> [Track]
PENDING_PASTE = {}    # view_id -> (size_before, sel_begin, sel_size)
USED_HISTORY = set()  # transcriptEntityId ja associados a um paste
LAST_LEARNED = []     # pilha de (id, action, phrase, observed)
_DB_LOCK = threading.Lock()
_GEN = [0]            # geracao do loop de tick (evita loops duplicados no reload)


# ---------------------------------------------------------------- utilidades
def settings():
    return sublime.load_settings("WisprLearn.sublime-settings")


def opt(key, default):
    try:
        v = settings().get(key)
    except Exception:
        v = None
    return default if v is None else v


def db_path():
    p = opt("db_path", "")
    if p:
        return os.path.expandvars(os.path.expanduser(p))
    if sys.platform == "darwin":  # nao testado no macOS: ajuste "db_path" se necessario
        return os.path.expanduser("~/Library/Application Support/Wispr Flow/flow.sqlite")
    return os.path.join(os.environ.get("APPDATA", ""), "Wispr Flow", "flow.sqlite")


def log(msg):
    line = "%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    if opt("debug", False):
        print("[WisprLearn] " + msg)


def status(msg):
    sublime.status_message("Wispr Learn: " + msg)


def wispr_ts(dt=None):
    """Formato usado pelo Wispr: '2026-10-31 00:32:30.209 +00:00' (UTC)."""
    dt = dt or datetime.datetime.utcnow()
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + "%03d +00:00" % (dt.microsecond // 1000)


def connect():
    con = sqlite3.connect(db_path(), timeout=10)
    con.execute("PRAGMA busy_timeout=10000")
    return con


def norm_space(s):
    return " ".join((s or "").split())


def fold(s):
    """minusculas e sem acentos"""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def phonetic(s):
    """Chave fonetica simples para portugues (sacal ~ cecal, embolisado ~ embolizado)."""
    s = (s or "").lower().replace("ç", "s")
    s = fold(s).replace(" ", "").replace("-", "")
    for a, b in (("ss", "s"), ("sc", "s"), ("xc", "s"), ("ch", "x"), ("sh", "x"),
                 ("lh", "li"), ("nh", "ni"), ("ph", "f"), ("th", "t"), ("qu", "k"),
                 ("gu", "g"), ("y", "i"), ("w", "v")):
        s = s.replace(a, b)
    s = re.sub(r"c(?=[ei])", "s", s)
    s = s.replace("c", "k").replace("z", "s").replace("h", "")
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def similarity(old, new):
    a, b = fold(old).replace(" ", ""), fold(new).replace(" ", "")
    r1 = difflib.SequenceMatcher(None, a, b).ratio()
    r2 = difflib.SequenceMatcher(None, phonetic(old), phonetic(new)).ratio()
    return max(r1, r2)


def is_word_char(c):
    return c.isalnum() or c in "-_'’"


# ------------------------------------------------------------ analise do diff
def find_corrections(original, edited, min_sim=0.55, max_ratio=0.4, min_len=3):
    """Retorna ([(phrase_nova, ditado, similaridade)], motivo_se_ignorado)."""
    a = WORD_RE.findall(original)
    b = WORD_RE.findall(edited)
    if not a or not b:
        return [], "trecho vazio"
    sm = difflib.SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b],
                                 autojunk=False)
    ops = sm.get_opcodes()
    out = []
    other_changes = 0  # mudancas que NAO parecem correcao de reconhecimento
    skipped = []
    for t, i1, i2, j1, j2 in ops:
        if t == "equal":
            continue
        size = max(i2 - i1, j2 - j1)
        if t != "replace":  # palavras so inseridas ou so apagadas nao ensinam nada
            other_changes += size
            continue
        old, new = a[i1:i2], b[j1:j2]
        o, n = " ".join(old), " ".join(new)
        if len(old) > 3 or len(new) > 3:
            other_changes += size
            continue
        if len(n) < min_len or any(ch.isdigit() for ch in n):
            other_changes += size
            continue
        sim = 1.0 if fold(o) == fold(n) else similarity(o, n)  # so acento = 1.0
        if sim < min_sim:
            other_changes += size
            skipped.append("ignorado (pouco parecido %.2f): %r -> %r" % (sim, o, n))
            continue
        out.append((n, o, sim))
    if len(a) >= 5 and float(other_changes) / len(a) > max_ratio:
        return [], "reescrita (%d de %d palavras mudaram)" % (other_changes, len(a))
    for s in skipped:
        log(s)
    return out, None


# ------------------------------------------------------------ banco do Wispr
def find_history(text, since_epoch):
    since = wispr_ts(datetime.datetime.utcfromtimestamp(since_epoch - 600))
    con = connect()
    try:
        rows = con.execute(
            "SELECT transcriptEntityId, pastedText, formattedText FROM History "
            "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 15", (since,)).fetchall()
    finally:
        con.close()
    target = norm_space(text)
    for hid, pasted, formatted in rows:
        if hid in USED_HISTORY:
            continue
        for cand in (pasted, formatted):
            if cand and norm_space(cand) == target:
                return hid
    return None


def learn_word(phrase, observed):
    now = wispr_ts()
    with _DB_LOCK:
        con = connect()
        try:
            with con:
                active = con.execute(
                    "SELECT id FROM Dictionary WHERE teamDictionaryId=? AND isDeleted=0 "
                    "AND phrase=? COLLATE NOCASE LIMIT 1", (TEAM, phrase)).fetchone()
                if active:
                    con.execute("UPDATE Dictionary SET frequencyUsed=frequencyUsed+1, lastUsed=? "
                                "WHERE id=?", (now, active[0]))
                    return active[0], "existing"
                deleted = con.execute(
                    "SELECT id FROM Dictionary WHERE teamDictionaryId=? AND phrase=?",
                    (TEAM, phrase)).fetchone()
                if deleted:
                    con.execute(
                        "UPDATE Dictionary SET isDeleted=0, source='user_edits', observedSource=?, "
                        "manualEntry=0, frequencyUsed=frequencyUsed+1, lastUsed=?, modifiedAt=? "
                        "WHERE id=?", (observed, now, now, deleted[0]))
                    return deleted[0], "reactivated"
                new_id = str(uuid.uuid4())
                con.execute(
                    "INSERT INTO Dictionary (id, phrase, replacement, teamDictionaryId, lastUsed, "
                    "frequencyUsed, remoteFrequencyUsed, manualEntry, createdAt, modifiedAt, "
                    "isDeleted, source, isSnippet, observedSource, isStarred, replacementHtml) "
                    "VALUES (?, ?, NULL, ?, ?, 1, 0, 0, ?, ?, 0, 'user_edits', 0, ?, 0, NULL)",
                    (new_id, phrase, TEAM, now, now, now, observed))
                return new_id, "inserted"
        finally:
            con.close()


def csv_path():
    p = opt("csv_path", "")
    if p:
        return os.path.expandvars(os.path.expanduser(p))
    return os.path.join(os.path.expanduser("~"), "Documents", "WisprLearn-dicionario.csv")


def csv_read_words():
    path = csv_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return [row[0] for row in csv.reader(f) if row and row[0].strip()]


def in_wispr_dictionary(phrase):
    """Leitura apenas: a palavra ja esta ativa no dicionario do Wispr?"""
    try:
        con = connect()
        try:
            return con.execute(
                "SELECT 1 FROM Dictionary WHERE teamDictionaryId=? AND isDeleted=0 "
                "AND phrase=? COLLATE NOCASE LIMIT 1", (TEAM, phrase)).fetchone() is not None
        finally:
            con.close()
    except Exception:
        return False


def learn_word_csv(phrase):
    """Acrescenta a palavra (uma coluna = vocabulario, sem regra de substituicao)."""
    with _DB_LOCK:
        if in_wispr_dictionary(phrase):
            return None, "existing"
        if not csv_append(phrase):
            return None, "existing"
        return phrase, "csv"


def csv_append(phrase):
    """Acrescenta ao CSV se ainda nao estiver la. Retorna True se acrescentou."""
    if any(w.lower() == phrase.lower() for w in csv_read_words()):
        return False
    path = csv_path()
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([phrase])
    return True


def csv_remove(phrase):
    with _DB_LOCK:
        words = [w for w in csv_read_words() if w != phrase]
        with open(csv_path(), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            for word in words:
                w.writerow([word])


def unlearn(entry_id):
    now = wispr_ts()
    with _DB_LOCK:
        con = connect()
        try:
            with con:
                con.execute("UPDATE Dictionary SET isDeleted=1, modifiedAt=? WHERE id=?",
                            (now, entry_id))
        finally:
            con.close()


# ------------------------------------------------------------ acompanhamento
class Track(object):
    def __init__(self, view, region, original):
        self.key = "wispr_learn_" + uuid.uuid4().hex[:10]
        self.view_id = view.id()
        self.original = original
        self.created = time.time()
        self.last_mod = self.created
        self.confirmed = False
        self.dirty = False
        self.learned = set()
        view.add_regions(self.key, [region], "", "", sublime.HIDDEN)

    def region(self, view):
        rs = view.get_regions(self.key)
        return rs[0] if rs else None

    def current(self, view):
        r = self.region(view)
        if r is None:
            return None
        a, b = r.begin(), r.end()
        while a > 0 and is_word_char(view.substr(a - 1)):
            a -= 1
        while b < view.size() and is_word_char(view.substr(b)):
            b += 1
        return view.substr(sublime.Region(a, b))

    def touches(self, view, regions):
        r = self.region(view)
        if r is None:
            return False
        big = sublime.Region(max(0, r.begin() - 1), r.end() + 1)
        return any(big.intersects(s) or big.contains(s) for s in regions)

    def drop(self, view):
        try:
            view.erase_regions(self.key)
        except Exception:
            pass
        lst = TRACKED.get(self.view_id, [])
        if self in lst:
            lst.remove(self)


def evaluate(track, view):
    track.dirty = False
    text = track.current(view)
    if text is None:
        return
    corrections, reason = find_corrections(
        track.original, text,
        min_sim=float(opt("min_similarity", 0.55)),
        max_ratio=float(opt("max_change_ratio", 0.4)),
        min_len=int(opt("min_length", 3)))
    if reason:
        log("nada aprendido: " + reason)
        return
    for phrase, observed, sim in corrections:
        k = (phrase, observed)
        if k in track.learned:
            continue
        track.learned.add(k)
        if opt("dry_run", False):
            log("[dry_run] aprenderia %r (ditado %r, sim %.2f)" % (phrase, observed, sim))
            status("[teste] aprenderia «%s»" % phrase)
            continue
        try:
            if opt("mode", "csv") == "database":
                entry_id, action = learn_word(phrase, observed)
                if action != "existing" and opt("csv_backup", True):
                    try:
                        with _DB_LOCK:
                            csv_append(phrase)  # copia de seguranca para reimportar
                    except Exception as e:
                        log("ERRO no CSV de backup: %r" % (e,))
            else:
                entry_id, action = learn_word_csv(phrase)
            LAST_LEARNED.append((entry_id, action, phrase, observed))
            log("%s: %r (ditado %r, sim %.2f)" % (action, phrase, observed, sim))
            if action == "existing":
                status("«%s» já estava no dicionário" % phrase)
            elif action == "csv":
                n = len(csv_read_words())
                mb = os.path.getsize(csv_path()) / 1048576.0
                extra = " — CSV perto de 3 MB, arquive-o" if mb >= float(opt("csv_warn_mb", 2.5)) else ""
                status("«%s» adicionada ao CSV (%d palavras)%s" % (phrase, n, extra))
            else:
                status("aprendeu «%s» (ditado: «%s»)" % (phrase, observed))
        except Exception as e:
            log("ERRO gravando %r: %r\n%s" % (phrase, e, traceback.format_exc()))
            status("erro ao gravar no Wispr (veja o log)")


def check_wispr(track, attempt):
    view = sublime.View(track.view_id)
    if not view.is_valid():
        return
    try:
        hid = find_history(track.original, track.created)
    except Exception as e:
        log("ERRO lendo History: %r" % (e,))
        hid = None
    if hid:
        USED_HISTORY.add(hid)
        track.confirmed = True
        log("ditado do Wispr detectado (%d palavras)" % len(WORD_RE.findall(track.original)))
    elif attempt < 15:
        sublime.set_timeout_async(lambda: check_wispr(track, attempt + 1), 1000)
    else:
        track.drop(view)  # cola comum, nao veio do Wispr


def tick(gen):
    if gen != _GEN[0]:
        return
    try:
        now = time.time()
        idle_need = float(opt("idle_seconds", 12))
        max_age = float(opt("max_track_seconds", 600))
        for vid, tracks in list(TRACKED.items()):
            view = sublime.View(vid)
            if not view.is_valid():
                TRACKED.pop(vid, None)
                continue
            for t in list(tracks):
                if not t.confirmed:
                    if now - t.created > 30:
                        t.drop(view)
                    continue
                idle = now - t.last_mod
                if t.dirty and idle >= idle_need and (not t.touches(view, view.sel()) or idle >= 45):
                    evaluate(t, view)
                if now - t.created >= max_age:
                    if t.dirty:
                        evaluate(t, view)
                    t.drop(view)
    except Exception:
        log("ERRO no tick:\n" + traceback.format_exc())
    sublime.set_timeout_async(lambda: tick(gen), 3000)


class WisprLearnListener(sublime_plugin.EventListener):
    def on_text_command(self, view, name, args):
        if name in PASTE_COMMANDS and opt("enabled", True) and sqlite3:
            sel = view.sel()
            if len(sel) == 1:
                PENDING_PASTE[view.id()] = (view.size(), sel[0].begin(), sel[0].size())

    def on_post_text_command(self, view, name, args):
        if name not in PASTE_COMMANDS:
            return
        p = PENDING_PASTE.pop(view.id(), None)
        if not p:
            return
        size0, start, selsize = p
        inserted = view.size() - size0 + selsize
        if inserted <= 0:
            return
        region = sublime.Region(start, start + inserted)
        text = view.substr(region)
        if not WORD_RE.search(text):
            return
        # um novo ditado encerra a observacao dos anteriores (como o Wispr faz)
        for t in TRACKED.get(view.id(), []):
            if t.confirmed and t.dirty:
                t.last_mod = 0
        track = Track(view, region, text)
        TRACKED.setdefault(view.id(), []).append(track)
        sublime.set_timeout_async(lambda: check_wispr(track, 0), 500)

    def on_modified_async(self, view):
        tracks = TRACKED.get(view.id())
        if not tracks:
            return
        sel = list(view.sel())
        now = time.time()
        for t in tracks:
            if t.confirmed and t.touches(view, sel):
                t.dirty = True
                t.last_mod = now

    def on_pre_close(self, view):
        for t in list(TRACKED.get(view.id(), [])):
            if t.confirmed and t.dirty:
                try:
                    evaluate(t, view)
                except Exception:
                    log("ERRO ao fechar:\n" + traceback.format_exc())
        TRACKED.pop(view.id(), None)


# ------------------------------------------------------------ comandos
class WisprLearnUndoCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        while LAST_LEARNED:
            entry_id, action, phrase, observed = LAST_LEARNED.pop()
            if action in ("inserted", "reactivated", "csv"):
                try:
                    if action != "csv":
                        unlearn(entry_id)
                    if os.path.exists(csv_path()):
                        csv_remove(phrase)
                    log("desfeito: %r" % phrase)
                    status("removeu «%s» do dicionário" % phrase)
                except Exception as e:
                    log("ERRO ao desfazer %r: %r" % (phrase, e))
                    status("erro ao desfazer (veja o log)")
                return
        status("nada para desfazer nesta sessão")


class WisprLearnShowLogCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not os.path.exists(LOG_PATH):
            open(LOG_PATH, "a", encoding="utf-8").close()
        self.window.open_file(LOG_PATH)


class WisprLearnOpenCsvCommand(sublime_plugin.WindowCommand):
    def run(self):
        path = csv_path()
        if not os.path.exists(path):
            status("CSV ainda vazio: nenhuma palavra aprendida")
            return
        self.window.open_file(path)


class WisprLearnArchiveCsvCommand(sublime_plugin.ApplicationCommand):
    """Depois de importar no Wispr: renomeia o CSV com a data e comeca um novo."""
    def run(self):
        path = csv_path()
        if not os.path.exists(path):
            status("não há CSV para arquivar")
            return
        base, ext = os.path.splitext(path)
        dest = "%s-importado-%s%s" % (base, datetime.datetime.now().strftime("%Y%m%d-%H%M"), ext)
        with _DB_LOCK:
            os.rename(path, dest)
        log("CSV arquivado em %s" % dest)
        status("CSV arquivado; novas palavras vão para um arquivo novo")


class WisprLearnToggleCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        s = settings()
        s.set("enabled", not s.get("enabled", True))
        sublime.save_settings("WisprLearn.sublime-settings")
        status("ativado" if s.get("enabled") else "desativado")


def plugin_loaded():
    _GEN[0] += 1
    info = [
        "python %s" % sys.version.split()[0],
        "sqlite3 %s" % (("ok " + sqlite3.sqlite_version) if sqlite3 else ("FALHOU " + str(SQLITE_ERROR))),
        "banco %s (existe=%s)" % (db_path(), os.path.exists(db_path())),
        "modo %s%s" % (opt("mode", "csv"), (" -> " + csv_path()) if opt("mode", "csv") != "database" else ""),
    ]
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(info) + "\n" + datetime.datetime.now().isoformat() + "\n")
    except Exception:
        pass
    log("plugin carregado | " + " | ".join(info))
    gen = _GEN[0]
    sublime.set_timeout_async(lambda: tick(gen), 3000)


def plugin_unloaded():
    _GEN[0] += 1
