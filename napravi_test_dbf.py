"""
Pravi podaci\\magacin.dbf + magacin.dbt: IZMISLJEN magacin iz kraja 90-ih, za vezbu.

Fajl je napisan bajt po bajt kao dBase III+ sa memo poljem, u DOS kodnoj strani
852 (YU latinica), BEZ oznake kodne strane u zaglavlju - tako izgleda vecina
starih fajlova iz srpskih firmi. Namerno ima probleme kakve nose pravi fajlovi:

  red  7, 15, 31   obrisani u dBase-u (DELETE bez PACK - i dalje su u fajlu)
  red 12           prazan datum nabavke
  red 19           datum 30.02.1999 (ne postoji)
  red 23           kolicina se nije uklopila u polje: **********
  red 27           AKTIVAN = '?' (nepoznato)
  red 33           prazna cena

Pokrece se jednom; rezultat je vec u folderu podaci.
"""

import datetime
import os
import random
import struct

POLJA = [  # ime, tip, duzina, decimale
    ("SIFRA", "C", 6, 0),
    ("NAZIV", "C", 30, 0),
    ("JM", "C", 3, 0),
    ("KOLICINA", "N", 10, 3),
    ("CENA", "N", 12, 2),
    ("DAT_NAB", "D", 8, 0),
    ("AKTIVAN", "L", 1, 0),
    ("NAPOMENA", "M", 10, 0),
]

ARTIKLI = [
    ("Šećer kristal", "kg"), ("Brašno T-400", "kg"), ("Ulje suncokretovo", "l"),
    ("Čokolada mlečna 100g", "kom"), ("Džem od šljiva", "kom"), ("Kafa mlevena 200g", "kom"),
    ("Žvaka 5 kom", "kom"), ("Đevrek", "kom"), ("Ćuretina file", "kg"),
    ("Sir gauda", "kg"), ("Mleko 2,8%", "l"), ("Jogurt čaša", "kom"),
    ("Pirinač", "kg"), ("Šampon za kosu", "kom"), ("Deterdžent 3kg", "kom"),
    ("Sapun", "kom"), ("Čaj od nane", "kom"), ("Paprika crvena", "kg"),
    ("Krompir mladi", "kg"), ("Luk crni", "kg"),
]
NAPOMENE = [
    "Dobavljač kasni sa isporukom.\r\nPozvati u ponedeljak.",
    "Čuvati na suvom i hladnom mestu.",
    "Akcija do kraja meseca - ćirilica na deklaraciji.",
    "Reklamacija: oštećena ambalaža (3 kom).",
]


def polje_bajtovi(tip, duzina, dec, vrednost):
    if vrednost is None:
        return b" " * duzina
    if isinstance(vrednost, bytes):           # namerno pokvarena sirova vrednost
        return vrednost.ljust(duzina)[:duzina]
    if tip == "C":
        return vrednost.encode("cp852").ljust(duzina)[:duzina]
    if tip == "N":
        return ("{:>{d}.{p}f}".format(vrednost, d=duzina, p=dec)).encode("ascii")
    if tip == "D":
        return vrednost.strftime("%Y%m%d").encode("ascii")
    if tip == "L":
        return vrednost.encode("ascii")
    if tip == "M":
        return ("{:>10d}".format(vrednost)).encode("ascii")
    raise ValueError(tip)


def main():
    random.seed(1998)
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podaci")
    os.makedirs(folder, exist_ok=True)

    memo_blokovi = []          # tekst po bloku; blok 0 je zaglavlje .dbt-a
    def dodaj_memo(tekst):
        sadrzaj = tekst.encode("cp852") + b"\x1a\x1a"
        broj = 1 + sum(len(b) // 512 for b in memo_blokovi)
        memo_blokovi.append(sadrzaj.ljust(((len(sadrzaj) + 511) // 512) * 512, b"\x00"))
        return broj

    zapisi = []
    for i in range(1, 41):
        naziv, jm = ARTIKLI[(i - 1) % len(ARTIKLI)]
        if i > len(ARTIKLI):
            naziv = naziv + " (2)"
        kolicina = round(random.uniform(1, 900), 3)
        cena = round(random.uniform(20, 2500), 2)
        datum = datetime.date(1995, 1, 1) + datetime.timedelta(days=random.randint(0, 2500))
        aktivan = random.choice("TTTF")
        memo = dodaj_memo(NAPOMENE[i % len(NAPOMENE)]) if i % 5 == 0 else None

        if i == 12:
            datum = None
        if i == 19:
            datum = b"19990230"
        if i == 23:
            kolicina = b"**********"
        if i == 27:
            aktivan = "?"
        if i == 33:
            cena = None

        vrednosti = ["{:06d}".format(1000 + i), naziv, jm, kolicina, cena, datum, aktivan, memo]
        obrisan = i in (7, 15, 31)
        zapis = (b"*" if obrisan else b" ") + b"".join(
            polje_bajtovi(t, d, p, v) for (_, t, d, p), v in zip(POLJA, vrednosti))
        zapisi.append(zapis)

    duzina_zapisa = 1 + sum(p[2] for p in POLJA)
    duzina_zaglavlja = 32 + 32 * len(POLJA) + 1
    zaglavlje = struct.pack("<BBBBIHH", 0x83, 2000 - 1900, 3, 15, len(zapisi),
                            duzina_zaglavlja, duzina_zapisa) + b"\x00" * 20  # bajt jezika = 0
    opisi = b""
    for ime, tip, duz, dec in POLJA:
        opisi += ime.encode("ascii").ljust(11, b"\x00") + tip.encode("ascii") + b"\x00" * 4 \
                 + bytes([duz, dec]) + b"\x00" * 14

    with open(os.path.join(folder, "magacin.dbf"), "wb") as f:
        f.write(zaglavlje + opisi + b"\x0d" + b"".join(zapisi) + b"\x1a")

    sledeci = 1 + sum(len(b) // 512 for b in memo_blokovi)
    with open(os.path.join(folder, "magacin.dbt"), "wb") as f:
        f.write(struct.pack("<I", sledeci).ljust(512, b"\x00") + b"".join(memo_blokovi))

    print("Napravljeno: podaci\\magacin.dbf ({} zapisa) i podaci\\magacin.dbt".format(len(zapisi)))


if __name__ == "__main__":
    main()
