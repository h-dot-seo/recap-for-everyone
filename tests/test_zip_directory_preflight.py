"""Directory-only entry budgets preserve one immutable archive snapshot."""
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from recaplib.zip_preflight import check_directory
from recaplib.inspect_web_zip import inspect_web_zip
from recaplib import prepare_web_export as p


def archive_bytes(count=1, content=b'[]'):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for i in range(count): archive.writestr('conversations-'+str(i)+'.json',content)
    return out.getvalue()


def zip64(raw):
    end=len(raw)-22
    values=struct.unpack_from('<4s4H2LH',raw,end)
    _,disk,cd_disk,on_disk,total,size,offset,comment=values
    record=struct.pack('<4sQ2H2L4Q',b'PK\x06\x06',44,45,45,0,0,total,total,size,offset)
    locator=struct.pack('<4sLQL',b'PK\x06\x07',0,end,1)
    tail=struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,65535,65535,0xffffffff,0xffffffff,0)
    return raw[:end]+record+locator+tail


class DirectoryPreflightTests(unittest.TestCase):
    def test_nested_attachment_signatures_do_not_count_as_entries(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            archive.writestr('conversations.json','[]')
            archive.writestr('synthetic-attachment.bin',b'PK\x01\x02'*1001)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.zip';path.write_bytes(out.getvalue())
            with patch.object(p,'MAX_ENTRIES',2):
                result=inspect_web_zip(path)
            self.assertEqual(result['total_entries'],2)
            self.assertEqual(result['total_candidates'],1)

    def test_normal_empty_comment_prefix_and_zip64(self):
        for raw in [archive_bytes(0),archive_bytes(),b'synthetic-prefix'+archive_bytes(),
                    zip64(archive_bytes()),b'synthetic-prefix'+zip64(archive_bytes())]:
            with self.subTest(length=len(raw)):
                check_directory(raw,2)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:self.assertLessEqual(len(archive.infolist()),1)
        raw=bytearray(archive_bytes());struct.pack_into('<H',raw,len(raw)-2,5);raw+=b'hello'
        check_directory(raw,1)

    def test_declared_entry_limit_before_zipfile(self):
        raw=bytearray(archive_bytes());struct.pack_into('<HH',raw,len(raw)-14,2,2)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.zip';path.write_bytes(raw)
            with patch.object(p,'MAX_ENTRIES',1),patch.object(zipfile,'ZipFile',side_effect=AssertionError('must reject first')):
                with self.assertRaisesRegex(ValueError,'1000-entry'):inspect_web_zip(path)

    def test_actual_entry_limit_even_when_declared_count_lies(self):
        raw=bytearray(archive_bytes(2));struct.pack_into('<HH',raw,len(raw)-14,1,1)
        with self.assertRaisesRegex(ValueError,'1000-entry'):check_directory(raw,1)
        with self.assertRaises(zipfile.BadZipFile):check_directory(raw,2)

    def test_directory_sizes_offsets_and_truncations(self):
        original=archive_bytes()
        variants=[original[:10],original[:-1],b'not zip']
        for field,value in [(12,0xffffffff),(16,0xffffffff),(20,65535),(4,1)]:
            raw=bytearray(original);struct.pack_into('<H' if field in (20,4) else '<L',raw,len(raw)-22+field,value);variants.append(raw)
        # A central entry's filename length runs beyond the declared directory.
        raw=bytearray(original);cd=raw.index(b'PK\x01\x02');struct.pack_into('<H',raw,cd+28,65535);variants.append(raw)
        for raw in variants:
            with self.subTest(length=len(raw)),self.assertRaises(zipfile.BadZipFile):check_directory(raw,1000)

    def test_zip64_limits_and_malformed_locator(self):
        raw=zip64(archive_bytes(2))
        with self.assertRaisesRegex(ValueError,'1000-entry'):check_directory(raw,1)
        for offset,value in [(-26,2),(-34,999999),(-70,43)]:
            changed=bytearray(raw)
            # locator disks, locator record offset, record payload size respectively
            if offset==-26:struct.pack_into('<L',changed,len(changed)+offset,value)
            elif offset==-34:struct.pack_into('<Q',changed,len(changed)+offset,value)
            else:struct.pack_into('<Q',changed,len(changed)-22-20-56+4,value)
            with self.subTest(offset=offset),self.assertRaises(zipfile.BadZipFile):check_directory(changed,2)

    def test_hash_mismatch_still_precedes_directory_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.zip';path.write_bytes(b'invalid zip')
            with patch.object(p,'check_directory',side_effect=AssertionError('hash first')):
                with self.assertRaisesRegex(ValueError,'changed after inspection'):inspect_web_zip(path,expected_archive_sha256='0'*64)
                with self.assertRaisesRegex(ValueError,'changed after inspection'):p.prepare_web_export(path,'conversations.json',Path(tmp)/'no',expected_archive_sha256='0'*64)
