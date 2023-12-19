import os
import configparser
from class_utils import tree_serialize, tree_parse
from other_utils import kvlm_serialize, kvlm_parse
from utils import repo_file


class VerizonRepository:
    worktree = None
    vrzdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.vrzdir = os.path.join(path, ".vrz")

        if not (force or os.path.isdir(self.vrzdir)):
            raise Exception(f"Not a Verizon Repository : {path}")

        # Read Config file.
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration File is Missing")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion : {vers}")


class VerizonObject:
    def __init__(self, data=None) -> None:
        if data is not None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self, repo):
        """Read the objects contents, and do whatever it takes to convert it into a meaningful representation."""
        raise NotImplementedError

    def deserialize(self, data):
        raise NotImplementedError

    def init(self):
        pass


# Tree wrapper for a single record(a single path).
class VerizonTreeLeaf:
    def __init__(self, mode, path, sha) -> None:
        self.mode = mode
        self.path = path
        self.sha = sha


## Type Header could be one of `blob`, `commit`, `tag`, `tree`.
# Blobs are user data. The content of every file we put in git is stored as a blob.


class VerizonBlob(VerizonObject):
    fmt = b"blob"

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data


class VerizonCommit(VerizonObject):
    fmt = b"commit"

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self, repo):
        return kvlm_serialize(self.kvlm)

    def init(self):
        self.kvlm = dict()


class VerizonTag(VerizonCommit):
    fmt = b"tag"


class VerizonTree(VerizonObject):
    fmt = b"tree"

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)

    def init(self):
        self.items = list()


class VerizonIndexEntry:
    def __init__(
        self,
        ctime=None,
        mtime=None,
        dev=None,
        ino=None,
        mode_type=None,
        mode_perms=None,
        uid=None,
        gid=None,
        fsize=None,
        sha=None,
        flag_assume_valid=None,
        flag_stage=None,
        name=None,
    ) -> None:
        self.ctime = ctime  # the last time the file's metadata changed.
        self.mtime = mtime  # the last time the file's data changed.
        self.dev = dev  # the ID of the device containing this file.
        self.ino = ino  # the file's inode number.
        self.mode_type = mode_type  # the object type - b1000(regular), b1010(symlink), b1110(verlink)
        self.mode_perms = mode_perms  # the object's permission(an integer)
        self.uid = uid  # the user id of the owner.
        self.gid = gid  # the group id of owner
        self.fsize = fsize  # the size of this object(in bytes)
        self.sha = sha  # the object's sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        self.name = name  # the name of the object(full path)


class VerizonIndex:
    version = None
    entries = []

    def __init__(self, version=2, entries=None) -> None:
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries


class VerizonIgnore:
    absolute = None
    scoped = None

    def __init__(self, absolute, scoped) -> None:
        self.absolute = absolute
        self.scoped = scoped
