import sqlite3
from pathlib import Path

# Crear carpeta si no existe
db_folder = Path("data/database")
db_folder.mkdir(parents=True, exist_ok=True)

db_path = db_folder / "barchart.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS population (
    year INTEGER,
    country TEXT,
    value REAL
)
""")

data = [
    (2000, "USA", 282.2),
    (2000, "Mexico", 97.5),
    (2000, "Canada", 30.7),

    (2001, "USA", 285.1),
    (2001, "Mexico", 99.0),
    (2001, "Canada", 31.0),

    (2002, "USA", 287.8),
    (2002, "Mexico", 100.6),
    (2002, "Canada", 31.4),
]

cursor.execute("DELETE FROM population")
cursor.executemany(
    "INSERT INTO population VALUES (?, ?, ?)",
    data
)

conn.commit()
conn.close()

print("Base de datos creada correctamente.")