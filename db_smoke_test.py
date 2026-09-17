"""Create the schema, insert a sample row, and read it back."""
from database import (connect, get_comparison_history, initialize_database,
                      insert_comparison_history)


def main():
    with connect() as connection:
        initialize_database(connection)
        history_id = insert_comparison_history(
            connection,
            'samples/left',
            'samples/right',
            added_count=1,
            changed_count=1,
            deleted_count=1,
            unchanged_count=1,
        )
        row = get_comparison_history(connection, history_id)

    if row is None:
        raise RuntimeError('INSERT한 비교 이력을 SELECT로 찾지 못했습니다.')

    columns = (
        'id', 'old_path', 'new_path', 'added_count', 'changed_count',
        'deleted_count', 'unchanged_count', 'compared_at',
    )
    print('PostgreSQL 연결, 테이블 생성, INSERT, SELECT에 성공했습니다.')
    for name, value in zip(columns, row):
        print(f'{name}: {value}')


if __name__ == '__main__':
    main()
