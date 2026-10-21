"""
Zajednicka pravila za prebacivanje Access baza (.mdb, .accdb) u MySQL.

Koriste ih access_u_mysql.py (uvoz) i provera_access.py (provera).

Access se cita preko ODBC drajvera (biblioteka pyodbc). Drajvera ima vise i
nisu jednaki:
  * "Microsoft Access Driver (*.mdb)"            - 32-bitni Jet, deo Windows-a.
        Cita Access 97 i 2000-2003 (.mdb). Radi samo iz 32-bitnog Python-a.
  * "Microsoft Access Driver (*.mdb, *.accdb)"   - 64-bitni ACE (Office / Access
        Database Engine). Cita .mdb od Access 2000 i .accdb, ali NE Access 97.
        Ako je deo Office-a (Microsoft 365), spoljni programi dobijaju poruku
        "The operating system is not presently configured to run this application".
  * "MDBTools"                                   - Linux, besplatan.
Alat sam bira prvi drajver koji otvori fajl.
"""

import argparse
import os
import re
import sys
import uuid
from decimal import Decimal

from kontrola import dodaj_mysql_argumente, kanonski, konekcija, kontrolna_suma  # noqa: F401

# MDBTools pada (segfault) na columns()/statistics(), pa se za njega ne pozivaju
_BEZ_METAPODATAKA = set()

DRAJVERI = [
    "Microsoft Access Driver (*.mdb, *.accdb)",
    "Microsoft Access Driver (*.mdb)",
    "MDBTools",
]


def otvori(putanja):
    """Vraca (konekcija, ime drajvera). Pokusava drajvere redom."""
    import pyodbc

    if not os.path.isfile(putanja):
        sys.exit("Nema fajla: " + putanja)
    putanja = os.path.abspath(putanja)
    instalirani = pyodbc.drivers()
    pokusaji = []
    for drajver in DRAJVERI:
        if drajver not in instalirani:
            continue
        try:
            con = pyodbc.connect("DRIVER={%s};DBQ=%s;ReadOnly=1;" % (drajver, putanja),
                                 autocommit=True, readonly=True)
            if drajver == "MDBTools":
                _BEZ_METAPODATAKA.add(id(con))
            return con, drajver
        except pyodbc.Error as e:
            pokusaji.append("  {}: {}".format(drajver, e))
    bitnost = "64" if sys.maxsize > 2**32 else "32"
    sys.exit("Nijedan Access drajver ne otvara fajl ({}-bitni Python).\n"
             "Instalirani Access drajveri: {}\n{}\n"
             "Za Access 97 i 2000-2003 (.mdb) najlakse je 32-bitni Python + Jet drajver iz Windows-a "
             "(vidi README).".format(bitnost, [d for d in instalirani if "Access" in d or "MDB" in d],
                                     "\n".join(pokusaji) or "  (nijedan nije pronadjen)"))


def tabele(con, samo=None):
    """Korisnicke tabele (bez sistemskih MSys* i bez upita)."""
    cur = con.cursor()
    imena = [r.table_name for r in cur.tables(tableType="TABLE")]
    imena = [t for t in imena if not t.startswith(("MSys", "~"))]
    if samo:
        trazene = [s.strip() for s in samo.split(",") if s.strip()]
        nema = [t for t in trazene if t not in imena]
        if nema:
            sys.exit("Ovih tabela nema u fajlu: {}\nPostoje: {}".format(nema, imena))
        imena = trazene
    return imena


class Kolona:
    def __init__(self, ime, py_tip, velicina, preciznost, decimale, tip_access):
        self.ime = ime
        self.py_tip = py_tip
        self.velicina = velicina or 0
        self.preciznost = preciznost or 0
        self.decimale = decimale or 0
        self.tip_access = (tip_access or "").upper()

    def mysql_tip(self):
        t, n = self.tip_access, self.velicina
        if t in ("BIT", "YESNO") or self.py_tip is bool:
            return "TINYINT(1)"
        if t == "BYTE" or (self.py_tip is int and n == 1):
            return "TINYINT UNSIGNED"
        if t == "SMALLINT" or (self.py_tip is int and n == 2):
            return "SMALLINT"
        if self.py_tip is int:
            return "INT"
        if t in ("CURRENCY", "MONEY"):
            return "DECIMAL(19,4)"
        if self.py_tip is Decimal:
            if self.preciznost and self.decimale and t not in ("",):
                return "DECIMAL({},{})".format(self.preciznost, self.decimale)
            return "DECIMAL(19,4)"      # bez podataka o decimalama: Access valuta (4 decimale)
        if self.py_tip is float:
            return "DOUBLE"             # i Access Single: DOUBLE cuva tacno istu vrednost
        if t in ("DATETIME",) or self.py_tip.__name__ in ("datetime", "date"):
            return "DATETIME"
        if self.py_tip is str:
            if t in ("LONGCHAR", "MEMO", "LONGTEXT") or n == 0 or n > 255:
                return "LONGTEXT"
            return "VARCHAR({})".format(n)
        if self.py_tip in (bytes, bytearray):
            return "LONGBLOB"           # OLE objekat, npr. slika
        if self.py_tip is uuid.UUID or t == "GUID":
            return "CHAR(38)"
        raise ValueError("Nepoznat tip kolone {}: {} / {}".format(self.ime, self.py_tip, t))

    def opis_access(self):
        return self.tip_access or self.py_tip.__name__


