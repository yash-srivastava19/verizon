import collections
import configparser
import os
import sys
from fnmatch import fnmatch

from class_utils import (
    index_read,
    index_write,
    object_find,
    object_hash,
    object_read,
    object_write,
)
from verizon.classes import (
    VerizonCommit,
    VerizonIgnore,
    VerizonIndexEntry,
    VerizonTag,
    VerizonTree,
    VerizonTreeLeaf,
)
from verizon.utils import repo_dir, repo_file


def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())


# Key Value List with Message
def kvlm_parse(raw, start=0, dct=None):
    if not dct:
        dct = collections.OrderedDict()

    # We search for next space and the next line. If space appears before a newline, we have a keyword. Othewise, it's the final message, which we just read to the end of file.
    spc = raw.find(b" ", start)
    nl = raw.find(b"\n", start)

    # Base Case :
    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start + 1 :]
        return dct

    # Recursive Case :
    key = raw[start:spc]
    end = start

    # Find the end of the value. We loop until we find a '\n' followed by a space.
    while True:
        end = raw.find(b"\n", end + 1)
        if raw[end + 1] != ord(" "):
            break

    value = raw[spc + 1 : end].replace(b"\n ", b"\n")

    if key in dct:
        if isinstance(dct[key], list):
            dct[key].append(value)
        else:
            dct[key] = [dct[key], value]
    else:
        dct[key] = value

    return kvlm_parse(raw, start=end + 1, dct=dct)


def kvlm_serialize(kvlm):
    ret = b""

    for k in kvlm.keys():
        if k is None:
            continue
        val = kvlm[k]

        if not isinstance(val, list):
            val = [val]

        for v in val:
            ret += k + b" " + (v.replace(b"\n ")) + b"\n"

    ret += b"\n" + kvlm[None] + b"\n"

    return ret


def log_graphviz(repo, sha, seen):
    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo, sha)
    # short_hash = sha[0:8]  # never used
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\", "\\\\")
    message = message.replace('"', '\\"')

    if "\n" in message:
        message = message[: message.index("\n")]

    print(f'  c_{sha} [label="{sha[0:7]}: {message}"]')
    assert commit.fmt == b"commit"

    if b"parent" not in commit.kvlm.keys():
        # Base Case is the initial commit.
        return

    parents = commit.kvlm[b"parent"]

    if not isinstance(parents, list):
        parents = [parents]

    for p in parents:
        p = p.decode("ascii")
        print(f"  c_{sha} -> c_{p};")
        log_graphviz(repo, p, seen)


def ls_tree(repo, ref, recursive=None, prefix=""):
    sha = object_find(repo, ref, fmt=b"tree")
    obj = object_read(repo, sha)

    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]

        match type:
            case b"04":
                type = "tree"
            case b"10":
                type = "blob"  # a regular file
            case b"12":
                type = "blob"  # a symlink
            case b"16":
                type = "commit"
            case _:
                raise Exception(f"Weird Tree Leaf Mode {item.mode}")

        if not (recursive and type == "tree"):  # that means that this is a leaf.
            print(
                f"{'0'*(6-len(item.mode)) + item.mode.decode('ascii')} {type} {item.sha}\t{os.path.join(prefix, item.path)}"
            )
        else:
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))


def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b"tree":
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)

        elif obj.fmt == b"blob":
            # TODO: Support for symlinks. Mode 12*
            with open(dest, "wb") as f:
                f.write(obj.blobdata)


def ref_resolve(repo, ref):
    path = repo_file(repo, ref)

    if not os.path.isfile(path):
        return None

    with open(path, "r") as fp:
        data = fp.read()[:-1]  # For dropping final \n

    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])

    return data


def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    ret = collections.OrderedDict()

    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)

        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)

        else:
            ret[f] = ref_resolve(repo, can)

    return ret


def show_ref(repo, refs, with_hash=True, prefix=""):
    for k, v in refs.items():
        if isinstance(v, str):
            print(f"{v + ' ' if with_hash else ''}{prefix + '/' if prefix else ''}{k}")

        else:
            show_ref(
                repo,
                v,
                with_hash=with_hash,
                prefix=f"{prefix}{'/' if prefix else ''}{k}",
            )


