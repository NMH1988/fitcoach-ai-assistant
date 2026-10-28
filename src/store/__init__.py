"""The store of signed-in users' data: SQLite with the authorisation inside it (T9.6, D13, D16).

`db` opens and migrates the file, `schema` holds the tables, `values` checks what is written,
`access` decides who may read whose data, `users` holds accounts, relationships and consents,
`records` the health records, `reviews` the weekly reviews, and `my_data` exports and deletes all of
a user's rows. Every query is a constant string with `?` parameters (tests/test_store_sql_scan.py).
The Capstone replaces this package with PostgreSQL.
"""
