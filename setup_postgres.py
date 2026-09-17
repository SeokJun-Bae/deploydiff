"""One-time PostgreSQL setup for a local DeployDiff development database."""
from getpass import getpass

import psycopg
from psycopg import sql

from database import initialize_database, load_db_config


def main():
    config = load_db_config()
    admin_user = input('PostgreSQL 관리자 사용자 [postgres]: ').strip() or 'postgres'
    admin_password = getpass('PostgreSQL 관리자 비밀번호: ')

    admin_config = {
        'host': config['host'],
        'port': config['port'],
        'dbname': 'postgres',
        'user': admin_user,
        'password': admin_password,
        'connect_timeout': config['connect_timeout'],
        'autocommit': True,
    }

    with psycopg.connect(**admin_config) as connection:
        role_exists = connection.execute(
            'SELECT 1 FROM pg_roles WHERE rolname = %s',
            (config['user'],),
        ).fetchone()

        if role_exists:
            connection.execute(
                sql.SQL('ALTER ROLE {} WITH LOGIN PASSWORD %s').format(
                    sql.Identifier(config['user'])
                ),
                (config['password'],),
            )
            print(f"역할 '{config['user']}'의 비밀번호를 .env와 일치시켰습니다.")
        else:
            connection.execute(
                sql.SQL('CREATE ROLE {} WITH LOGIN PASSWORD %s').format(
                    sql.Identifier(config['user'])
                ),
                (config['password'],),
            )
            print(f"역할 '{config['user']}'을 생성했습니다.")

        database_exists = connection.execute(
            'SELECT 1 FROM pg_database WHERE datname = %s',
            (config['dbname'],),
        ).fetchone()

        if database_exists:
            print(f"데이터베이스 '{config['dbname']}'가 이미 있습니다.")
        else:
            connection.execute(
                sql.SQL('CREATE DATABASE {} OWNER {}').format(
                    sql.Identifier(config['dbname']),
                    sql.Identifier(config['user']),
                )
            )
            print(f"데이터베이스 '{config['dbname']}'를 생성했습니다.")

    app_config = dict(config)
    with psycopg.connect(**app_config) as connection:
        initialize_database(connection)

    print('comparison_history 테이블 준비가 완료되었습니다.')
    print('다음 명령으로 INSERT/SELECT 테스트를 실행하세요:')
    print(r'.\.venv\Scripts\python.exe db_smoke_test.py')


if __name__ == '__main__':
    main()
