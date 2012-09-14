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

def recursive_mkdir(directory, perms=0701):
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
            # give minimium permissions
            os.chmod(subpath, perms)
    return True

def copy(source, dest):
    """Copy file"""
    if not os.path.isfile(source):
        raise RuntimeError('File %s does not found, cannot copy' % source)
        return False
    if os.path.isfile(dest):
        if os.path.getmtime(dest) > os.path.getmtime(source):
            # Destination is newer than source, no need for copying
            return True
    source = open(source, 'rb')
    dest = open(dest, 'wb')
    while line in source.read(2048):
        dest.write(line)
    dest.close()
    source.close()
    return True
