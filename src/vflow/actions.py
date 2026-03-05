"""
Thin façade that re-exports every public action from the service modules.

main.py and tests import ``actions.*``; the real implementations live in:

- ingest_service   – ingest_shoot, ingest_report, prep_shoot, pull_shoot
- delivery_service – archive_file, create_select_file, copy_metadata_folder
- backup_service   – consolidate_files, verify_backup, list_backups,
                     restore_folder, list_duplicates, remove_duplicates
"""

from .ingest_service import (  # noqa: F401
    ingest_report,
    ingest_shoot,
    prep_shoot,
    pull_shoot,
)

from .delivery_service import (  # noqa: F401
    archive_file,
    create_select_file,
    copy_metadata_folder,
)

from .backup_service import (  # noqa: F401
    consolidate_files,
    verify_backup,
    list_backups,
    restore_folder,
    list_duplicates,
    remove_duplicates,
)

# Re-export core helpers that tests import via actions.*
from .core.patterns import (  # noqa: F401
    _extract_number_from_filename,
    _parse_range_pattern,
    _matches_pattern,
)
