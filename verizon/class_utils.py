import os
import re
import zlib
import hashlib

from math import ceil

from classes import (
    VerizonIndex,
    VerizonIndexEntry,
    VerizonCommit,
    VerizonBlob,
    VerizonTag,
    VerizonTree,
    VerizonTreeLeaf,
)
from utils import repo_file, repo_dir
from other_utils import ref_resolve


def index_read(repo):
    index_file = repo_file(repo, "index")
    if not os.path.exists(index_file):
        return VerizonIndex()

    with open(index_file, "rb") as f:
        raw = f.read()

    header = raw[:12]
    signature = header[:4]
    assert signature == b"DIRC"

    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "Verizon supports only index file version 2"

    count = int.from_bytes(header[8:12], "big")

    entries = list()
    content = raw[12:]
    idx = 0

    for i in range(0, count):
        ctime_s = int.from_bytes(content[idx : idx + 4], "big")
        ctime_ns = int.from_bytes(content[idx + 4 : idx + 8], "big")

        mtime_s = int.from_bytes(content[idx + 8 : idx + 12], "big")
        mtime_ns = int.from_bytes(content[idx + 12 : idx + 16], "big")

        dev = int.from_bytes(content[idx + 16 : idx + 20], "big")
        ino = int.from_bytes(content[idx + 20 : idx + 24], "big")

        unused = int.from_bytes(content[idx + 24 : idx + 26], "big")
        assert 0 == unused

        mode = int.from_bytes(content[idx + 26 : idx + 28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]

        mode_perms = mode & 0b0000000111111111

        uid = int.from_bytes(content[idx + 28 : idx + 32], "big")
        gid = int.from_bytes(content[idx + 32 : idx + 36], "big")
        fsize = int.from_bytes(content[idx + 36 : idx + 40], "big")

        sha = format(int.from_bytes(content[idx + 40 : idx + 60], "big"), "040x")

        flags = int.from_bytes(content[idx + 60 : idx + 62], "big")

        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage = flags & 0b0011000000000000

        name_length = flags & 0b0000111111111111

        idx += 62

        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x00
            raw_name = content[idx : idx + name_length]
            idx += name_length + 1

        else:
            print("Notice that Name is 0x{:X} bytes long".format(name_length))
            null_idx = content.find(b"\x00", idx + 0xFFF)
            raw_name = content[idx:null_idx]
            idx = null_idx + 1

        name = raw_name.decode("utf8")

        idx = 8 * ceil(idx / 8)

        entries.append(
            VerizonIndexEntry(
                ctime=(ctime_s, ctime_ns),
                mtime=(mtime_s, mtime_ns),
                dev=dev,
                ino=ino,
                mode_type=mode_type,
                mode_perms=mode_perms,
                uid=uid,
                gid=gid,
                fsize=fsize,
                sha=sha,
                flag_assume_valid=flag_assume_valid,
                flag_stage=flag_stage,
                name=name,
            )
        )

    return VerizonIndex(version=version, entries=entries)


def index_write(repo, index):
    with open(repo_file(repo, "index"), "wb") as f:
        f.write(b"DIRC")
        f.write(index.version.to_bytes(4, "big"))
        f.write(len(index.entries).to_bytes(4, "big"))

        idx = 0
        # Entries
        for e in index.entries:
            f.write(e.ctime[0].to_bytes(4, "big"))
            f.write(e.ctime[1].to_bytes(4, "big"))
            f.write(e.mtime[0].to_bytes(4, "big"))
            f.write(e.mtime[1].to_bytes(4, "big"))

            f.write(e.dev.to_bytes(4, "big"))
            f.write(e.ino.to_bytes(4, "big"))

            # Mode
            mode = (e.mode_type << 12) | e.mode_perms
            f.write(mode.to_bytes(4, "big"))

            f.write(e.uid.to_bytes(4, "big"))
            f.write(e.gid.to_bytes(4, "big"))

            f.write(e.fsize.to_bytes(4, "big"))

            f.write(int(e.sha, 16).to_bytes(20, "big"))

            flag_assume_valid = 0x1 << 15 if e.flag_assume_valid else 0

            name_bytes = e.name.encode("utf8")
            bytes_len = len(name_bytes)

            if bytes_len >= 0xFFF:
                name_length = 0xFFF
            else:
                name_length = bytes_len

            f.write((flag_assume_valid | e.flag_stage | name_length).to_bytes(2, "big"))

            f.write(name_bytes)
            f.write((0).to_bytes(1, "big"))

            idx += 62 + len(name_bytes) + 1

            if idx % 8 != 0:
                pad = 8 - (idx % 8)
                f.write((0).to_bytes(pad, "big"))
                idx += pad


def tree_parse_one(raw, start=0):
    x = raw.find(b" ", start)
    assert x - start == 5 or x - start == 6

    mode = raw[start:x]
    if len(mode) == 5:
        mode = b" " + mode

    y = raw.find(b"\x00", x)
    path = raw[x + 1 : y]

    sha = format(int.from_bytes(raw[y + 1 : y + 21], "big"), "040x")
    return y + 21, VerizonTreeLeaf(mode, path.decode("utf8"), sha)


def tree_parse(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)

    return ret


# This is the ordering function. Entries are sorted by name, alphabetically, but directories are sorted with a final / added.
def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b"10"):
        return leaf.path
    return leaf.path + "/"


