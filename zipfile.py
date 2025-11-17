# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import struct
from micropython import const
from binascii import crc32
from collections import OrderedDict
from zlib import decompress

# Constants
SEEK_SET = const(0)
SEEK_CUR = const(1)
SEEK_END = const(2)
ZIP_WBITS = const(-15)
COMP_NONE = const(0)
COMP_DEF = const(8)

# ZIP structures
EOCD_SIG = b'PK\x05\x06'
EOCD_STRUCT = '<4s4H2LH'
EOCD_SIZE = struct.calcsize(EOCD_STRUCT)
CD_F_H_SIG = b'PK\x01\x02'
CD_F_H_STRUCT = '<4s4B4H3L5H2L'
CD_F_H_SIZE = struct.calcsize(CD_F_H_STRUCT)
LOCAL_F_H_STRUCT = '<4s2B4HL2L2H'
LOCAL_F_H_SIZE = struct.calcsize(LOCAL_F_H_STRUCT)


class BadZipFile(Exception):
    pass


class ZipInfo:
    def __init__(self, cd_header_data):
        self.name = ''  # Overriden by ZipFile
        (sig,
         _, _, _, _,  # Compressor and min version, we don't care
         _,  # General purpose bit flag?
         self.compress_method,
         self.last_mod_time,
         self.last_mod_date,
         self.crc32,
         self.compressed_size,
         self.size,
         self.filename_len,
         self.extra_field_len,
         self.comment_len,
         _,  # Disk number, we only support single part ZIPs
         _, _,  # File attributes, we don't care
         self.offset) = struct.unpack(CD_F_H_STRUCT, cd_header_data)
        if sig != CD_F_H_SIG:
            raise BadZipFile(
                "Central directory entry signature mismatch, ZIP corrupt?")

    @property
    def compressed(self):
        return self.compress_method != COMP_NONE

    def __str__(self):
        return "<{} name={}, compressed={}, size={}, offset={}>".format(
            self.__class__.__name__,
            self.name,
            self.compressed,
            self.size,
            self.offset)


class ZipFile:
    def __init__(self, file_obj):
        self.file_obj = file_obj
        file_obj.seek(-EOCD_SIZE, SEEK_END)
        (magic_number,
         num_disks,
         _, _,  # Per disk stuff, we don't care
         central_dir_count,
         central_dir_size,
         central_dir_offset,
         comment_len) = struct.unpack(EOCD_STRUCT, file_obj.read(EOCD_SIZE))

        if magic_number != EOCD_SIG:
            raise BadZipFile(
                "EOCD contains comment or ZIP corrupt?")
        if num_disks:
            raise BadZipFile(
                "Multipart/disk ZIPs not supported")

        self.entries = OrderedDict()
        file_obj.seek(central_dir_offset)
        for i in range(central_dir_count):
            zi = ZipInfo(file_obj.read(CD_F_H_SIZE))
            zi.name = file_obj.read(zi.filename_len).decode()
            self.entries[zi.name] = zi

            # Skip to next entry
            file_obj.seek(zi.extra_field_len + zi.comment_len, SEEK_CUR)

    def __iter__(self):
        yield from self.entries

    def __getitem__(self, k):
        return self.entries[k]

    def read(self, member):
        zip_info = member if isinstance(member, ZipInfo) else self[member]

        # Seek to data, skip local file header
        self.file_obj.seek(zip_info.offset + LOCAL_F_H_SIZE
                           + zip_info.filename_len + zip_info.extra_field_len)

        # Read actual data, perform decompression if needed
        comp_data = self.file_obj.read(zip_info.compressed_size)
        if zip_info.compress_method == COMP_DEF:
            # Decompress, not DecompIO because of very bad performance
            uncomp_data = decompress(comp_data, -15)
        elif zip_info.compress_method == COMP_NONE:
            uncomp_data = comp_data  # Data was just stored, not compressed
        else:
            raise BadZipFile("Unsupported compression method"
                             "for file {}".format(zip_info.name))

        # Validate CRC32
        if crc32(uncomp_data) != zip_info.crc32:
            raise BadZipFile("Bad CRC32 for file {}".format(zip_info.name))

        return uncomp_data
