"""
Proverava da tabela u MySQL-u sadrzi TACNO ono sto je u .dbf fajlu.

    python provera_dbf.py podaci\\test.dbf
    python provera_dbf.py podaci\\magacin.dbf --kodna-strana cp852

Poredi, posebno za svaku kolonu:
  * broj zapisa i broj obrisanih;
  * koliko vrednosti nije prazno (NULL);
  * zbir brojeva i najduzi tekst (hvata odsecanje i zaokruzivanje);
  * kontrolnu sumu (SHA-256) svih vrednosti, red po red.
I na kraju pokazuje 3 nasumicna zapisa jedan pored drugog, za proveru okom.
Bazu samo cita.
"""

import random
import sys
from decimal import Decimal

from dbf_zajednicko import (
    Parser, argumenti, ime_tabele, kanonski, konekcija, kontrolna_suma, otvori)


def profil(redovi, n_kolona):
    """Za svaku kolonu: (ne-NULL, zbir brojeva, najduzi tekst)."""
    rez = []
    for i in range(n_kolona):
        vrednosti = [r[i] for r in redovi if r[i] is not None]
        brojevi = [v for v in vrednosti if isinstance(v, (int, Decimal)) and not isinstance(v, bool)]
        tekst = [v for v in vrednosti if isinstance(v, str)]
        rez.append((len(vrednosti),
                    sum(brojevi, Decimal(0)) if brojevi else None,
                    max((len(t) for t in tekst), default=None)))
    return rez


def main():
    arg = argumenti(__doc__.strip().splitlines()[0])
    tabela = otvori(arg.dbf, arg.kodna_strana)
    ime = ime_tabele(arg.dbf, arg.tabela)
    polja = [p.name for p in tabela.fields]

    parser = Parser(tabela)
    iz_dbf = [[red, int(obrisan)] + [v[p] for p in polja] for red, obrisan, v in tabela.svi_zapisi(parser)]

    con = konekcija(arg)
    try:
        with con.cursor() as c:
            c.execute("SELECT `_red`, `_obrisan`, {} FROM `{}` ORDER BY `_red`".format(
                ", ".join("`{}`".format(p) for p in polja), ime))
            iz_baze = [list(r) for r in c.fetchall()]
    finally:
        con.close()

    kolone = ["_red", "_obrisan"] + polja
    greske = 0

    def uporedi(naziv, a, b):
        nonlocal greske
        ok = a == b
        greske += 0 if ok else 1
        print("  {:<4} {:<34} dbf: {:<22} baza: {}".format("OK" if ok else "RAZL", naziv, str(a), str(b)))

    print("Tabela {}.{}  <->  {}".format(arg.baza, ime, arg.dbf))
    uporedi("broj zapisa", len(iz_dbf), len(iz_baze))
    uporedi("obrisanih", sum(r[1] for r in iz_dbf), sum(r[1] for r in iz_baze))

    p_dbf, p_baza = profil(iz_dbf, len(kolone)), profil(iz_baze, len(kolone))
    for i, kol in enumerate(kolone[2:], start=2):
        uporedi(kol + ": popunjeno", p_dbf[i][0], p_baza[i][0])
        if p_dbf[i][1] is not None or p_baza[i][1] is not None:
            uporedi(kol + ": zbir", p_dbf[i][1], p_baza[i][1])
        if p_dbf[i][2] is not None or p_baza[i][2] is not None:
            uporedi(kol + ": najduzi tekst", p_dbf[i][2], p_baza[i][2])

    for i, kol in enumerate(kolone[2:], start=2):
        a = kontrolna_suma([r[0], r[i]] for r in iz_dbf)
        b = kontrolna_suma([r[0], r[i]] for r in iz_baze)
        uporedi(kol + ": kontrolna suma", a[:16], b[:16])
    uporedi("CELA TABELA: kontrolna suma", kontrolna_suma(iz_dbf)[:16], kontrolna_suma(iz_baze)[:16])

    if iz_dbf and len(iz_dbf) == len(iz_baze):
        print("\nNasumicni zapisi (dbf / baza):")
        for i in sorted(random.sample(range(len(iz_dbf)), min(3, len(iz_dbf)))):
            print("  zapis {}".format(iz_dbf[i][0]))
            print("    dbf : " + " | ".join(kanonski(v) for v in iz_dbf[i][2:]))
            print("    baza: " + " | ".join(kanonski(v) for v in iz_baze[i][2:]))

    if parser.problemi:
        print("\nNapomena: {} vrednosti iz .dbf-a nisu mogle da se procitaju i namerno su NULL "
              "(spisak daje dbf_u_mysql.py --pregled).".format(len(parser.problemi)))

    print("\n" + ("SVE SE POKLAPA." if greske == 0 else "RAZLIKA: {}. Proveri gore redove sa RAZL.".format(greske)))
    sys.exit(0 if greske == 0 else 1)


if __name__ == "__main__":
    main()
