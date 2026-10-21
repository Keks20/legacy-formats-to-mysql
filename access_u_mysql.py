"""
Prebacuje Access bazu (.mdb ili .accdb) u MySQL: svaka tabela postaje tabela u MySQL-u.

    D:\\Python314-32\\python.exe access_u_mysql.py podaci\\access\\nwind.mdb --pregled
    D:\\Python314-32\\python.exe access_u_mysql.py podaci\\access\\nwind.mdb

Sta radi:
  * pravi bazu u MySQL-u istog imena kao fajl (nwind.mdb -> baza nwind), ili --baza;
  * prenosi tipove: Text -> VARCHAR, Memo -> LONGTEXT, Currency -> DECIMAL(19,4),
    Yes/No -> TINYINT(1), Date/Time -> DATETIME, OLE (slike) -> LONGBLOB...;
  * cuva primarni kljuc i redosled redova (kolona _red);
  * imena tabela i kolona ostaju ista kao u Access-u (i sa razmacima, npr. `Order Details`);
  * podatke upisuje u jednoj transakciji: ili sve tabele, ili nista.

Upiti (queries), forme i izvestaji iz Access-a se NE prenose - to je logika aplikacije,
ne podaci. Veze izmedju tabela (relationships) drajver ne daje; spisak treba napraviti
rucno iz Access-a (Database Tools -> Relationships) - vidi README.
"""

import sys

from access_zajednicko import (
    argumenti, kolone, konekcija, otvori, primarni_kljuc, procitaj, tabele)


def main():
    arg = argumenti(__doc__.strip().splitlines()[0], sa_prepisi=True)
    con, drajver = otvori(arg.access)
    print("Fajl:     {}".format(arg.access))
    print("Drajver:  {}".format(drajver))
    print("MySQL:    baza {}".format(arg.baza))

    spisak = tabele(con, arg.tabele)
    print("Tabela:   {}\n".format(len(spisak)))

    problemi = []
    plan = []   # (tabela, kolone, pk, redovi)
    for t in spisak:
        kol = kolone(con, t)
        pk = primarni_kljuc(con, t)
        redovi = procitaj(con, t, kol, pk, problemi)
        plan.append((t, kol, pk, redovi))
        print("{}  ({} redova, primarni kljuc: {})".format(t, len(redovi), ", ".join(pk) or "nema"))
        for k in kol:
            print("    {:<24} {:<12} -> {}".format(k.ime, k.opis_access(), k.mysql_tip()))
        if arg.pregled and redovi:
            print("    prvi red: {}".format([str(v)[:25] for v in redovi[0]]))
        print()
    con.close()

    if problemi:
        print("PROBLEMI ({}): vrednosti koje postaju NULL".format(len(problemi)))
        for p in problemi[:30]:
            print("  {}  red {}  {}: {!r}  {}".format(*p))
    else:
        print("Problema nema.")

    if arg.pregled:
        print("\n--pregled: MySQL nije diran.")
        return

    # Baza se pravi ako ne postoji
    c0 = konekcija(arg, sa_bazom=False)
    with c0.cursor() as c:
        c.execute("CREATE DATABASE IF NOT EXISTS `{}` CHARACTER SET utf8mb4 "
                  "COLLATE utf8mb4_unicode_ci".format(arg.baza))
    c0.close()

    db = konekcija(arg)
    try:
        with db.cursor() as c:
            postojece = []
            for t, *_ in plan:
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                          (arg.baza, t))
                if c.fetchone():
                    postojece.append(t)
            if postojece and not arg.prepisi:
                sys.exit("\nOve tabele vec postoje u bazi {}: {}\nNista nije menjano. "
                         "Za ponovni uvoz (stari sadrzaj se brise): --prepisi".format(arg.baza, postojece))

            # 1) struktura (CREATE TABLE u MySQL-u sam potvrdjuje, pa ide pre transakcije)
            for t, kol, pk, _ in plan:
                c.execute("DROP TABLE IF EXISTS `{}`".format(t))
                definicije = ["`_red` INT NOT NULL"] + \
                    ["`{}` {} NULL".format(k.ime, k.mysql_tip()) for k in kol]
                # Primarni kljuc iz Access-a ostaje primarni; _red (redosled) je samo jedinstven
                if pk:
                    kljuc = "PRIMARY KEY ({}),\n  UNIQUE KEY `_red` (`_red`)".format(
                        ", ".join("`{}`".format(x) for x in pk))
                else:
                    kljuc = "PRIMARY KEY (`_red`)"
                c.execute("CREATE TABLE `{}` (\n  {},\n  {}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                          "COLLATE=utf8mb4_unicode_ci".format(t, ",\n  ".join(definicije), kljuc))

            # 2) podaci, sve tabele u jednoj transakciji
            for t, kol, pk, redovi in plan:
                sql = "INSERT INTO `{}` (`_red`, {}) VALUES ({})".format(
                    t, ", ".join("`{}`".format(k.ime) for k in kol), ", ".join(["%s"] * (len(kol) + 1)))
                podaci = [[i] + r for i, r in enumerate(redovi, start=1)]
                for i in range(0, len(podaci), 200):
                    c.executemany(sql, podaci[i:i + 200])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    ukupno = sum(len(r) for *_, r in plan)
    print("\nUpisano u bazu {}: {} tabela, {} redova.".format(arg.baza, len(plan), ukupno))
    print("Proveri sa:  provera_access.py {}".format(arg.access))


if __name__ == "__main__":
    main()
