import os
import configparser
from typing import Tuple
from classes import VerizonRepository


def repo_dir(repo: VerizonRepository, *path, mkdir=False):
    path = repo_path(repo, *path)

    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        raise Exception(f"Not a directory : {path}")

    if mkdir:
        os.mkdir(path)
        return path
    return None


def repo_path(repo: VerizonRepository, *path: Tuple[str]):
    return os.path.join(repo.vrzdir, *path)


def repo_file(repo, *path, mkdir=False):
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def repo_default_config():
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")
    return ret


def repo_create(path):
    """Creates a new repo at path."""
    repo = VerizonRepository(path, True)

    # To make sure the path either doesn't exist or is an empty dir.
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory !")

        if os.path.exists(repo.vrzdir) and os.listdir(repo.vrzdir):
            raise Exception(f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    # .vrz/description
    with open(repo_file(repo, "description"), "w") as f:
        f.write(
            "This is an unnamed repo, edit this file 'description' to name the repo. "
        )

    # .vrz/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    # .vrz/config
    # Config file is really simple, it's a INI-like file with a single section(core) and three fields - repositoryformatversion, filemode, bare.
    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo


def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".vrz")):
        return VerizonRepository(path)

    # If we haven't retured till now, we recurse in parent.
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        if required:
            raise Exception("Not a verizon directory.")
        return None

    return repo_find(parent, required)