def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b""

    for i in obj.items:
        ret += i.mode
        ret += b""
        ret += i.path.encode("utf8")
        ret += b"\x00"
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")

    return ret


def object_read(repo, sha):
    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None

    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Read the object type
        x = raw.find(b"")
        fmt = raw[0:x]

        # Read and Validate the object size
        y = raw.find(b"\x00", x)
        size = int(raw[x:y].decode("ascii"))

        if size != len(raw) - y - 1:
            raise Exception(f"Malformed object {sha}: bad length")

        match fmt:
            case b"commit":
                c = VerizonCommit
            case b"tree":
                c = VerizonTree
            case b"tag":
                c = VerizonTag
            case b"blob":
                c = VerizonBlob
            case _:
                raise Exception(f"Unknown type {fmt.decode('ascii')} for object {sha}")

        # Call constructor and return object.
        return c(raw[y + 1])


def object_write(obj, repo=None):
    data = obj.serialize()

    result = obj.fmt + b" " + str(len(data)).encode() + b"\x00" + data

    sha = hashlib.sha1(result).hexdigest()

    if repo:
        path = repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(zlib.compress(result))

    return sha


def object_find(repo, name, fmt=None, follow=True):
    sha = object_resolve(repo, name)

    if not sha:
        raise Exception(f"No such reference : {name}")

    if len(sha) > 1:
        raise Exception(
            "Ambigious Reference - {0}. Candidates are :\n - {1}".format(
                name, "\n - ".join(sha)
            )
        )

    sha = sha[0]

    if not fmt:
        return sha

    while True:
        obj = object_read(repo, sha)

        if obj.fmt == fmt:
            return sha

        if not follow:
            return None

        # Follow tags
        if obj.fmt == b"tag":
            sha = obj.kvlm[b"object"].decode("ascii")

        elif obj.fmt == b"commit":
            sha = obj.kvlm[b"tree"].decode("ascii")

        else:
            return None


def object_hash(fd, fmt, repo=None):
    data = fd.read()
    match fmt:
        case b"commit":
            obj = VerizonCommit(data)
        case b"tree":
            obj = VerizonTree(data)
        case b"tag":
            obj = VerizonTag(data)
        case b"blob":
            obj = VerizonBlob(data)
        case _:
            raise Exception(f"Unknown Type : {fmt}")

    return object_write(obj, repo)


def object_resolve(repo, name):
    """Resolve names to an object has in repo."""
    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    if not name.strip():
        return None

    # If it's head, then it is non-ambigious.
    if name == "HEAD":
        return [ref_resolve(repo, "HEAD")]

    if hashRE.match(name):
        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "objects", prefix, mkdir=False)

        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    candidates.append(prefix + f)

    as_tag = ref_resolve(repo, "refs/tags/" + name)
    # Try for references.
    if as_tag:
        candidates.append(as_tag)

    # Try for branches.
    as_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_branch:
        candidates.append(as_branch)

    return candidates
