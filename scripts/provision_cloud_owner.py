"""Owner-run Render console enrollment. Never run unattended or pass passwords.

Creates a NEW account, never upgrades the legacy demo. Secrets stay on Render.
No publishing or migrations. Requires the previously migrated persistent schema.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from cryptography.hazmat.primitives.twofactor import InvalidToken


def enroll(database, email, password, secret, counter, runtime_file):
    """Atomic account + encrypted MFA insertion after a verified encrypted backup."""
    runtime_file=Path(runtime_file)
    if runtime_file.exists():
        raise ValueError('Runtime file already exists; refusing to replace credentials')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(email)>254:
        raise ValueError('Invalid email')
    if len(password)<16 or len(password.encode())>72:
        raise ValueError('Password must contain at least 16 characters and at most 72 UTF-8 bytes')
    os.umask(0o077)
    db=sqlite3.connect(str(database),timeout=15)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failed')
        if db.execute('SELECT COUNT(*) FROM credential_secrets').fetchone()[0]:
            raise ValueError('Existing encrypted credentials require a reviewed key-preserving setup')
        if db.execute('SELECT id FROM users WHERE lower(email)=?',(email.casefold(),)).fetchone():
            raise ValueError('Email already exists; no existing account was changed')
        key=Fernet.generate_key(); cipher=Fernet(key)
        snapshot=sqlite3.connect(':memory:');db.backup(snapshot)
        raw=snapshot.serialize();snapshot.close()
        encrypted=cipher.encrypt(raw)
        if hashlib.sha256(cipher.decrypt(encrypted)).digest()!=hashlib.sha256(raw).digest():raise ValueError('Encrypted backup verification failed')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        backup=runtime_file.parent/('before-owner-'+stamp+'.db.fernet')
        with backup.open('xb') as f:f.write(encrypted)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT id FROM users WHERE lower(email)=?',(email.casefold(),)).fetchone():raise ValueError('Account appeared concurrently')
        now=datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        cur=db.execute('INSERT INTO users(email,username,hashed_password,company_name,is_active,is_demo,phone_verified,created_at,updated_at) VALUES(?,?,?,?,1,0,0,?,?)',
            (email.casefold(),'ET EXPO Owner',bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),'ET EXPO INC',now,now))
        owner=cur.lastrowid
        scope='cloud-owner-mfa-v1';kind='record'
        cur=db.execute('INSERT INTO credential_metadata(user_id,scope,kind,created_at,updated_at) VALUES(?,?,?,?,?)',(owner,scope,kind,now,now))
        value=json.dumps(dict(secret=secret,last_counter=counter))
        envelope=json.dumps(dict(owner=owner,scope=scope,kind=kind,value=value)).encode()
        db.execute('INSERT INTO credential_secrets(user_id,credential_id,key_id,ciphertext) VALUES(?,?,?,?)',(owner,cur.lastrowid,'cloud-v1',cipher.encrypt(envelope).decode()))
        config=dict(SECRET_KEY=secrets.token_urlsafe(48),CREDENTIAL_KEYS=json.dumps({'cloud-v1':key.decode()}),CREDENTIAL_ACTIVE_KEY='cloud-v1',
                    DATABASE_URL='sqlite:///'+str(Path(database).resolve()),MARKETING_OWNER_ID=str(owner))
        # Keep the backup key recoverable even if the final DB commit fails.
        with runtime_file.open('x',encoding='utf-8') as f:json.dump(config,f)
        os.chmod(runtime_file,0o600)
        db.commit()
        return dict(owner_id=owner,backup_sha256=hashlib.sha256(encrypted).hexdigest(),backup_integrity='PASS',runtime_file=str(runtime_file))
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--email',required=True);args=parser.parse_args()
    database=Path('/opt/render/project/src/data/marketing.db')
    runtime=database.parent/'cloud-runtime.json'
    print('PRIVATE OWNER SETUP. Creates a new cloud Owner; existing accounts and data remain unchanged.')
    print('Use a NEW password that has not appeared in chat. Requires an authenticator app.')
    input('Owner: press Enter to start private setup (the assistant must stop observing now): ')
    password=getpass.getpass('New password (16+ characters, hidden): ')
    if password!=getpass.getpass('Repeat password (hidden): '):raise ValueError('Passwords differ')
    if len(password)<16 or len(password.encode())>72:raise ValueError('Password length rejected')
    secret=base64.b32encode(secrets.token_bytes(20)).decode()
    print('In your authenticator choose Add account > Enter setup key. Account: ET EXPO Marketing.')
    print('Type: Time based, 6 digits, 30 seconds. Setup key (PRIVATE): '+secret)
    code=getpass.getpass('Enter the current 6-digit authenticator code (hidden): ')
    otp=TOTP(base64.b32decode(secret),6,hashes.SHA1(),30);counter=None
    for step in (int(time.time()//30),int(time.time()//30)-1,int(time.time()//30)+1):
        try:otp.verify(code.encode(),step*30);counter=step;break
        except InvalidToken:pass
    if counter is None:raise ValueError('Authenticator verification failed; account not created')
    result=enroll(database,args.email,password,secret,counter,runtime)
    print('\033[2J\033[3J\033[H',end='')
    print('OWNER_SETUP_COMPLETE '+json.dumps(result))
    print('Do not share the setup key or password. Inform Codex that setup completed.')


if __name__=='__main__':
    try:main()
    except Exception:
        print('\033[2J\033[3J\033[H',end='')
        print('Owner setup was not completed. No credential details are displayed. Do not retry over an existing runtime file.')
        raise SystemExit(1)
