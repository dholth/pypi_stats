import sqlalchemy

from sqlalchemy import Column, Integer, Unicode, BLOB
from sqlalchemy.ext.declarative.api import declarative_base
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.orm import relationship, deferred
from sqlalchemy.types import TIMESTAMP

Base = declarative_base()

class Archive(Base):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)
    modified = Column(TIMESTAMP, default=sqlalchemy.func.current_timestamp())
    name = Column(Unicode, index=True, nullable=False)

class File(Base):
    __tablename__ = 'file'
    id = Column(Integer, primary_key=True)
    archive_id = Column(ForeignKey(Archive.id), index=True)
    name = Column(Unicode, index=True)
    contents = deferred(Column(BLOB))
    archive = relationship(Archive, backref='files')

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, (self.name))

class PKGINFO(Base):
    __tablename__ = 'pkginfo'
    id = Column(Integer, primary_key=True)
    file_id = Column(ForeignKey(File.id), index=True)
    key = Column(Unicode, index=True) # XXX or another table...
    value = Column(Unicode)
    file = relationship(File, backref='parsed_pkginfo')
    
class Requirement(Base):
    """Store unique requires clauses."""
    __tablename__ = 'requirements'
    id = Column(Integer, primary_key=True)
    text = Column(Unicode, index=True)

class Dependency(Base):
    __tablename__ = 'dependencies'
    id = Column(Integer, primary_key=True)
    extra = Column(Unicode)
    file_id = Column(ForeignKey(File.id), index=True)
    req_id = Column(ForeignKey(Requirement.id), index=True)
    
    req = relationship(Requirement)
    
class Distribution(Base):
    __tablename__ = 'distributions'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode, index=True, nullable=False)

def initdb(uri="sqlite:///packagedata.db"):
    """Initialize database, returning session factory."""
    engine = sqlalchemy.create_engine(uri)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session

