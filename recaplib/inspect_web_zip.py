"""Read-only metadata inventory of conventionally named web conversation parts."""
from collections import Counter
import io
from pathlib import PurePosixPath
import re
import zipfile
from recaplib import prepare_web_export as preparation

_NAME = re.compile(r'conversations(?:[-_]?([0-9]+))?\.json', re.IGNORECASE)


def inspect_web_zip(path, limit=50, offset=0, expected_archive_sha256=None):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('limit must be 1..100 and offset must be an integer in 0..9223372036854775807')
    preparation._validate_expected_archive_sha256(expected_archive_sha256)
    raw = preparation.archive_bytes(path)
    archive_digest = preparation._checked_archive_sha256(raw, expected_archive_sha256)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > preparation.MAX_ENTRIES:
                raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
            names = Counter(entry.filename for entry in entries)
            candidates = []
            for index, entry in enumerate(entries):
                match = _NAME.fullmatch(PurePosixPath(entry.filename).name)
                if match is None:
                    continue
                problem = preparation.member_problem(entry)
                if names[entry.filename] != 1:
                    problem = ('DUPLICATE_MEMBER', 'member name identifies multiple ZIP entries')
                candidates.append(dict(member=entry.orig_filename, archive_entry_index=index,
                                       numbered_part_hint=match.group(1),
                                       compressed_bytes=entry.compress_size, declared_bytes=entry.file_size,
                                       metadata_eligible=problem is None, reason_code=problem[0] if problem else None,
                                       duplicate_name_count=names[entry.filename],
                                       content_validation='NOT_PERFORMED'))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError('invalid or unsupported ZIP archive metadata') from error
    page = candidates[offset:offset+limit]
    return dict(schema='recap.web-zip-candidates.v1', archive_sha256=archive_digest,
                archive_bytes=len(raw), total_entries=len(entries), total_candidates=len(candidates),
                other_entries_not_listed=len(entries)-len(candidates), limit=limit, offset=offset,
                next_offset=offset+len(page) if offset+len(page)<len(candidates) else None,
                candidates=page, candidate_order='central-directory order, not part chronology',
                members_decompressed=False, database_access=False, files_written=False,
                parts_completeness='NOT_ASSESSED', remote_mutation=False,
                warning='PRIVATE FILENAMES. Names and declared sizes only; CRC, JSON shape, completeness and authenticity are not checked. Select an exact member for separate preparation; nothing is automatically extracted.')