def tag_create(repo, name, ref, create_tag_object=False):
    sha = object_find(repo, ref)

    if create_tag_object:
        tag = VerizonTag(repo)
        tag.kvlm = collections.OrderedDict()
        tag.kvlm[b"object"] = sha.encode()
        tag.kvlm[b"type"] = b"commit"
        tag.kvlm[b"tag"] = name.encode()

        # Let the user name this, and that we can fix this after commit.
        tag.kvlm[b"tagger"] = b"verizon <ver-bot>"
        tag.kvlm[
            None
        ] = b"A tag generated by Verizon, which won't let you customize the message."

        tag_sha = object_write(tag)
        # Creates a reference
        ref_create(repo, "tags/" + name, tag_sha)

    else:
        # Creates a lighweight tag.
        ref_create(repo, "tags/" + name, sha)


def ref_create(repo, ref_name, sha):
    with open(repo_file(repo, "refs/" + ref_name), "w") as fp:
        fp.write(sha + "\n")


def vrzignore_parse1(raw):
    raw = raw.strip()

    if not raw or raw[0] == "#":
        return None

    elif raw[0] == "!":
        return (raw[1:], False)

    elif raw[0] == "\\":
        return (raw[1:], True)

    else:
        return (raw, True)


def vrzignore_parse(lines):
    ret = list()

    for line in lines:
        parsed = vrzignore_parse1(line)
        if parsed:
            ret.append(parsed)

    return ret


