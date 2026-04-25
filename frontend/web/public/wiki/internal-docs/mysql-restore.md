# MySQL Restore Procedure

> When you need this, you'll be stressed. Read all the way through once before
> typing anything.

The daily backup script `mysql_backup.py` ships compressed `mysqldump` files
to `cos://doctor-ai-backups-1408751198/mysql-daily/` and lets a 90-day
lifecycle rule auto-expire them. To recover from data loss:

## 1. Pick the backup to restore

```bash
# List available backups (most recent first)
.venv/bin/python -c "
from qcloud_cos import CosConfig, CosS3Client
import configparser, os
cp = configparser.ConfigParser(); cp.read(os.path.expanduser('~/.tccli/credential'))
client = CosS3Client(CosConfig(
    Region='ap-shanghai',
    SecretId=cp.get('default', 'secretId'),
    SecretKey=cp.get('default', 'secretKey'),
))
resp = client.list_objects(Bucket='doctor-ai-backups-1408751198', Prefix='mysql-daily/')
for o in sorted(resp.get('Contents', []), key=lambda x: x['Key'], reverse=True)[:10]:
    print(f\"  {o['LastModified']}  {int(o['Size']):>12,}B  {o['Key']}\")
"
```

Pick the one you want — usually the most recent `*.sql.gz` from before the
incident.

## 2. Download the chosen backup

```bash
KEY="mysql-daily/doctor_ai_20260425_031700.sql.gz"   # ← change this
.venv/bin/python -c "
from qcloud_cos import CosConfig, CosS3Client
import configparser, os, sys
cp = configparser.ConfigParser(); cp.read(os.path.expanduser('~/.tccli/credential'))
client = CosS3Client(CosConfig(
    Region='ap-shanghai',
    SecretId=cp.get('default', 'secretId'),
    SecretKey=cp.get('default', 'secretKey'),
))
client.download_file(
    Bucket='doctor-ai-backups-1408751198',
    Key='$KEY',
    DestFilePath='/tmp/restore.sql.gz',
)
print('downloaded:', '/tmp/restore.sql.gz')
"
ls -lh /tmp/restore.sql.gz
```

## 3. Decide: in-place restore or fresh sandbox?

**STRONGLY prefer the sandbox approach** unless prod is already known-broken
and you cannot make it worse. Restoring on top of a partially-working
database can compound the damage.

### 3a. Sandbox restore (recommended)

Spin up a temporary mysql container, restore into it, inspect, *then* decide
how to merge or swap.

```bash
# 1. Run a sandbox MySQL on a different port so it doesn't conflict with prod
sudo docker run -d --name mysql-restore \
  -e MYSQL_ROOT_PASSWORD='Restore_Sandbox_Pwd' \
  -p 127.0.0.1:3307:3306 \
  mysql:8.0

# wait ~15s for it to initialize
until sudo docker exec mysql-restore mysqladmin ping -uroot -pRestore_Sandbox_Pwd 2>/dev/null | grep -q alive; do
  sleep 2
done

# 2. Restore into it
gunzip -c /tmp/restore.sql.gz \
  | sudo docker exec -i mysql-restore mysql -uroot -pRestore_Sandbox_Pwd

# 3. Connect from your laptop to inspect (via SSH tunnel or directly)
sudo docker exec -it mysql-restore mysql -uroot -pRestore_Sandbox_Pwd doctor_ai
# > SELECT COUNT(*) FROM doctors;
# > SELECT COUNT(*) FROM patients;
# etc.

# 4. When done inspecting, decide:
#   - Merge specific tables to prod (mysqldump from sandbox → mysql to prod)
#   - Swap entire DB to prod (see 3b)
#   - Discard sandbox: sudo docker rm -f mysql-restore
```

### 3b. In-place restore (last resort)

Only if prod is unrecoverable and you have a clean dump.

```bash
# 1. Stop the backend so no writes corrupt the restore
sudo systemctl stop doctor-ai-backend

# 2. Drop the doctor_ai database (irreversible! make sure backup is good)
sudo docker exec doctor-ai-mysql mysql -uroot -p"$(sudo docker exec doctor-ai-mysql printenv MYSQL_ROOT_PASSWORD)" \
  -e 'DROP DATABASE doctor_ai;'

# 3. Restore from the dump
gunzip -c /tmp/restore.sql.gz \
  | sudo docker exec -i doctor-ai-mysql mysql -uroot -p"$(sudo docker exec doctor-ai-mysql printenv MYSQL_ROOT_PASSWORD)"

# 4. Restart backend
sudo systemctl start doctor-ai-backend

# 5. Verify
curl https://api.doctoragentai.cn/healthz
sudo docker exec doctor-ai-mysql mysql -uroot -p"$(sudo docker exec doctor-ai-mysql printenv MYSQL_ROOT_PASSWORD)" \
  doctor_ai -e 'SHOW TABLES; SELECT COUNT(*) FROM doctors;'
```

## 4. After-action

- Note in the incident log when you restored from and what you restored to
- If you used the in-place path, immediately trigger a fresh backup so the
  next restore-window starts clean: `/home/ubuntu/doctor-ai-agent/deploy/tencent/mysql_backup.py`
- Investigate root cause (corrupted disk? deleted by mistake? container
  crash?) so you can prevent recurrence

## 5. Common gotchas

- **`--all-databases` includes the `mysql.user` table.** Restoring resets
  user accounts and passwords. The container's `MYSQL_ROOT_PASSWORD` env
  is set on container start and *not* reapplied — if the dump's mysql.user
  has a different root password, you may lock yourself out. The current
  prod root password is stored in the container env (`docker exec
  doctor-ai-mysql printenv MYSQL_ROOT_PASSWORD`) and the dump should
  match it.
- **GTID / binlog state** is included in the dump header. If you restore
  to a fresh server, that's fine. If restoring to a server that's been
  used for replication, you may need `RESET MASTER` first.
- **Character set** — dump is UTF-8; if your client/terminal isn't,
  Chinese text in patient records will look wrong but the DB is fine.
- **Foreign keys** — `mysqldump` adds `SET FOREIGN_KEY_CHECKS=0` at the
  top, so dependency order doesn't matter on restore.