def kolone(con, tabela):
    """Kolone tabele, redom. Tip iz cursor.columns() ako drajver to daje, inace iz rezultata upita."""
    cur = con.cursor()
    cur.execute("SELECT * FROM [{}] WHERE 1=0".format(tabela))
    opis = cur.description
    meta = {}
    if id(con) not in _BEZ_METAPODATAKA:
        try:
            for c in con.cursor().columns(table=tabela):
                meta[c.column_name] = c
        except Exception:
            pass                     # drajver ne daje opis kolona: tip iz rezultata upita
    rez = []
    for d in opis:
        m = meta.get(d[0])
        rez.append(Kolona(
            d[0], d[1],
            m.column_size if m else (d[3] or d[2]),
            m.column_size if m else d[4],
            m.decimal_digits if m else d[5],
            m.type_name if m else ""))
    return rez


def primarni_kljuc(con, tabela):
    """Kolone primarnog kljuca (Access indeks 'PrimaryKey'), ako drajver to prijavljuje."""
    if id(con) in _BEZ_METAPODATAKA:
        return []
    try:
        redovi = [s for s in con.cursor().statistics(tabela) if s.index_name]
    except Exception:
        return []
    pk = sorted((s for s in redovi if s.index_name.lower() == "primarykey"), key=lambda s: s.ordinal_position)
    return [s.column_name for s in pk]


def procitaj(con, tabela, kol, pk, problemi=None):
    """Svi redovi tabele, sortirani po primarnom kljucu (ako ga ima), kao liste vrednosti.

    Datum pre 1000. godine Access dozvoljava, a MySQL DATETIME ne: postaje NULL
    i upisuje se u problemi (tabela, red, kolona, vrednost, razlog)."""
    sql = "SELECT {} FROM [{}]".format(", ".join("[{}]".format(k.ime) for k in kol), tabela)
    if pk:
        sql += " ORDER BY " + ", ".join("[{}]".format(k) for k in pk)
    cur = con.cursor()
    cur.execute(sql)
    redovi = []
    for i, r in enumerate(cur.fetchall(), start=1):
        red = [normalizuj(v) for v in r]
        for j, v in enumerate(red):
            if hasattr(v, "year") and v.year < 1000:
                if problemi is not None:
                    problemi.append((tabela, i, kol[j].ime, v, "datum pre 1000. godine (MySQL ga ne prima)"))
                red[j] = None
        redovi.append(red)
    return redovi


def normalizuj(v):
    """Vrednost iz ODBC-a u oblik koji ide u MySQL i u kontrolnu sumu."""
    if isinstance(v, bytearray):
        return bytes(v)
    if isinstance(v, uuid.UUID):
        return "{" + str(v).upper() + "}"
    if isinstance(v, bool):
        return int(v)
    return v


def ime_baze(putanja, zadato=None):
    ime = zadato or os.path.splitext(os.path.basename(putanja))[0]
    ime = re.sub(r"[^0-9A-Za-z_]", "_", ime).lower()
    return ime if ime and not ime[0].isdigit() else "a_" + ime


def argumenti(opis, sa_prepisi=False):
    p = argparse.ArgumentParser(description=opis)
    p.add_argument("access", help="putanja do .mdb ili .accdb fajla")
    p.add_argument("--tabele", help="samo ove tabele, odvojene zarezom (podrazumevano: sve)")
    dodaj_mysql_argumente(p, baza=None)
    if sa_prepisi:
        p.add_argument("--prepisi", action="store_true",
                       help="obrisi postojece tabele istog imena i uvezi ponovo")
        p.add_argument("--pregled", action="store_true",
                       help="samo prikazi tabele, kolone i primere; MySQL se ne dira")
    arg = p.parse_args()
    arg.baza = arg.baza or ime_baze(arg.access)
    return arg
