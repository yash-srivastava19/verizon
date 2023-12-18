from utils import *
from other_utils import *

def cmd_init(args):
    repo_create(args.path)

def cmd_add(args):
    repo = repo_find()
    add(repo, args.path)

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None
    
    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

def cmd_log(args):
    repo = repo_find()
    print("digraph verizonlog{")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree, args.recursive)

def cmd_checkout(args):
    repo = repo_find()
    obj = object_read(repo, object_find(repo, args.commit))

    if obj.fmt == b'tree':
        obj = object_read(repo, obj.kvlm[b'tree'].decode('ascii'))
    
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Not a directory : {args.path}")
        if os.listdir(args.path):
            raise Exception(f"Not empty {args.path} !")
    else:
        os.makedirs(args.path)
    
    tree_checkout(repo, obj, os.path.relpath(args.path))

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def cmd_tag(args):
    repo = repo_find()

    if args.name:
        tag_create(repo, args.name, args.object, type="object" if args.create_tag_object else "ref")
    
    else:
        refs = ref_list(repo)
        show_ref(repo, refs["tags"], with_hash=False)

def cmd_rev_parse(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None
    
    repo = repo_find()
    print(object_find(repo, args.name, fmt, follow=True))

def cmd_ls_files(args):
    repo = repo_find()
    index = index_read(repo)

    if args.verbose:
        print(f"Index File Format v{index.version}, containing {len(index.entries)} entries")
    
    for e in index.entries:
        print(e.name)
        if args.verbose:
            print("  {} with perms: {:o}".format(
                {0b1000: "regular_file",
                 0b1010: "symlink",
                 0b1110: "git link"}[e.mode_type], e.mode_perms))
            
            print(f"  on blob: {e.sha}")
            print(f"  created: {datetime.fromtimestamp(e.ctime[0])}.{e.ctime[1]}, modified: {datetime.fromtimestamp(e.mtime[0])}.{e.mtime[1]}")
            print(f"  device: {e.dev}, inode: {e.ino}")
            print(f"  user: {pwd.getpwuid(e.uid).pw_name}({e.uid}) group: {grp.getgrgid(e.gid).gr_name}({e.gid})")
            print(f"  flags: stage={e.flag_stage} assume_valid={e.flag_assume_valid}")


def cmd_check_ignore(args):
    repo = repo_find()
    rules = vrzignore_read(repo)

    for path in args.path:
        if check_ignore(rules, path):
            print(path)

def cmd_status_head_index(repo, index):
    print("Changes to be committed.")

    head = tree_to_dict(repo, "HEAD")
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                print(f"  modified: {entry.name}")
            del head[entry.name]
        else:
            print(f"  added:  {entry.name}")

    for entry in head.keys():
        print(f"  deleted: {entry}")

def cmd_status_index_worktree(repo, index):
    print("Changes not staged for commit:")

    ignore = vrzignore_read(repo)
    vrzdir_prefix = repo.vrzdir + os.path.sep 
    all_files = list()

    for (root, _, files) in os.walk(repo.worktree, True):
        if root == repo.vrzdir or root.startswith(vrzdir_prefix):
            continue 
        
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, repo.worktree)
            all_files.append(rel_path)
        
    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)

        if not os.path.exists(full_path):
            print(f"  deleted: {entry.name}")
        else:
            stat = os.stat(full_path)

            ctime_ns = entry.ctime[0]*10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0]*10**9 + entry.mtime[1]

            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                with open(full_path, "rb") as fd:
                    new_sha = object_hash(fd, b'blob', None)
                    same = entry.sha == new_sha
                    if not same:
                        print(f"  modified: {entry.name}")
        if entry.name in all_files:
            all_files.remove(entry.name) 
    
    print("\nUntracked Files: ")
    for f in all_files:
        if not check_ignore(ignore, f):
            print(" ", f)

def cmd_status_branch(repo):
    branch = branch_get_active(repo)
    if branch:
        print(f"On branch {branch}.")
    else:
        print(f"HEAD detached at {object_find(repo, 'HEAD')}")

def cmd_status(_):
    repo = repo_find()
    index = index_read(repo)

    cmd_status_branch(repo)
    cmd_status_head_index(repo, index)
    print()
    cmd_status_index_worktree(repo, index)

def cmd_rm(args):
    repo = repo_find()
    rm(repo, args.path)

def cmd_commit(args):
    repo = repo_find()
    index = index_read(repo)

    tree = tree_from_index(repo, index)

    commit = commit_create(repo, 
                           tree,
                           object_find(repo, "HEAD"), 
                           vrzconfig_user_get(vrzconfig_read()),
                           datetime.now(),
                           args.message)
    
    active_branch = branch_get_active(repo)
    if active_branch:
        with open(repo_file(repo, os.path.join("refs/heads", active_branch)), "w") as fd:
            fd.write(commit + "\n")
    
    else:
        with open(repo_file(repo, "HEAD"), "w") as fd:
            fd.write("\n")
