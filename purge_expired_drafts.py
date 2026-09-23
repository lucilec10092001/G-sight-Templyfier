"""IT maintenance: delete expired personal drafts; preserve all other documents.

Run on the application host with its server environment and service account.
No source files or consumer values are loaded. Corrupt records stop the transaction.
"""
from datetime import datetime, timezone
import json
from templyfier import server_storage as storage
from templyfier.drafts import _validate_store


def purge_expired():
    if not storage.server_mode():raise ValueError('This maintenance command requires server mode.')
    now=datetime.now(timezone.utc)
    connection=storage._connect()
    removed=0
    try:
        connection.execute('BEGIN IMMEDIATE')
        records=connection.execute("SELECT scope,payload,revision FROM documents WHERE name='drafts'").fetchall()
        for scope,payload,revision in records:
            if not scope.startswith('personal:'):raise ValueError('Unexpected draft workspace; no records changed.')
            document=_validate_store(json.loads(payload))
            active={key:record for key,record in document['drafts'].items() if datetime.fromisoformat(record['expires'])>now}
            count=len(document['drafts'])-len(active)
            if count:
                document['drafts']=active;revision+=1;removed+=count
                connection.execute("UPDATE documents SET payload=?,revision=? WHERE scope=? AND name='drafts'",(json.dumps(document,ensure_ascii=False,sort_keys=True),revision,scope))
                connection.execute('INSERT INTO audit(timestamp,actor,scope,action,revision) VALUES (?,?,?,?,?)',(now.isoformat(timespec='seconds'),'it-maintenance',scope,'draft_expiry',revision))
        connection.commit()
        return removed
    finally:
        if connection.in_transaction:connection.rollback()
        connection.close()


if __name__=='__main__':
    print(f'Expired personal drafts removed: {purge_expired()}')
