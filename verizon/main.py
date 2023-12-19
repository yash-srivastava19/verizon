import sys
import argparse

from cmd_fns import (
    cmd_add,
    cmd_cat_file,
    cmd_check_ignore,
    cmd_checkout,
    cmd_commit,
    cmd_init,
    cmd_log,
    cmd_ls_files,
    cmd_ls_tree,
    cmd_rev_parse,
    cmd_rm,
    cmd_show_ref,
    cmd_status,
    cmd_tag,
)


## Main Logic. We will be working with CLI a lot.
argparser = argparse.ArgumentParser(description="Verizon for Version Control")
argsubparsers = argparser.add_subparsers(title="Command", dest="command")
argsubparsers.required = True

## Init
argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repo")

argsp.add_argument(
    "path",
    metavar="directory",
    nargs="?",
    default=".",
    help="Where to create the repository",
)

## Cat-File
argsp = argsubparsers.add_parser(
    "cat-file", help="Provide contents of repository objects."
)

argsp.add_argument(
    "type",
    metavar="type",
    choices=["blob", "commit", "tag", "tree"],
    help="Specify the type.",
)

argsp.add_argument("object", metavar="object", help="The object to display")

## Hash-Object
argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute the object ID and optionally create a blob from a file.",
)

argsp.add_argument(
    "-t",
    metavar="type",
    dest="type",
    choices=["blob", "commit", "tag", "tree"],
    default="blob",
    help="Specify the type.",
)

argsp.add_argument(
    "-w",
    dest="write",
    action="store_true",
    help="Actually write the object into the database.",
)

argsp.add_argument("path", help="Read object from file.")

## Log
argsp = argsubparsers.add_parser("log", help="Display the history of a given commit.")

argsp.add_argument("commit", default="HEAD", nargs="?", help="Commit to start at.")

## Ls-Tree
argsp = argsubparsers.add_parser("ls-tree", help="Pretty print a tree object.")

argsp.add_argument(
    "-r", dest="recursive", action="store_true", help="Recurse into sub-trees."
)

argsp.add_argument("tree", help="A tree-ish object.")

## Checkout
argsp = argsubparsers.add_parser(
    "checkout", help="Checkout a commit inside of a directory."
)

argsp.add_argument("commit", help="The commit or tree to checkout.")

argsp.add_argument("path", help="The empty directory to checkout on.")

## Show-Ref.
argsp = argsubparsers.add_parser("show-ref", help="List references.")

## Tag.
argsp = argsubparsers.add_parser("tag", help="List and create tags.")

argsp.add_argument(
    "-a",
    action="store_true",
    dest="create_tag_object",
    help="Whether to create a tag object.",
)

argsp.add_argument("name", nargs="?", help="The new tag's name.")

argsp.add_argument(
    "object", default="HEAD", nargs="?", help="The object the new tag will point to."
)

## Rev-Parse.
argsp = argsubparsers.add_parser(
    "rev-parse", help="Parse revision(or other objects) identifiers."
)

argsp.add_argument(
    "-vrz-type",
    metavar="type",
    dest="type",
    choices=["blob", "commit", "tag", "tree"],
    default=None,
    help="Specify the expected type.",
)

argsp.add_argument("name", help="The name to parse.")

## Ls-Files.
argsp = argsubparsers.add_parser("ls-files", help="List all the stage files.")

argsp.add_argument("--verbose", action="store_true", help="Show everything.")

## Check-Ignore.
argsp = argsubparsers.add_parser(
    "check-ignore", help="Check path(s) against ignore rules."
)

argsp.add_argument("path", nargs="+", help="Paths to check.")

## Status.
argsp = argsubparsers.add_parser("status", help="Show the working tree status.")

## Remove.
argsp = argsubparsers.add_parser(
    "rm", help="Remove files from the working tree and the index."
)

argsp.add_argument("path", nargs="+", help="Files to check.")

## Add.
argsp = argsubparsers.add_parser("add", help="Add file contents files to the index.")

argsp.add_argument("path", nargs="+", help="Files to add.")

## Commit.
argsp = argsubparsers.add_parser("commit", help="Record changes to the repository.")

argsp.add_argument(
    "-m",
    metavar="message",
    dest="message",
    help="Message to associate with this commit.",
)


# Bridge functions take the parsed args as their unique parameter, and are responsible for processing and validating them before executing the actual command.
def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add":
            cmd_add(args)
        case "cat-file":
            cmd_cat_file(args)
        case "check-ignore":
            cmd_check_ignore(args)
        case "checkout":
            cmd_checkout(args)
        case "commit":
            cmd_commit(args)
        case "hash-object":
            cmd_add(args)
        case "init":
            cmd_init(args)
        case "log":
            cmd_log(args)
        case "ls-files":
            cmd_ls_files(args)
        case "ls-tree":
            cmd_ls_tree(args)
        case "rev-parse":
            cmd_rev_parse(args)
        case "rm":
            cmd_rm(args)
        case "show-ref":
            cmd_show_ref(args)
        case "status":
            cmd_status(args)
        case "tag":
            cmd_tag(args)
        case _:
            print("Invalid Command")
