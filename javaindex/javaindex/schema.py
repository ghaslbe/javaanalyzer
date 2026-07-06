"""SQLite schema for the Java code index.

Everything is rebuilt from scratch on every `build` run (see build.py) --
there is no incremental/migration story, re-run the build after the source
changes.
"""

import sqlite3

SCHEMA = """
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    package TEXT
);

CREATE TABLE types (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    name TEXT NOT NULL,
    fqn TEXT NOT NULL,                -- not unique: the same FQN can legitimately be
                                       -- declared in more than one file in a large repo
    kind TEXT NOT NULL,              -- class | interface | enum
    outer_type_id INTEGER REFERENCES types(id),
    superclass_name TEXT,            -- as written in source (simple/qualified)
    superclass_fqn TEXT,             -- resolved, may be NULL/external
    modifiers TEXT,
    start_line INTEGER,
    end_line INTEGER
);

CREATE TABLE type_implements (
    type_id INTEGER NOT NULL REFERENCES types(id),
    interface_name TEXT NOT NULL,
    interface_fqn TEXT
);

CREATE TABLE fields (
    id INTEGER PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES types(id),
    name TEXT NOT NULL,
    field_type_name TEXT,
    field_type_fqn TEXT,
    modifiers TEXT
);

CREATE TABLE methods (
    id INTEGER PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES types(id),
    name TEXT NOT NULL,
    signature TEXT NOT NULL,         -- name(paramType1,paramType2,...)
    return_type_name TEXT,
    modifiers TEXT,
    start_line INTEGER,
    end_line INTEGER
);

CREATE TABLE method_params (
    method_id INTEGER NOT NULL REFERENCES methods(id),
    position INTEGER NOT NULL,
    name TEXT,
    param_type_name TEXT
);

CREATE TABLE calls (
    id INTEGER PRIMARY KEY,
    caller_method_id INTEGER NOT NULL REFERENCES methods(id),
    callee_name TEXT NOT NULL,
    callee_type_fqn TEXT,             -- resolved receiver type, NULL if unknown
    callee_method_id INTEGER REFERENCES methods(id),  -- resolved within our own index
    resolved INTEGER NOT NULL DEFAULT 0,
    line INTEGER
);

CREATE TABLE type_refs (
    id INTEGER PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES types(id),
    method_id INTEGER REFERENCES methods(id),
    referenced_fqn TEXT NOT NULL,
    kind TEXT NOT NULL   -- field_type | param_type | return_type | local_var | instantiation
);

CREATE INDEX idx_types_fqn ON types(fqn);
CREATE INDEX idx_methods_type ON methods(type_id);
CREATE INDEX idx_calls_caller ON calls(caller_method_id);
CREATE INDEX idx_calls_callee ON calls(callee_method_id);
CREATE INDEX idx_type_refs_type ON type_refs(type_id);
CREATE INDEX idx_type_refs_target ON type_refs(referenced_fqn);

CREATE VIRTUAL TABLE search USING fts5(
    fqn, name, kind, path UNINDEXED, ref_id UNINDEXED, ref_kind UNINDEXED, content
);
"""


def init_db(db_path):
    """(Re-)create the database at db_path with a fresh schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript("PRAGMA foreign_keys = OFF;")
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS search;
        DROP TABLE IF EXISTS type_refs;
        DROP TABLE IF EXISTS calls;
        DROP TABLE IF EXISTS method_params;
        DROP TABLE IF EXISTS methods;
        DROP TABLE IF EXISTS fields;
        DROP TABLE IF EXISTS type_implements;
        DROP TABLE IF EXISTS types;
        DROP TABLE IF EXISTS files;
    """)
    cur.executescript(SCHEMA)
    conn.commit()
    return conn
