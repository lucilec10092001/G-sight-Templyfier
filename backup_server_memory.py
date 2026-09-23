"""IT-only local SQLite backup. OS access required; no credentials in this script."""
import argparse
from pathlib import Path
import sqlite3
import time


def backup_database(database, output):
    database, output = Path(database), Path(output)
    if not database.is_absolute() or not output.is_absolute():
        raise ValueError('Les chemins de base et de sauvegarde doivent être absolus.')
    if not database.is_file() or not output.parent.is_dir():
        raise ValueError('La base source et le dossier de sauvegarde doivent exister.')
    if database.resolve() == output.resolve():
        raise ValueError('La sauvegarde doit être distincte de la base active.')
    # Exclusive creation: never overwrite any backup or the active database.
    with output.open('xb'):
        pass
    source = destination = None
    try:
        source = sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
        destination = sqlite3.connect(output,timeout=10)
        started = time.monotonic()
        def progress(status, remaining, total):
            if time.monotonic()-started > 30:
                raise TimeoutError('Sauvegarde interrompue après 30 secondes ; réessaie à un moment moins chargé.')
        source.backup(destination, pages=128, progress=progress, sleep=.05)
        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Intégrité de la sauvegarde non confirmée.')
    except Exception:
        if destination is not None:
            destination.close(); destination=None
        output.unlink()  # Only the file exclusively created by this invocation.
        raise
    finally:
        if source is not None: source.close()
        if destination is not None: destination.close()
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Sauvegarde cohérente SQLite pour l’IT ; destination nouvelle uniquement.')
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    args=parser.parse_args()
    print(backup_database(args.database,args.output))
