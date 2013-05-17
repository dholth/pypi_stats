import os.path
import tarfile
import zipfile
import ast
import sys

from . import tables
from .tables import Archive, File

import collections
from datetime import datetime
statsd = collections.defaultdict(lambda: 0)
entry_points_text = []
non_text_ep = 0

def getname(t):
    if isinstance(t, ast.Attribute):
        return getname(t.value)
    elif isinstance(t, ast.Name):
        return t.id
    else:
        return t

class EntryPointsVisitor(ast.NodeVisitor):
    """Oops, I can just extract entry_points.txt"""
    def visit_Assign(self, node):
        try:
            names = [getname(t) for t in node.targets]
            entry_points = 'entry_points' in names
            if not entry_points:
                self.generic_visit(node)
            else:
                print ast.dump(node)
        except AttributeError, e:
            pass

    def visit_Call(self, node):
        global non_text_ep
        if not (isinstance(node.func, ast.Name) and node.func.id == 'setup'):
            self.generic_visit(node)
        else:
            for keyword in node.keywords:
                if keyword.arg == 'entry_points':
                    if isinstance(keyword.value, ast.Str):
                        entry_points_text.append(keyword.value.s)
                    else:
                        non_text_ep += 1

def eval_entry_points(setup_py):
    if not setup_py:
        return
    try:
        a = ast.parse(setup_py)
    except SyntaxError:
        return
    nv = EntryPointsVisitor()
    nv.visit(a)

def stats(name, setup_py):
    eval_entry_points(setup_py)
    pkg_resources = 'pkg_resources' in setup_py
    find_packages = 'find_packages' in setup_py
    has_entry_points = 'entry_points' in setup_py
    statsd['pkg_resources'] += pkg_resources
    statsd['find_packages'] += find_packages
    statsd['has_entry_points'] += has_entry_points
    statsd['count'] += 1
    print "%r %s" % (['t' if x else 'f' for x in (pkg_resources, find_packages, has_entry_points)], name)
    
class ZipTarError(Exception):
    pass

class ZipTar(object):
    """Wrapper providing a minimal consistent interface for zip and tar files."""
    @staticmethod
    def open(path):
        try:
            if path.endswith(('.tar.gz', '.tar.bz2')):
                return ZipTarTar(path)
            elif path.endswith('.zip'):
                return ZipTarZip(path)
            else:
                raise ZipTarError("Unsupported extension.")
        except (KeyError, tarfile.ReadError, zipfile.BadZipfile) as e:
            raise ZipTarError(path, e)
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.archive != None:
            self.archive.close()
            
    def yield_interesting(self, criteria):
        """
        Yield all the (name, file-like) tuples if any((c(name) for c in criteria)).
        """ 
        for name, opener in self.yield_openers():
            if any((c(name) for c in criteria)):
                opened = opener() # or the contextlib closer
                try:
                    yield (name, opened)
                finally:
                    opened.close()

class ZipTarZip(ZipTar):
    def __init__(self, path):
        self.archive = zipfile.ZipFile(path)
        
    def yield_openers(self):
        for info in self.archive.infolist():
            def opener():
                return self.archive.open(info)
            yield (info.filename, opener)
        
class ZipTarTar(ZipTar):
    def __init__(self, path):
        self.archive = tarfile.open(path)
        
    def yield_openers(self):
        for info in self.archive.getmembers():
            def opener():
                return self.archive.extractfile(info)
            yield (info.name, opener)

entry_points = {}

def is_requires_txt(x):
    # pkg_resources itself also looks for depends.txt...
    return x.endswith('.egg-info/requires.txt') or x.endswith('.egg-info/depends.txt')

def is_entry_points_txt(x):
    return x.endswith('.egg-info/entry_points.txt')

def is_deplinks_txt(x):
    return x.endswith('.egg-info/dependency_links.txt')

def is_pkg_info(x):
    return x.endswith('/PKG-INFO')

def is_egg_pkg_info(x):
    return x.endswith('.egg-info/PKG-INFO')

def is_setup_py(x):
    return x.endswith('/setup.py')

def pkg_info_or_metadata(x):
    return x.endswith('PKG-INFO') or x.endswith('METADATA')

pkg_info = []
requires = []
requires_sections = {}
has_deplinks = {}

def unicode_or_else(s):
    try:
        return s.decode('utf-8')
    except UnicodeDecodeError:
        return s.decode('latin1')

def yield_archive_paths(root):
    for path, directories, files in os.walk(root):
        for file in files:
            if file.endswith(('.tar.gz', '.tar.bz2', '.zip')):
                abspath = os.path.join(path, file)
                yield (path, file, os.stat(abspath).st_mtime)
                    
def yield_archives(session, archive_paths):
    all_archives = {}
    for archive in session.query(Archive).all():
        all_archives[archive.name] = archive
        
    for archive_path, archive_name, archive_mtime in archive_paths:
        u_archive_name = unicode_or_else(archive_name)
        archive = all_archives.get(u_archive_name)
        if not archive:
            archive = Archive(name=u_archive_name)
            session.add(archive)
        file_modified = datetime.fromtimestamp(archive_mtime)
        if not archive.modified or file_modified > archive.modified:
            archive.modified = file_modified
            fullpath = os.path.join(archive_path, archive_name)
            try:
                with ZipTar.open(fullpath) as zt:
                    yield (archive, zt)
            except ZipTarError as e:
                sys.stderr.write(str(e))

if __name__ == "__main__":
    # Absolute path to .../web/packages/source of a local pypi mirror (or any
    # directory tree full of sdists)
    sdists_path = sys.argv[1]
      
    Session = tables.initdb()
    session = Session()
    session.autoflush = False

    desirables = {'requires':is_requires_txt,
                  'entry_points':is_entry_points_txt,
                  'deplinks':is_deplinks_txt,
                  'pkg_info':is_pkg_info,
                  'egg_pkg_info':is_egg_pkg_info,
                  'setup':is_setup_py}

    sofar = 0
    batch_size = 1000

    for archive, zt in yield_archives(session, yield_archive_paths(sdists_path)):
        while archive.files:
            session.delete(archive.files.pop())
        for name, filelike in zt.yield_interesting(desirables.values()):
            file = File(name=unicode_or_else(name), contents=filelike.read())
            archive.files.append(file)
        sofar += 1
        if (sofar % batch_size) == 0:
            session.commit()
            print sofar
            
    session.commit()
    
    session.close()

