"""
Zajednicka pravila za prebacivanje dBase/Clipper/FoxPro .dbf fajlova u MySQL.

Koriste ih i dbf_u_mysql.py (uvoz) i provera_dbf.py (provera), da bi provera
merila TACNO ono sto je uvoz uradio. Svako pravilo je opisano u README.md,
odeljak "Pravila pretvaranja".

Biblioteka dbfread cita format fajla, ali neke stvari radi tiho, a to kod
migracije ne sme:
  * broj koji se nije uklopio u polje ('*****') pretvara u prazno, bez upozorenja;
  * brojeve sa decimalama vraca kao float (12.1 postaje 12.0999999...);
  * na neispravnom datumu (30. februar) prekida ceo uvoz.
Zato ovde postoji sopstveni parser: svaka cudna vrednost postaje NULL, ali se
zapise kao PROBLEM (red, polje, sirova vrednost, razlog), da bi se videlo i
moglo resiti sa klijentom.
"""

import argparse
import os
import re
import sys
from decimal import Decimal, InvalidOperation

from dbfread import DBF
from dbfread.field_parser import FieldParser

from kontrola import dodaj_mysql_argumente, kanonski, konekcija, kontrolna_suma  # noqa: F401 (koriste ih druge skripte)

# Tipovi polja koje alat zna da prebaci. Ostali (binarni G, B, P...) se odbijaju
# glasno, umesto da se tiho preskoce.
PODRZANI_TIPOVI = set("CNFDLMITY")


class Problem:
    """Vrednost koja nije mogla da se procita kako treba - u bazi postaje NULL."""

    def __init__(self, red, polje, sirovo, razlog):
        self.red = red
        self.polje = polje
        self.sirovo = sirovo
        self.razlog = razlog

    def __str__(self):
        return "red {:>6}  {:<10}  {!r:<16}  {}".format(
            self.red, self.polje, self.sirovo, self.razlog)


class Parser(FieldParser):
    """Parser polja koji ne prekida uvoz i ne gubi podatke bez traga."""

    def __init__(self, table, memofile=None):
        super().__init__(table, memofile)
        self.red = 0          # broj zapisa koji se trenutno cita (postavlja citac)
        self.problemi = []

    def _problem(self, polje, sirovo, razlog):
        self.problemi.append(Problem(self.red, polje.name, sirovo, razlog))
        return None

    # ---- tekst ----
    def parseC(self, field, data):
        tekst = super().parseC(field, data)
        return tekst if tekst != "" else None

    def parseM(self, field, data):
        try:
            memo = super().parseM(field, data)
        except (ValueError, LookupError) as e:
            return self._problem(field, data, "memo: " + str(e))
        if memo is None or memo == "":
            return None
        if not isinstance(memo, str):
            return self._problem(field, data, "binarni memo (nije tekst)")
        return memo.rstrip("\x1a")

    # ---- brojevi: Decimal, ne float ----
    def _broj(self, field, data):
        s = data.strip()
        if not s:
            return None
        if b"*" in s:
            return self._problem(field, data, "broj se nije uklopio u polje (prekoracenje)")
        try:
            vrednost = Decimal(s.replace(b",", b".").decode("ascii"))
        except (InvalidOperation, UnicodeDecodeError):
            return self._problem(field, data, "nije broj")
        if field.decimal_count == 0:
            if vrednost != vrednost.to_integral_value():
                return self._problem(field, data, "decimale u celobrojnom polju")
            return int(vrednost)
        return vrednost.quantize(Decimal(1).scaleb(-field.decimal_count))

    def parseN(self, field, data):
        return self._broj(field, data)

    def parseF(self, field, data):
        return self._broj(field, data)

    # ---- datum i logicko polje ----
    def parseD(self, field, data):
        try:
            return super().parseD(field, data)
        except ValueError:
            return self._problem(field, data, "neispravan datum")

    def parseL(self, field, data):
        try:
            vrednost = super().parseL(field, data)
        except ValueError:
            return self._problem(field, data, "nije T/F/Y/N/?")
        return None if vrednost is None else int(vrednost)

    def parseT(self, field, data):
        try:
            return super().parseT(field, data)
        except ValueError:
            return self._problem(field, data, "neispravan datum i vreme")