def vrzignore_read(repo):
    ret = VerizonIgnore(absolute=list(), scoped=dict())

    repo_file = os.path.join(repo.vrzdir, "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            ret.absolute.append(vrzignore_parse(f.readlines()))

    # Global Configuration
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home, "vrz/ignore")

    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(vrzignore_parse(f.readlines()))

    index = index_read(repo)

    for entry in index.entries:
        if entry.name == ".vrzignore" or entry.name.endswith("/.vrzignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = vrzignore_parse(lines)

    return ret


def check_ignore1(rules, path):
    result = None
    for pattern, value in rules:
        if fnmatch(path, pattern):
            result = value
    return result


def check_ignore_scoped(rules, path):
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignore1(rules[parent], path)
            if result is not None:
                return result

        if parent == "":
            break

        parent = os.path.dirname(parent)

    return None


def check_ignore_absolute(rules, path):
    # parent = os.path.dirname(path)  # Never used. TODO: remove
    for rs in rules:
        result = check_ignore1(rs, path)
        if result is not None:
            return result
    return False


def check_ignore(rules, path):
    if os.path.isabs(path):
        raise Exception(
            "This function requires path to be relative to the repository's root."
        )

    result = check_ignore_scoped(rules.scoped, path)
    if result is not None:
        return result

    return check_ignore_absolute(rules.absolute, path)


def branch_get_active(repo):
    with open(repo_file(repo, "HEAD"), "r") as f:
        head = f.read()

    if head.startswith("ref: refs/heads/"):
        return head[16:-1]
    return False


def tree_to_dict(repo, ref, prefix=""):
    ret = dict()
    tree_sha = object_find(repo, ref, fmt=b"tree")
    tree = object_read(repo, tree_sha)

    for leaf in tree.items:
        full_path = os.path.join(prefix, leaf.path)

        is_subtree = leaf.mode.startswith(b"04")

        if is_subtree:
            ret.update(tree_to_dict(repo, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha

    return ret


def rm(repo, paths, delete=True, skip_missing=False):
    index = index_read(repo)
    worktree = repo.worktree + os.sep

    abspaths = list()
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree):
            abspaths.append(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of the worktree: {paths}")

    kept_entries = list()
    remove = list()

    for e in index.entries:
        full_path = os.path.join(repo.worktree, e.name)

        if full_path in abspaths:
            remove.append(full_path)
            abspaths.remove(full_path)
        else:
            kept_entries.append(e)
    if len(abspaths) > 0 and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index : {abspaths}")

    if delete:
        for path in remove:
            os.unlink(path)

    index.entries = kept_entries
    index_write(repo, index)


def add(repo, paths, delete=True, skip_missing=False):
    rm(repo, paths, delete=False, skip_missing=True)

    worktree = repo.worktree + os.sep

    clean_paths = list()
    for path in paths:
        abspath = os.path.abspath(path)
        if not (abspath.startswith(worktree) and os.path.isfile(abspath)):
            raise Exception(f"Not a file, or outside the worktree: {paths}")
        relpath = os.path.relpath(abspath, repo.worktree)
        clean_paths.append((abspath, relpath))

    index = index_read(repo)

    for abspath, relpath in clean_paths:
        with open(abspath, "rb") as fd:
            sha = object_hash(fd, b"blob", repo)

        stat = os.stat(abspath)

        ctime_s = int(stat.st_ctime)
        ctime_ns = stat.st_ctime_ns * 10**9
        mtime_s = int(stat.st_mtime)
        mtime_ns = stat.st_mtime_ns * 10**9

        entry = VerizonIndexEntry(
            ctime=(ctime_s, ctime_ns),
            mtime=(mtime_s, mtime_ns),
            dev=stat.st_dev,
            ino=stat.st_ino,
            mode_type=0b1000,
            mode_perms=0o644,
            uid=stat.st_uid,
            gid=stat.st_gid,
            fsize=stat.st_size,
            sha=sha,
            flag_assume_valid=False,
            flag_stage=False,
            name=relpath,
        )

        index.entries.append(entry)

    index_write(repo, index)


def vrzconfig_read():
    xdg_config_home = (
        os.environ["XDG_CONFIG_HOME"]
        if "XDG_CONFIG_HOME" in os.environ
        else "~/.config"
    )
    config_files = [
        os.path.expanduser(os.path.join(xdg_config_home, "vrz/config")),
        os.path.expanduser("~/.vrzconfig"),
    ]

    config = configparser.ConfigParser()
    config.read(config_files)

    return config


def tree_from_index(repo, index):
    contents = dict()
    contents[""] = list()

    for entry in index.entries:
        dirname = os.path.dirname(entry.name)
        key = dirname
        while key != "":
            if key not in contents:
                contents[key] = list()
            key = os.path.dirname(key)

        contents[dirname].append(entry)

    sorted_paths = sorted(contents.keys(), key=len, reverse=True)

    sha = None

    for path in sorted_paths:
        tree = VerizonTree()
        for entry in contents[path]:
            if isinstance(entry, VerizonIndexEntry):
                leaf_mode = "{:02o}{:04o}".format(
                    entry.mode_type, entry.mode_perms
                ).encode("ascii")
                leaf = VerizonTreeLeaf(
                    mode=leaf_mode, path=os.path.basename(entry.name), sha=entry.sha
                )

            else:
                leaf = VerizonTreeLeaf(mode=b"040000", path=entry[0], sha=entry[1])

            tree.items.append(leaf)

        sha = object_write(tree, repo)

        parent = os.path.dirname(path)
        base = os.path.basename(path)
        contents[parent].append((base, sha))

    return sha


def vrzconfig_user_get(config):
    if "user" in config:
        if "name" in config["user"] and "email" in config["user"]:
            return f"{config['user']['name']} <{config['user']['email']}>"

        return None


def commit_create(repo, tree, parent, author, timestamp, message):
    commit = VerizonCommit()
    commit.kvlm[b"tree"] = tree.encode("ascii")

    if parent:
        commit.kvlm[b"parent"] = parent.encode("ascii")

    offset = int(timestamp.astimezone().utcoffset().total_seconds())
    hours = offset // 3600
    minutes = (offset % 3600) // 60
    tz = "{}{:02}{:02}".format("+" if offset > 0 else "-", hours, minutes)

    author = author + timestamp.strftime(" %s ") + tz

    commit.kvlm[b"author"] = author.encode("utf8")
    commit.kvlm[b"committer"] = author.encode("utf8")
    commit.kvlm[None] = message.encode("utf8")

    return object_write(commit, repo)
