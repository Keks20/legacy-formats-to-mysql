"""
Zajednicko za sve alate u ovom folderu (.dbf i Access):
kanonski zapis vrednosti, kontrolna suma i veza sa MySQL-om.

Ista vrednost procitana iz starog fajla i iz MySQL-a mora da da ISTI tekst,
inace kontrolna suma ne bi mogla da se poredi.
"""

import datetime
import hashlib
import os
import uuid
from decimal import Decimal


def kanonski(vrednost):
    if vrednost is None:
        return "∅"
    if isinstance(vrednost, bool):
        return str(int(vrednost))
    if isinstance(vrednost, Decimal):
        # Vrednost, ne zapis: 14.0000 iz Access-a i 14.00 iz MySQL-a su isti broj
        return format(vrednost.normalize(), "f")
    if isinstance(vrednost, float):
        return repr(vrednost)
    if isinstance(vrednost, datetime.datetime):
        return vrednost.isoformat(sep=" ")
    if isinstance(vrednost, (datetime.date, datetime.time)):
        return vrednost.isoformat()
    if isinstance(vrednost, (bytes, bytearray, memoryview)):
        b = bytes(vrednost)
        return "bin:{}:{}".format(len(b), hashlib.sha256(b).hexdigest()[:16])
    if isinstance(vrednost, uuid.UUID):
        return "{" + str(vrednost).upper() + "}"
    return str(vrednost)


def kontrolna_suma(redovi):
    """SHA-256 preko svih redova (u redosledu u kom su dati)."""
    h = hashlib.sha256()
    for red in redovi:
        h.update("\x1f".join(kanonski(v) for v in red).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def dodaj_mysql_argumente(p, baza="stari_formati"):
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--korisnik", default="root")
    p.add_argument("--lozinka", default=os.environ.get("MYSQL_LOZINKA", ""))
    p.add_argument("--baza", default=baza, help="baza u MySQL-u (podrazumevano: {})".format(baza or "ime fajla"))


def konekcija(arg, sa_bazom=True, baza=None):
    import pymysql
    return pymysql.connect(
        host=arg.host, port=arg.port, user=arg.korisnik, password=arg.lozinka,
        database=(baza or arg.baza) if sa_bazom else None, charset="utf8mb4", autocommit=False)
