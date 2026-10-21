# Stari formati → MySQL

> **In English:** small Python tools that move old dBase/Clipper (`.dbf`) and Microsoft Access (`.mdb`, `.accdb`) databases into MySQL, and then prove with checksums that nothing was lost or changed. They are part of the case study [Modernizing POKSI without stopping it](https://github.com/Keks20/POKSIPP-Modernizacija/blob/main/CASE_STUDY.md). The guide below is in Serbian.

Prebacivanje starih baza u MySQL, kakve donose pravi klijenti.
Dva dela: **dBase / Clipper / FoxPro (`.dbf`)** i **Microsoft Access (`.mdb`, `.accdb`)**.

Alati rade za bilo koji `.dbf` ili Access fajl, ne samo za primere iz foldera `podaci`.

| Fajl | Šta radi |
| --- | --- |
| `dbf_u_mysql.py` | uvoz jednog `.dbf` fajla u tabelu u MySQL-u (ili samo `--pregled`) |
| `provera_dbf.py` | poredi `.dbf` i tabelu, kolonu po kolonu, sa kontrolnim sumama |
| `dbf_zajednicko.py` | pravila pretvaranja koja koriste obe skripte |
| `napravi_test_dbf.py` | pravi `podaci\magacin.dbf` (izmišljen, vidi dole) |
| `access_u_mysql.py` | uvoz cele Access baze (sve tabele) u MySQL bazu istog imena |
| `provera_access.py` | poredi Access i MySQL, tabelu po tabelu i kolonu po kolonu |
| `access_zajednicko.py` | izbor drajvera, tipovi kolona, čitanje |
| `kontrola.py` | kontrolne sume i veza sa MySQL-om, zajedničko za sve |

## Podaci za vežbu (`.dbf`)

- **`podaci\test.dbf`**: klasičan Clipper uzorak (dBase III, 500 zaposlenih, poslednja izmena 1999). Preuzet iz javnog repozitorijuma [Harbour](https://github.com/harbour/core) (`tests/test.dbf`), slobodnog naslednika Clipper-a. Podaci su izmišljeni test podaci.
- **`podaci\magacin.dbf` + `magacin.dbt`**: **izmišljen** srpski magacin iz 1995–2001. Napravila ga je skripta `napravi_test_dbf.py`, bajt po bajt, kao dBase III+ sa memo poljem. Namerno ima probleme kakve nose pravi stari fajlovi:
  - DOS kodna strana 852 (YU latinica), a u zaglavlju nije upisana;
  - 3 obrisana zapisa (u dBase-u `DELETE` bez `PACK`, pa su i dalje u fajlu);
  - datum 30. 2. 1999, prazan datum, broj koji se nije uklopio u polje (`**********`), logičko polje `?` i prazna cena.

## Pokretanje: `.dbf` (XAMPP)

1. U XAMPP-u pokreni **MySQL**.
2. U ovom folderu, samo prvi put:

   ```
   pip install -r requirements.txt
   ```

3. Clipper uzorak: prvo pogledaj, pa uvezi, pa proveri:

   ```
   python dbf_u_mysql.py podaci\test.dbf --pregled
   python dbf_u_mysql.py podaci\test.dbf
   python provera_dbf.py podaci\test.dbf
   ```

4. Srpski magacin. Prvo **bez** kodne strane, da vidiš šta alat kaže:

   ```
   python dbf_u_mysql.py podaci\magacin.dbf --pregled
   ```

   Ispisaće isti naziv u pet kodnih strana. Ispravno je samo u `cp852`. Onda:

   ```
   python dbf_u_mysql.py podaci\magacin.dbf --kodna-strana cp852
   python provera_dbf.py podaci\magacin.dbf --kodna-strana cp852
   ```

5. Pogledaj bazu **`stari_formati`** u phpMyAdmin-u (`http://localhost/phpmyadmin`).

Podrazumevano: `127.0.0.1:3306`, korisnik `root`, prazna lozinka, baza `stari_formati`.
Drugačije: `--host`, `--port`, `--korisnik`, `--lozinka`, `--baza`, a ime tabele sa `--tabela`.

Ako tabela već postoji, uvoz ne radi ništa. Ponovni uvoz (stari sadržaj se briše) radi se sa `--prepisi`.

## Pravila pretvaranja (`.dbf`)

| U `.dbf`-u | U MySQL-u | Zašto |
| --- | --- | --- |
| `C` tekst | `VARCHAR(dužina)`, razmaci na kraju se skidaju, prazno → `NULL` | dBase dopunjava tekst razmacima do dužine polja |
| `N` / `F` bez decimala | `INT` (do 9 cifara) ili `BIGINT` | |
| `N` / `F` sa decimalama | `DECIMAL(dužina, decimale)` | tačno kao u fajlu; `float` bi 12,1 pretvorio u 12,0999… |
| `D` datum | `DATE`; prazan → `NULL` | |
| `L` logičko | `TINYINT(1)`: T/Y → 1, F/N → 0, `?` → `NULL` | |
| `M` memo (`.dbt`/`.fpt`) | `MEDIUMTEXT` | |
| broj zapisa | kolona `_red` (primarni ključ) | čuva redosled iz fajla |
| obrisan zapis (`*`) | uvozi se, kolona `_obrisan = 1` | obrisan zapis nije nestao; klijent odlučuje šta s njim |

**Problemi.** Vrednost koja ne može da se pročita (nemoguć datum, `*****` u broju, slovo u broju) postaje `NULL`, ali se ne gubi bez traga. Uvoz je nabraja kao PROBLEM: red, polje, sirova vrednost i razlog. Taj spisak ide klijentu, da on kaže šta je trebalo da piše.

Biblioteka `dbfread` sama bi `*****` tiho pretvorila u prazno, a na 30. februaru prekinula ceo uvoz. Zato `dbf_zajednicko.py` ima sopstveni parser.

## Šta naučiti iz `.dbf` dela

- **Kodna strana se ne vidi u fajlu.** Pogrešna kodna strana ne javlja grešku. Sa `--kodna-strana cp1250` uvoz „uspe“, a umesto „Šećer“ u bazi piše „će†er“. Ni provera to ne hvata, jer obe strane čitaju istom pogrešnom kodnom stranom. Zato uvek prvo `--pregled`, pa očima proveriti naša slova.
- **Provera hvata sve ostalo.** Promena cene od 1 pare ili „Šećer“ → „Secer“ u bazi daju `RAZL` u kontrolnoj sumi te kolone.
- **Obrisano u dBase-u nije obrisano.** Dok se ne uradi `PACK`, zapis je u fajlu, samo označen zvezdicom.

## Access (`.mdb`, `.accdb`)

### Podaci za vežbu (`podaci\access`)

Iz javnog repozitorijuma [mdbtools/mdbtestdata](https://github.com/mdbtools/mdbtestdata):

- **`nwind.mdb`**: Microsoftov Northwind u formatu **Access 97** (Jet 3). Prodavnica sa 9 tabela: kupci, porudžbine, stavke, proizvodi, dobavljači, zaposleni sa fotografijama…, ukupno 4032 reda.
- `DateTestDatabase.mdb` (Access 2000) i `ASampleDatabase.accdb` (Access 2007+): manji fajlovi za probu drugih formata.

### Drajver: zašto 32-bitni Python

Access se čita preko Microsoft-ovog ODBC drajvera, a on nije isti na svakom računaru:

| Drajver | Čita | Napomena |
| --- | --- | --- |
| „Microsoft Access Driver (*.mdb)“, 32-bit (Jet) | Access 97 i 2000–2003 `.mdb` | deo Windows-a, ništa se ne instalira; radi samo iz **32-bitnog** Python-a |
| „Microsoft Access Driver (*.mdb, *.accdb)“, 64-bit (ACE) | `.mdb` od Access 2000 i `.accdb` | **ne** čita Access 97; ako je deo Office-a (Microsoft 365), spoljni programi dobijaju „The operating system is not presently configured to run this application“ |

Zato za `.mdb` koristimo 32-bitni Python sa Jet drajverom, instaliran pored običnog (npr. `D:\Python314-32`):

```
D:\Python314-32\python.exe -m pip install pyodbc PyMySQL
```

### Pokretanje

```
D:\Python314-32\python.exe access_u_mysql.py podaci\access\nwind.mdb --pregled
D:\Python314-32\python.exe access_u_mysql.py podaci\access\nwind.mdb
D:\Python314-32\python.exe provera_access.py podaci\access\nwind.mdb
```

Svaka Access baza dobija svoju MySQL bazu istog imena (`nwind.mdb` → baza `nwind`), a sa `--baza` može drugačije. Samo neke tabele: `--tabele "Orders,Order Details"`.

### Šta se prenosi, a šta ne

| Access | MySQL |
| --- | --- |
| Text | `VARCHAR(dužina)` |
| Memo / Long Text | `LONGTEXT` |
| Number (Byte / Integer / Long) | `TINYINT UNSIGNED` / `SMALLINT` / `INT` |
| Number (Single / Double) | `DOUBLE` |
| Currency | `DECIMAL(19,4)` |
| Date/Time | `DATETIME` (datum pre 1000. godine → `NULL` + PROBLEM) |
| Yes/No | `TINYINT(1)` |
| OLE Object (slike) | `LONGBLOB` |
| primarni ključ | ostaje primarni ključ; dodaje se `_red` (redosled) |

**Ne prenosi se:** upiti (queries), forme, izveštaji i VBA moduli. To je logika aplikacije, ne podaci, i ona se piše iznova u novoj aplikaciji. **Veze između tabela** (Relationships) drajver ne daje. Za klijenta se prepisuju ručno iz Access-a (Database Tools → Relationships) i dodaju kao strani ključevi tek kad se proveri da podaci zaista poštuju te veze.

Imena tabela i kolona ostaju ista kao u Access-u, i sa razmacima (`` `Order Details` ``). Preimenovanje dolazi kasnije, kad se pravi nova aplikacija.

### Šta naučiti iz ovoga

- **Access 97 je i dalje tu.** Novi Microsoft-ov drajver ga ne otvara, a stari 32-bitni Jet iz Windows-a ga otvara. Kod klijenta se prvo proverava verzija fajla.
- **Single broj nije „okrugao“.** Popust 0,05 u Access-u (tip Single) je zapravo 0,0500000007…, i tako se i prenosi, jer `DOUBLE` čuva tačno istu vrednost. Ako treba „lepih“ 0,05, to je odluka o podacima, a ne posao uvoza.
- **Provera hvata i slike.** Fotografije zaposlenih se porede preko SHA-256 sadržaja, pa i jedan promenjen bajt daje `RAZL`.
- **Dva nezavisna čitača.** Isti `nwind.mdb` pročitan je i Microsoft-ovim drajverom (Windows) i besplatnim mdbtools (Linux). Na 7 od 9 tabela kontrolne sume su iste, i sa slikama. Na `Order Details` poređenje je uhvatilo grešku u mdbtools-u: brojeve tipa Single čita pogrešno (popust 0,05 postaje broj blizu nule). Tabelu `Umsätze` mdbtools ne otvara zbog slova „ä“ u imenu. Zato se kod klijenta ne veruje jednom alatu: ono što je važno proveri se na dva načina.

## Odakle su podaci za vežbu

- `podaci/test.dbf`: iz javnog repozitorijuma [harbour/core](https://github.com/harbour/core) (`tests/test.dbf`).
- `podaci/access/*`: iz javnog repozitorijuma [mdbtools/mdbtestdata](https://github.com/mdbtools/mdbtestdata). Northwind je Microsoft-ova primer baza.
- `podaci/magacin.dbf` i `.dbt`: izmišljeni, pravi ih `napravi_test_dbf.py`.

Svi podaci su test podaci, bez stvarnih osoba i firmi.

## Zahtevi

Python 3.10+ i MySQL/MariaDB (XAMPP je dovoljan). Biblioteke su u `requirements.txt` (za Access: 32-bitni Python sa `pyodbc` i `PyMySQL`).
