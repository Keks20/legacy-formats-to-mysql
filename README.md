# legacy-formats-to-mysql

Small Python tools that move old databases into MySQL, the kind real clients still bring:
**dBase / Clipper / FoxPro (`.dbf`)** and **Microsoft Access (`.mdb`, `.accdb`)**.
Each import has a matching checker that proves, with checksums, that nothing was lost or changed.

They are part of the case study
[Modernizing POKSI without stopping it](https://github.com/Keks20/poksipp-modernization/blob/main/CASE_STUDY.md).
The tools work with any `.dbf` or Access file, not only with the samples in `podaci`.

*Srpska verzija uputstva: [README.sr.md](README.sr.md).*

> The command-line options and the output are in Serbian. See [Serbian words in the tools](#serbian-words-in-the-tools) at the end.

| File | What it does |
| --- | --- |
| `dbf_u_mysql.py` | imports one `.dbf` file into a MySQL table (or only previews it with `--pregled`) |
| `provera_dbf.py` | compares the `.dbf` file and the table, column by column, with checksums |
| `dbf_zajednicko.py` | conversion rules shared by both scripts |
| `napravi_test_dbf.py` | builds `podaci\magacin.dbf` (invented, see below) |
| `access_u_mysql.py` | imports a whole Access database (all tables) into a MySQL database of the same name |
| `provera_access.py` | compares Access and MySQL, table by table and column by column |
| `access_zajednicko.py` | driver choice, column types, reading |
| `kontrola.py` | checksums and the MySQL connection, shared by everything |

## Sample data (`.dbf`)

- **`podaci\test.dbf`**: a classic Clipper sample (dBase III, 500 employees, last changed in 1999), taken from the public [Harbour](https://github.com/harbour/core) repository (`tests/test.dbf`), the free successor to Clipper. The data is invented test data.
- **`podaci\magacin.dbf` + `magacin.dbt`**: an **invented** Serbian warehouse from 1995–2001. The script `napravi_test_dbf.py` writes it byte by byte as dBase III+ with a memo field. On purpose, it has the problems real old files have:
  - DOS code page 852 (Serbian Latin), not recorded in the header;
  - 3 deleted records (in dBase, `DELETE` without `PACK`, so they are still in the file);
  - the date 30 February 1999, an empty date, a number too big for its field (`**********`), a logical field set to `?` and an empty price.

## Running: `.dbf` (XAMPP)

1. Start **MySQL** in XAMPP.
2. In this folder, the first time only:

   ```
   pip install -r requirements.txt
   ```

3. The Clipper sample: preview first, then import, then check:

   ```
   python dbf_u_mysql.py podaci\test.dbf --pregled
   python dbf_u_mysql.py podaci\test.dbf
   python provera_dbf.py podaci\test.dbf
   ```

4. The Serbian warehouse. First **without** a code page, to see what the tool says:

   ```
   python dbf_u_mysql.py podaci\magacin.dbf --pregled
   ```

   It prints the same product name in five code pages. Only `cp852` is correct. Then:

   ```
   python dbf_u_mysql.py podaci\magacin.dbf --kodna-strana cp852
   python provera_dbf.py podaci\magacin.dbf --kodna-strana cp852
   ```

5. Look at the **`stari_formati`** database in phpMyAdmin (`http://localhost/phpmyadmin`).

Defaults: `127.0.0.1:3306`, user `root`, empty password, database `stari_formati`.
To change them: `--host`, `--port`, `--korisnik`, `--lozinka`, `--baza`; the table name with `--tabela`.

If the table already exists, the import does nothing. To import again (the old content is deleted), add `--prepisi`.

## Conversion rules (`.dbf`)

| In the `.dbf` | In MySQL | Why |
| --- | --- | --- |
| `C` text | `VARCHAR(length)`, trailing spaces removed, empty → `NULL` | dBase pads text with spaces to the field length |
| `N` / `F` without decimals | `INT` (up to 9 digits) or `BIGINT` | |
| `N` / `F` with decimals | `DECIMAL(length, decimals)` | exactly as in the file; a `float` would turn 12.1 into 12.0999… |
| `D` date | `DATE`; empty → `NULL` | |
| `L` logical | `TINYINT(1)`: T/Y → 1, F/N → 0, `?` → `NULL` | |
| `M` memo (`.dbt`/`.fpt`) | `MEDIUMTEXT` | |
| record number | column `_red` (primary key) | keeps the order from the file |
| deleted record (`*`) | imported, column `_obrisan = 1` | a deleted record is not gone; the client decides what to do with it |

**Problems.** A value that cannot be read (an impossible date, `*****` in a number, a letter in a number) becomes `NULL`, but it does not disappear without a trace. The import lists it as a PROBLEM: row, field, raw value and reason. That list goes to the client, who says what it should have been.

The `dbfread` library on its own would silently turn `*****` into an empty value and stop the whole import on 30 February. That is why `dbf_zajednicko.py` has its own parser.

## What the `.dbf` part teaches

- **The code page is not in the file.** A wrong code page gives no error. With `--kodna-strana cp1250` the import "succeeds", and the database says "će†er" instead of "Šećer". Even the checker cannot catch it, because both sides read with the same wrong code page. So always preview first (`--pregled`) and check the local letters by eye.
- **The checker catches everything else.** Changing a price by 0.01 or "Šećer" → "Secer" in the database gives `RAZL` for that column's checksum.
- **Deleted in dBase is not deleted.** Until someone runs `PACK`, the record is still in the file, only marked with an asterisk.

## Access (`.mdb`, `.accdb`)

### Sample data (`podaci\access`)

From the public [mdbtools/mdbtestdata](https://github.com/mdbtools/mdbtestdata) repository:

- **`nwind.mdb`**: Microsoft's Northwind in **Access 97** format (Jet 3). A shop with 9 tables (customers, orders, order lines, products, suppliers, employees with photos…), 4,032 rows in total.
- `DateTestDatabase.mdb` (Access 2000) and `ASampleDatabase.accdb` (Access 2007+): smaller files for trying other formats.

### The driver: why 32-bit Python

Access is read through Microsoft's ODBC driver, and it is not the same on every PC:

| Driver | Reads | Note |
| --- | --- | --- |
| "Microsoft Access Driver (*.mdb)", 32-bit (Jet) | Access 97 and 2000–2003 `.mdb` | part of Windows, nothing to install; works only from **32-bit** Python |
| "Microsoft Access Driver (*.mdb, *.accdb)", 64-bit (ACE) | `.mdb` from Access 2000 on, and `.accdb` | does **not** read Access 97; when it comes with Office (Microsoft 365), outside programs get "The operating system is not presently configured to run this application" |

So for `.mdb` files the tools use 32-bit Python with the Jet driver, installed next to the normal one (e.g. `D:\Python314-32`):

```
D:\Python314-32\python.exe -m pip install pyodbc PyMySQL
```

### Running

```
D:\Python314-32\python.exe access_u_mysql.py podaci\access\nwind.mdb --pregled
D:\Python314-32\python.exe access_u_mysql.py podaci\access\nwind.mdb
D:\Python314-32\python.exe provera_access.py podaci\access\nwind.mdb
```

Each Access database gets its own MySQL database of the same name (`nwind.mdb` → database `nwind`); `--baza` picks another name. Only some tables: `--tabele "Orders,Order Details"`.

### What moves and what does not

| Access | MySQL |
| --- | --- |
| Text | `VARCHAR(length)` |
| Memo / Long Text | `LONGTEXT` |
| Number (Byte / Integer / Long) | `TINYINT UNSIGNED` / `SMALLINT` / `INT` |
| Number (Single / Double) | `DOUBLE` |
| Currency | `DECIMAL(19,4)` |
| Date/Time | `DATETIME` (a date before year 1000 → `NULL` + PROBLEM) |
| Yes/No | `TINYINT(1)` |
| OLE Object (pictures) | `LONGBLOB` |
| primary key | stays the primary key; `_red` (row order) is added |

**Not moved:** queries, forms, reports and VBA modules. They are application logic, not data, and get rewritten in the new application. The driver does not report **table relationships** either. For a client they are copied by hand from Access (Database Tools → Relationships) and added as foreign keys only after checking that the data really follows them.

Table and column names stay as they are in Access, spaces included (`` `Order Details` ``). Renaming comes later, when the new application is built.

### What this teaches

- **Access 97 is still around.** Microsoft's new driver cannot open it; the old 32-bit Jet driver in Windows can. With a client, check the file version first.
- **A Single is not "round".** A 0.05 discount in Access (type Single) is really 0.0500000007…, and that is what moves, because `DOUBLE` keeps exactly the same value. If the client wants a "clean" 0.05, that is a data decision, not the import's job.
- **The checker covers pictures too.** Employee photos are compared by the SHA-256 of their content, so a single changed byte gives `RAZL`.
- **Two independent readers.** The same `nwind.mdb` was read with Microsoft's driver (Windows) and with the free mdbtools (Linux). On 7 of the 9 tables the checksums match, photos included. On `Order Details` the comparison caught a bug in mdbtools: it misreads Single numbers (a 0.05 discount comes out close to zero). mdbtools cannot open the `Umsätze` table at all, because of the "ä" in its name. So with a client, no single tool is trusted: what matters is checked two ways.

## Where the sample data comes from

- `podaci/test.dbf`: from the public [harbour/core](https://github.com/harbour/core) repository (`tests/test.dbf`).
- `podaci/access/*`: from the public [mdbtools/mdbtestdata](https://github.com/mdbtools/mdbtestdata) repository. Northwind is a Microsoft sample database.
- `podaci/magacin.dbf` and `.dbt`: invented, built by `napravi_test_dbf.py`.

All of it is test data, with no real people or companies.

## Requirements

Python 3.10+ and MySQL/MariaDB (XAMPP is enough). The libraries are in `requirements.txt` (for Access: 32-bit Python with `pyodbc` and `PyMySQL`).

## Serbian words in the tools

| In the tools | Meaning |
| --- | --- |
| `--pregled` | preview only, MySQL is not touched |
| `--kodna-strana cp852` | code page of the `.dbf` file |
| `--prepisi` | overwrite: delete the existing tables and import again |
| `--tabela` / `--tabele` | table name / list of tables |
| `--baza` | MySQL database name |
| `--korisnik`, `--lozinka` | MySQL user, password |
| `podaci` | sample data folder |
| `_red`, `_obrisan` | row number, deleted flag |
| `OK` / `RAZL` | match / difference |
| `PROBLEM` | value that could not be read and became `NULL` |
| `SVE SE POKLAPA` | everything matches |
