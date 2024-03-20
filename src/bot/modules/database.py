import os
import time

import mariadb
from mariadb import Connection, Cursor

con: Connection | None = None


def connect():
    global con
    print("Connecting to database...", end=" ")
    while True:
        try:
            con = mariadb.connect(
                user=os.environ['DB_USER'],
                password=os.environ['DB_PASSWORD'],
                host=os.environ.get('DB_HOST') or "127.0.0.1",
                port=int(os.environ.get('DB_PORT') or 3306),
                database=os.environ['DB_DATABASE']
            )
            con.auto_reconnect = True
            break
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)
    print("Done!")


def get_cursor() -> Cursor:
    return con.cursor(buffered=True)


connect()
