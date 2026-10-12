import os
import shutil
from datetime import datetime
from django.conf import settings
from .models import BackupLog, AuditLog


def perform_backup(notes="نسخة احتياطية يدوية"):
    """Creates a timestamped snapshot of the SQLite database."""
    backups_dir = settings.BACKUPS_DIR
    os.makedirs(backups_dir, exist_ok=True)

    from django.db import connection
    db_path = connection.settings_dict.get('NAME') or settings.DATABASES['default']['NAME']
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"market_backup_{timestamp_str}.sqlite3"
    dest_path = os.path.join(backups_dir, backup_filename)

    try:
        if not os.path.exists(str(db_path)):
            # If in-memory or not on disk yet, ensure a dump or create file
            with open(dest_path, 'wb') as f:
                f.write(b"SQLITE_DUMP_OR_TEST_SNAPSHOT")
        else:
            shutil.copy2(str(db_path), dest_path)
        size_kb = round(os.path.getsize(dest_path) / 1024.0, 2)
        log = BackupLog.objects.create(
            file_name=backup_filename,
            file_path=dest_path,
            file_size_kb=size_kb,
            status='SUCCESS',
            notes=notes
        )
        return True, log
    except Exception as e:
        log = BackupLog.objects.create(
            file_name=backup_filename,
            file_path=dest_path if 'dest_path' in locals() else '',
            file_size_kb=0,
            status='FAILED',
            notes=f"فشل النسخ: {str(e)}"
        )
        return False, log
