"""
Prebacuje jedan .dbf fajl (dBase III/IV, Clipper, FoxPro) u tabelu u MySQL-u.

    python dbf_u_mysql.py podaci\\test.dbf --pregled              (samo pogledaj)
    python dbf_u_mysql.py podaci\\test.dbf                        (uvezi)
    python dbf_u_mysql.py podaci\\magacin.dbf --kodna-strana cp852

Sta radi:
  * pravi bazu (podrazumevano stari_formati) i tabelu sa tipovima iz zaglavlja .dbf-a;
  * prebacuje SVE zapise, i one obrisane u dBase-u (kolona _obrisan = 1),
    jer obrisan zapis u .dbf-u nije nestao - klijent mozda zeli da ga vidi;
  * cuva redosled iz fajla (kolona _red = broj zapisa, 1, 2, 3...);
  * vrednosti koje ne moze da procita upisuje kao NULL i nabraja ih kao PROBLEME;
  * sve upisuje u jednoj transakciji: ili cela tabela, ili nista.

Postojecu tabelu ne brise, osim uz --prepisi.
"""

import sys

from dbf_zajednicko import (
    Parser, argumenti, ima_ne_ascii, ime_tabele, konekcija, mysql_tip, otvori)

KODNE_STRANE_ZA_PROBU = ["cp852", "cp1250", "cp437", "cp866", "cp1252"]


def prikazi_strukturu(tabela, ime):
    h = tabela.header
    print("Fajl:          {}".format(tabela.filename))
    print("Verzija:       0x{:02x}   (0x03 dBase III, 0x83 dBase III + memo, 0x30 Visual FoxPro...)".format(h.dbversion))
    print("Poslednja izmena (iz zaglavlja): {}".format(tabela.date))
    print("Zapisa:        {}".format(h.numrecords))
    print("Kodna strana:  {}  (bajt jezika u zaglavlju: 0x{:02x})".format(tabela.encoding, h.language_driver))
    print("Tabela u MySQL-u: {}".format(ime))
    print()
    print("  {:<11} {:<4} {:>5} {:>4}   {}".format("Polje", "Tip", "Duz.", "Dec", "MySQL"))
    for p in tabela.fields:
        print("  {:<11} {:<4} {:>5} {:>4}   {}".format(p.name, p.type, p.length, p.decimal_count, mysql_tip(p)))
    print()


def predlozi_kodnu_stranu(tabela):
    """Pokazuje prvi tekst sa nasim slovima u vise kodnih strana - covek bira onu koja je citljiva."""
    tekstualna = [p for p in tabela.fields if p.type == "C"]
    with open(tabela.filename, "rb") as f:
        f.seek(tabela.header.headerlen)
        while True:
            oznaka = f.read(1)
            if oznaka in (b"\x1a", b""):
                return
            for p in tabela.fields:
                bajtovi = f.read(p.length)
                if p in tekstualna and any(b > 127 for b in bajtovi):
                    print("Tekst sa slovima van ASCII-ja, polje {}, procitan u raznim kodnim stranama:".format(p.name))
                    for ks in KODNE_STRANE_ZA_PROBU:
                        print("  {:<7} {}".format(ks, bajtovi.decode(ks, errors="replace").rstrip()))
                    print("Izaberi onu u kojoj su slova ispravna i dodaj npr.  --kodna-strana cp852")
                    return


def main():
    arg = argumenti(__doc__.strip().splitlines()[0], sa_prepisi=True)
    tabela = otvori(arg.dbf, arg.kodna_strana)
    ime = ime_tabele(arg.dbf, arg.tabela)

    prikazi_strukturu(tabela, ime)

    # Bez kodne strane i bez podatka u zaglavlju dbfread pretpostavlja ASCII.
    # Ako fajl ima nasa slova, to bi puklo usred uvoza - bolje odmah i jasno.
    if not arg.kodna_strana and tabela.encoding == "ascii" and ima_ne_ascii(tabela):
        predlozi_kodnu_stranu(tabela)
        sys.exit("\nKodna strana nije upisana u fajl, a tekst ima slova van ASCII-ja. "
                 "Pokreni ponovo sa --kodna-strana.")

    parser = Parser(tabela)
    try:
        zapisi = list(tabela.svi_zapisi(parser))
    except UnicodeDecodeError as e:
        predlozi_kodnu_stranu(tabela)
        sys.exit("\nTekst ne moze da se procita u kodnoj strani {}: {}".format(tabela.encoding, e))

    obrisanih = sum(1 for _, obrisan, _ in zapisi if obrisan)
    print("Procitano zapisa: {}  (aktivnih {}, obrisanih u dBase-u {})".format(
        len(zapisi), len(zapisi) - obrisanih, obrisanih))
    if parser.problemi:
        print("PROBLEMI ({}): vrednosti koje postaju NULL".format(len(parser.problemi)))
        for p in parser.problemi[:30]:
            print("  " + str(p))
        if len(parser.problemi) > 30:
            print("  ... i jos {}".format(len(parser.problemi) - 30))
    else:
        print("Problema nema.")

    if arg.pregled:
        print("\nPrvih 5 zapisa:")
        for red, obrisan, vrednosti in zapisi[:5]:
            print("  {}{}: {}".format(red, " (obrisan)" if obrisan else "", vrednosti))
        print("\n--pregled: baza nije dirana.")
        return

    polja = [p.name for p in tabela.fields]
    kolone = ",\n  ".join("`{}` {} NULL".format(p.name, mysql_tip(p)) for p in tabela.fields)
    ddl = ("CREATE TABLE `{}` (\n"
           "  `_red` INT NOT NULL,\n"
           "  `_obrisan` TINYINT(1) NOT NULL DEFAULT 0,\n"
           "  {},\n"
           "  PRIMARY KEY (`_red`)\n"
           ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci").format(ime, kolone)

    # Baza se pravi ako ne postoji
    con = konekcija(arg, sa_bazom=False)
    with con.cursor() as c:
        c.execute("CREATE DATABASE IF NOT EXISTS `{}` CHARACTER SET utf8mb4 "
                  "COLLATE utf8mb4_unicode_ci".format(arg.baza))
    con.close()

    con = konekcija(arg)
    try:
        with con.cursor() as c:
            c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                      (arg.baza, ime))
            if c.fetchone():
                if not arg.prepisi:
                    sys.exit("\nTabela `{}` vec postoji u bazi {}. Nista nije menjano.\n"
                             "Da bi se uvezla ponovo (stari sadrzaj se brise): dodaj --prepisi".format(ime, arg.baza))
                c.execute("DROP TABLE `{}`".format(ime))
            c.execute(ddl)   # CREATE TABLE u MySQL-u sam potvrdjuje; podaci idu u transakciju ispod

            sql = "INSERT INTO `{}` (`_red`, `_obrisan`, {}) VALUES ({})".format(
                ime, ", ".join("`{}`".format(p) for p in polja), ", ".join(["%s"] * (len(polja) + 2)))
            redovi = [[red, int(obrisan)] + [vrednosti[p] for p in polja] for red, obrisan, vrednosti in zapisi]
            for i in range(0, len(redovi), 500):
                c.executemany(sql, redovi[i:i + 500])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print("\nUpisano u {}.{}: {} redova. Proveri sa:  python provera_dbf.py {}{}".format(
        arg.baza, ime, len(redovi), arg.dbf,
        " --kodna-strana " + arg.kodna_strana if arg.kodna_strana else ""))


if __name__ == "__main__":
    main()
