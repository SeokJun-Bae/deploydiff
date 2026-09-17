"""PostgreSQL access for DeployDiff comparison history."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


def load_db_config(env_file=BASE_DIR / '.env'):
    """Load database settings without placing credentials in source code."""
    load_dotenv(env_file)
    names = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    config = {name: os.getenv(name) for name in names}
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise RuntimeError(
            'DB 환경변수가 없습니다: ' + ', '.join(missing)
            + '. .env.example을 복사해 .env를 작성해주세요.'
        )
    return {
        'host': config['DB_HOST'],
        'port': config['DB_PORT'],
        'dbname': config['DB_NAME'],
        'user': config['DB_USER'],
        'password': config['DB_PASSWORD'],
        'connect_timeout': 5,
    }


def connect(env_file=BASE_DIR / '.env'):
    """Open a new PostgreSQL connection."""
    return psycopg.connect(**load_db_config(env_file))


def initialize_database(connection, schema_file=BASE_DIR / 'schema.sql'):
    """Create missing database objects. Existing history is preserved."""
    connection.execute(schema_file.read_text(encoding='utf-8'))
    connection.commit()


def insert_comparison_history(connection, old_path, new_path, *,
                              added_count, changed_count, deleted_count,
                              unchanged_count):
    """Store one comparison summary and return its generated id."""
    row = connection.execute(
        '''
        INSERT INTO comparison_history (
            old_path, new_path, added_count, changed_count,
            deleted_count, unchanged_count
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        ''',
        (str(old_path), str(new_path), added_count, changed_count,
         deleted_count, unchanged_count),
    ).fetchone()
    connection.commit()
    return row[0]


def get_comparison_history(connection, history_id):
    """Read one stored comparison summary by id."""
    return connection.execute(
        '''
        SELECT id, old_path, new_path, added_count, changed_count,
               deleted_count, unchanged_count, compared_at
        FROM comparison_history
        WHERE id = %s
        ''',
        (history_id,),
    ).fetchone()


def save_comparison_result(old_path, new_path, entries):
    """Count file results, initialize the schema, and save one history row."""
    counts = {'추가': 0, '변경': 0, '삭제': 0, '동일': 0}
    for entry in entries:
        paths = (entry.left, entry.right)
        is_file = any(
            path is not None and (path.is_file() or path.is_symlink())
            for path in paths
        )
        if is_file and entry.status in counts:
            counts[entry.status] += 1

    with connect() as connection:
        initialize_database(connection)
        return insert_comparison_history(
            connection,
            old_path,
            new_path,
            added_count=counts['추가'],
            changed_count=counts['변경'],
            deleted_count=counts['삭제'],
            unchanged_count=counts['동일'],
        )
