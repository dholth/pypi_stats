# parse all pkg_info (preferring egg pkg info)
# inserts into pkg_info table

from sqlalchemy.sql import exists, and_
from wheel.pkginfo import read_pkg_info_bytes
from pkg_resources import safe_extra, split_sections, parse_requirements

import re
import collections

from .tables import Archive, File, PKGINFO, Requirement, Dependency, initdb

archive_name = re.compile('(?P<name>.*)\.((tar\.(gz|bz2)|zip))')

def best_pkg_info(session, name='PKG-INFO', egg_info_only=False):
    stmt = exists().where(and_(Archive.id==File.archive_id, 
                               File.name.like('%/'+name)))
    for archive in session.query(Archive).filter(stmt):
        try:
            basename = archive_name.match(archive.name).group('name')
        except AttributeError:
            print "Doesn't match re: %s" % (archive.name,)
            continue
        distname = basename.partition('-')[0]
        best_pkg_info = None
        for file in archive.files:
            # oops, version # is not in .egg-info
            if file.name == '/'.join((basename, distname+'.egg-info', name)):
                best_pkg_info = file
                break
            if not egg_info_only \
                    and file.name == '/'.join((basename, name)):
                best_pkg_info = file
        if best_pkg_info:
            yield best_pkg_info 

def parse_to_db(session, pkg_infos):
    pkginfo_insert = PKGINFO.__table__.insert()
    i = 0
    for file in pkg_infos:
        try:
            pkginfo = read_pkg_info_bytes(file.contents)
        except Exception as e:
            # doesn't happen
            session.execute(pkginfo_insert, 
                    {'file_id':file.id, 
                     'key':'error', 'value':repr(e)})
            continue
        # XXX delete old values (or purge entire table)
        for key, value in pkginfo.items():
            if key.lower() == 'description':
                continue
            key = key.title()
            try:
                key = key.decode('latin1')
                value = value.decode('utf-8')
            except UnicodeDecodeError:
                value = value.decode('latin1')
            session.execute(pkginfo_insert, {'file_id':file.id, 
                'key':key, 'value':value})
            i+=1
            if (i % 10000) == 0:
                print i

def dep_map(requires_txt):
    """Parse dependency map. From setuptools."""
    dm = collections.OrderedDict({None: []})
    for extra, reqs in split_sections(requires_txt):
        if extra: extra = safe_extra(extra)
        dm.setdefault(extra,[]).extend(parse_requirements(reqs))
    return dm

def parse_requires_to_db(session, requireses):
    known_requirements = {}
    for file in requireses:
        try:
            dm = dep_map(file.contents)
        except:
            print "Can't parse requires.txt from", file
            continue
        for key, value in dm.items():
            extra = key if key else ''
            for req in value:
                as_text = str(req)
                if not as_text in known_requirements:
                    known_requirements[as_text] = Requirement(text=as_text)
                    session.add(known_requirements[as_text])
                session.add(Dependency(extra=extra, 
                                       file_id=file.id, 
                                       req=known_requirements[as_text]))

if __name__ == '__main__':
    Session = initdb()
    session = Session(autocommit=True)
    with session.begin():
        parse_to_db(session, best_pkg_info(session))
        parse_requires_to_db(session, 
                             best_pkg_info(session, 
                                           name='requires.txt', 
                                           egg_info_only=True))

