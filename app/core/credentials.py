"""Owner-bound authenticated encryption. Rotation reads old keys, writes active key.

CREDENTIAL_KEYS is a JSON object of key IDs to Fernet keys supplied by deployment.
CREDENTIAL_ACTIVE_KEY identifies the current key. No key or plaintext is persisted.
"""
import json
import os
from cryptography.fernet import Fernet
from app.core.security import utcnow


class CredentialStore:
    def __init__(self):
        try:
            self.keys = {k: Fernet(v.encode()) for k, v in json.loads(os.environ['CREDENTIAL_KEYS']).items()}
            self.active = os.environ['CREDENTIAL_ACTIVE_KEY']
            if self.active not in self.keys:
                raise ValueError()
        except Exception:
            raise ValueError('Credential encryption is not configured') from None

    def put(self, db, owner, scope, kind, value):
        from app.models.models import CredentialMetadata, CredentialSecret
        row = db.query(CredentialMetadata).filter_by(user_id=owner, scope=scope, kind=kind).first()
        if row is None:
            row = CredentialMetadata(user_id=owner, scope=scope, kind=kind)
            db.add(row)
            db.flush()
        material = db.query(CredentialSecret).filter_by(credential_id=row.id, user_id=owner).first()
        if material is None:
            material = CredentialSecret(credential_id=row.id, user_id=owner)
            db.add(material)
        envelope = json.dumps({'owner': owner, 'scope': scope, 'kind': kind, 'value': value}).encode()
        material.ciphertext = self.keys[self.active].encrypt(envelope).decode()
        material.key_id = self.active
        row.updated_at = utcnow()
        return row

    def get(self, db, owner, scope, kind):
        from app.models.models import CredentialMetadata, CredentialSecret
        row = db.query(CredentialMetadata).filter_by(user_id=owner, scope=scope, kind=kind).first()
        if row is None:
            raise ValueError('Credential unavailable')
        material = db.query(CredentialSecret).filter_by(credential_id=row.id, user_id=owner).first()
        try:
            envelope = json.loads(self.keys[material.key_id].decrypt(material.ciphertext.encode()))
            if (envelope['owner'], envelope['scope'], envelope['kind']) != (owner, scope, kind):
                raise ValueError()
            return envelope['value']
        except Exception:
            raise ValueError('Credential unavailable') from None

    def rotate(self, db, owner, scope, kind):
        return self.put(db, owner, scope, kind, self.get(db, owner, scope, kind))


def has_credentials(db, owner, scope):
    from app.models.models import CredentialMetadata
    return db.query(CredentialMetadata).filter_by(user_id=owner, scope=scope).first() is not None


def remove_credentials(db, owner, scope):
    from app.models.models import CredentialMetadata, CredentialSecret
    for row in db.query(CredentialMetadata).filter_by(user_id=owner, scope=scope).all():
        db.query(CredentialSecret).filter_by(user_id=owner, credential_id=row.id).delete()
        db.delete(row)