class Tabela(DBF):
    """DBF koji vraca SVE zapise redom, i obrisane, sa brojem zapisa."""

    def svi_zapisi(self, parser):
        """Vraca (broj_zapisa, obrisan, {polje: vrednost}) redom kao u fajlu."""
        with open(self.filename, "rb") as f, self._open_memofile() as memo:
            if memo is not None:
                parser.get_memo = memo.__getitem__
            f.seek(self.header.headerlen, 0)
            red = 0
            while True:
                oznaka = f.read(1)
                if oznaka in (b"\x1a", b""):
                    break
                red += 1
                parser.red = red
                sirovo = {polje.name: f.read(polje.length) for polje in self.fields}
                vrednosti = {ime: parser.parse(polje, sirovo[ime])
                             for polje, ime in ((p, p.name) for p in self.fields)}
                yield red, oznaka == b"*", vrednosti
            if red != self.header.numrecords:
                parser.problemi.append(Problem(
                    "-", "(fajl)", red,
                    "zaglavlje kaze {} zapisa, procitano {}".format(self.header.numrecords, red)))


def otvori(putanja, kodna_strana=None):
    """Otvara .dbf. Bez kodne strane uzima onu iz zaglavlja (ako je upisana)."""
    if not os.path.isfile(putanja):
        sys.exit("Nema fajla: " + putanja)
    tabela = Tabela(putanja, encoding=kodna_strana, load=False,
                    char_decode_errors="strict", parserclass=Parser,
                    ignore_missing_memofile=False)
    nepodrzani = [(p.name, p.type) for p in tabela.fields if p.type not in PODRZANI_TIPOVI]
    if nepodrzani:
        sys.exit("Polja tipa koji alat ne zna da prebaci: {}".format(nepodrzani))
    return tabela


def ima_ne_ascii(tabela):
    """Da li tekstualna polja imaju bajtove > 127 (č, ć, š... u nekoj kodnoj strani)."""
    tekstualna = [p for p in tabela.fields if p.type == "C"]
    if not tekstualna:
        return False
    with open(tabela.filename, "rb") as f:
        f.seek(tabela.header.headerlen)
        sadrzaj = f.read()
    return any(b > 127 for b in sadrzaj)


def mysql_tip(polje):
    """Tip kolone u MySQL-u za polje iz .dbf-a."""
    t, duz, dec = polje.type, polje.length, polje.decimal_count
    if t == "C":
        return "VARCHAR({})".format(duz)
    if t in "NF":
        if dec == 0:
            return "INT" if duz <= 9 else "BIGINT"
        # U dBase-u duzina ukljucuje znak i decimalnu tacku, pa je DECIMAL(duz, dec) uvek dovoljan
        return "DECIMAL({},{})".format(max(duz, dec + 1), dec)
    if t == "D":
        return "DATE"
    if t == "L":
        return "TINYINT(1)"
    if t == "M":
        return "MEDIUMTEXT"
    if t == "I":
        return "INT"
    if t == "T":
        return "DATETIME"
    if t == "Y":
        return "DECIMAL(19,4)"
    raise ValueError(t)


def ime_tabele(putanja, zadato=None):
    ime = zadato or os.path.splitext(os.path.basename(putanja))[0]
    ime = re.sub(r"[^0-9A-Za-z_]", "_", ime).lower()
    if not ime or ime[0].isdigit():
        ime = "t_" + ime
    return ime


def argumenti(opis, sa_prepisi=False):
    p = argparse.ArgumentParser(description=opis)
    p.add_argument("dbf", help="putanja do .dbf fajla (memo .dbt/.fpt mora biti pored njega)")
    p.add_argument("--tabela", help="ime tabele u MySQL-u (podrazumevano: ime fajla)")
    p.add_argument("--kodna-strana", dest="kodna_strana",
                   help="npr. cp852 (DOS, YU latinica), cp1250 (Windows), cp437 (stari DOS bez nasih slova)")
    dodaj_mysql_argumente(p)
    if sa_prepisi:
        p.add_argument("--prepisi", action="store_true",
                       help="obrisi postojecu tabelu istog imena i uvezi ponovo")
        p.add_argument("--pregled", action="store_true",
                       help="samo prikazi strukturu, primere i probleme; baza se ne dira")
    return p.parse_args()
