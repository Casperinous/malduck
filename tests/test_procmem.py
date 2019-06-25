# Copyright (C) 2018 Jurriaan Bremer.
# This file is part of Roach - https://github.com/jbremer/malduck.
# See the file 'docs/LICENSE.txt' for copying permission.

import os
import struct
import tempfile

from malduck import procmem, procmempe, cuckoomem, pad, pe, insn, PAGE_READWRITE


def test_cuckoomem_dummy_dmp():
    with cuckoomem.from_file("tests/files/dummy.dmp") as p:
        assert len(p.regions) == 3
        assert p.regions[0].to_json() == {
            "addr": "0x41410000",
            "end": "0x41411000",
            "offset": 24,
            "size": 0x1000,
            "state": 0,
            "type": 0,
            "protect": "rwx",
        }
        assert p.regions[1].to_json() == {
            "addr": "0x41411000",
            "end": "0x41413000",
            "offset": 4144,
            "protect": "r",
            "size": 0x2000,
            "state": 42,
            "type": 43,
        }
        assert p.regions[2].to_json() == {
            "addr": "0x42420000",
            "end": "0x42421000",
            "offset": 12360,
            "protect": "r",
            "size": 0x1000,
            "state": 0,
            "type": 0,
        }

        assert len(p.regions) == 3
        assert p.readv(0x41410f00, 0x200) == "A"*0xf4 + "X"*4 + "A"*8 + "B"*0x100
        assert p.uint8p(p.v2p(0x41410fff)) == 0x41
        assert p.uint8v(0x41410fff) == 0x41
        assert p.uint16p(p.v2p(0x4141100f)) == 0x4242
        assert p.uint16v(0x4141100f) == 0x4242
        assert p.uint32p(p.v2p(0x42420000)) == 0x43434343
        assert p.uint32v(0x42420000) == 0x43434343
        assert p.uint64p(p.v2p(0x41410ff8)) == 0x4141414141414141
        assert p.uint64v(0x41410ffe) == 0x4242424242424141
        assert p.p2v(p.v2p(0x41411414)) == 0x41411414

        assert p.uint8v(0x1000) is None
        assert p.uint16v(0x1000) is None
        assert p.uint32v(0x1000) is None
        assert p.uint64v(0x1000) is None


def test_calc_dmp():
    with cuckoomem.from_file("tests/files/calc.dmp") as p:
        ppe = procmempe.from_memory(p, 0xd0000)
        assert p.regions == ppe.regions
        assert p.findmz(0x129abc) == 0xd0000
        # Old/regular method with PE header.
        assert pe(p.readv(p.imgbase, 0x1000)).dos_header.e_lfanew == 0xd8
        assert p.readv(p.imgbase + 0xd8, 4) == "PE\x00\x00"

        assert pe(p).is32bit is True
        d = pe(p).optional_header.DATA_DIRECTORY[2]
        assert d.VirtualAddress == 0x59000 and d.Size == 0x62798
        data = pe(p).resource("WEVT_TEMPLATE")
        assert data.startswith("CRIM")
        assert len(data) == 4750


def test_calc_exe():
    with procmempe.from_file("tests/files/calc.exe", image=True) as ppe:
        assert ppe.imgbase == 0x1000000
        assert ppe.readv(ppe.imgbase + 0xd8, 4) == "PE\x00\x00"
        assert ppe.pe.is32bit is True
        d = ppe.pe.optional_header.DATA_DIRECTORY[2]
        assert d.VirtualAddress == 0x59000 and d.Size == 0x62798
        data = ppe.pe.resource("WEVT_TEMPLATE")
        assert data.startswith("CRIM")
        assert len(data) == 4750
        # Check relocations
        assert not ppe.readv(0x10016C2, 4) == 0x10551f8


def test_cuckoomem_methods():
    fd, filepath = tempfile.mkstemp()
    os.write(fd, "".join((
        struct.pack("QIIII", 0x401000, 0x1000, 0, 0, PAGE_READWRITE),
        pad.null("foo\x00bar thisis0test\n hAAAA\xc3", 0x1000),
    )))
    os.close(fd)
    with cuckoomem.from_file(filepath) as buf:
        assert buf.readv(0x401000, 0x1000).endswith("\x00"*0x100)
        assert list(buf.regexv("thisis(.*)test")) == [0x401008]
        assert list(buf.regexv(" ")) == [0x401007, 0x401014]
        assert list(buf.regexv(" ", 0x401000, 0x10)) == [0x401007]
        assert list(buf.regexv("test..h")) == [0x40100f]
        assert buf.disasmv(0x401015, 6) == [
            insn("push", 0x41414141, addr=0x401015),
            insn("ret", addr=0x40101a),
        ]


def test_findbytes():
    payload = " " * 0x1000 + pad.null(
        "\xffoo\x00bar thisis0test\n hAAAA\xc3\xc0\xc2\xc4\n\n\x10\x2f\x1f\x1a\x1b\x1f\x1d\xbb\xcc\xdd\xff",
        0x10000)
    buf = procmem(payload, base=0x400000)
    assert list(buf.findbytesv("c? c? c? 0A")) == [0x40101B]
    assert list(buf.findbytesv("1f ?? ?b")) == [0x401022, 0x401025]
    assert list(buf.findbytesv("?f ?? ?? 00")) == [0x401000, 0x40102A]
    assert not list(buf.findbytesv("test hAAAA".encode("hex")))
    assert list(buf.findbytesv("test\n hAAAA".encode("hex")))
