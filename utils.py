# encoding: utf-8
import pwd
import os
import pwd
import grp

def get_uid(username):
    try:
        pwd.getpwnam(username)[2]
    except:
        return None

def drop_privileges(uid_name='nobody', gid_name='nogroup'):
    if os.getuid() != 0:
        # We're not root so, like, whatever dude
        return

    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_gid = grp.getgrnam(gid_name).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    old_umask = os.umask(077)

def recursive_mkdir(directory):
    """Python version of mkdir -p dir"""
    path = []
    directory = directory.rstrip('/')
    for p in directory.split('/'):
        if len(p) == 0:
            continue
        if len(path) == 0 and directory[0] == '/':
            p = '/%s' % p
        path.append(p)
        subpath = os.path.join(*path)
        if os.path.exists(subpath) and not os.path.isdir(subpath):
            raise IOError('Path %s is exist but not directory' % subpath)
        if not os.path.exists(subpath) and not os.path.isdir(subpath):
            os.mkdir(subpath)
    return True