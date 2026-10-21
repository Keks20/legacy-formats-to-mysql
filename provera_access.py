"""
Proverava da baza u MySQL-u sadrzi TACNO ono sto je u Access fajlu.

    D:\\Python314-32\\python.exe provera_access.py podaci\\access\\nwind.mdb

Za svaku tabelu poredi broj redova, pa za svaku kolonu broj popunjenih vrednosti,
zbir brojeva, najduzi tekst i kontrolnu sumu (SHA-256), i na kraju kontrolnu sumu
cele tabele. Slike i drugi binarni podaci (OLE) porede se preko SHA-256 sadrzaja.
Bazu samo cita.
"""

import sys
from decimal import Decimal

from access_zajednicko import (
    argumenti, kolone, konekcija, kontrolna_suma, otvori, primarni_kljuc, procitaj, tabele)


def profil(redovi, i):
    vrednosti = [r[i] for r in redovi if r[i] is not None]
    brojevi = [v for v in vrednosti if isinstance(v, (int, Decimal)) and not isinstance(v, bool)]
    realni = [v for v in vrednosti if isinstance(v, float)]
    tekst = [v for v in vrednosti if isinstance(v, str)]
    zbir = None
    if brojevi:
        zbir = format(sum(brojevi, Decimal(0)).normalize(), "f")
    elif realni:
        zbir = round(sum(realni), 6)
    return len(vrednosti), zbir, max((len(t) for t in tekst), default=None)


def main():
    arg = argumenti(__doc__.strip().splitlines()[0])
    con, drajver = otvori(arg.access)
    spisak = tabele(con, arg.tabele)
    db = konekcija(arg)

    greske = 0

    def uporedi(naziv, a, b):
        nonlocal greske
        ok = a == b
        greske += 0 if ok else 1
        if not ok or naziv.endswith(("redova", "CELA TABELA")):
            print("  {:<4} {:<44} access: {:<18} mysql: {}".format("OK" if ok else "RAZL", naziv, str(a), str(b)))

    print("Access {}  <->  MySQL baza {}   (drajver: {})".format(arg.access, arg.baza, drajver))
    for t in spisak:
        kol = kolone(con, t)
        pk = primarni_kljuc(con, t)
        iz_access = procitaj(con, t, kol, pk)
        with db.cursor() as c:
            c.execute("SELECT {} FROM `{}` ORDER BY `_red`".format(
                ", ".join("`{}`".format(k.ime) for k in kol), t))
            iz_mysql = [[bytes(v) if isinstance(v, (bytearray, memoryview)) else v for v in r]
                        for r in c.fetchall()]

        print("\n{}".format(t))
        uporedi("broj redova", len(iz_access), len(iz_mysql))
        for i, k in enumerate(kol):
            a, b = profil(iz_access, i), profil(iz_mysql, i)
            uporedi(k.ime + ": popunjeno", a[0], b[0])
            if a[1] is not None or b[1] is not None:
                uporedi(k.ime + ": zbir", a[1], b[1])
            if a[2] is not None or b[2] is not None:
                uporedi(k.ime + ": najduzi tekst", a[2], b[2])
            uporedi(k.ime + ": kontrolna suma",
                    kontrolna_suma([r[i]] for r in iz_access)[:16], kontrolna_suma([r[i]] for r in iz_mysql)[:16])
        uporedi("CELA TABELA", kontrolna_suma(iz_access)[:16], kontrolna_suma(iz_mysql)[:16])

    con.close()
    db.close()
    print("\n" + ("SVE SE POKLAPA ({} tabela).".format(len(spisak)) if greske == 0
                  else "RAZLIKA: {}. Proveri gore redove sa RAZL.".format(greske)))
    sys.exit(0 if greske == 0 else 1)


if __name__ == "__main__":
    main()
