"""Connection-local defense in depth for read-only SQLite inspection."""
import sqlite3


def safety_status(connection):
    """Read back actual settings; unsupported features are never claimed active."""
    result = {}
    for name in ('trusted_schema', 'cell_size_check'):
        row = connection.execute('PRAGMA ' + name).fetchone()
        result[name] = 'UNAVAILABLE' if row is None else 'ON' if row[0] else 'OFF'
    flag = getattr(sqlite3, 'SQLITE_DBCONFIG_DEFENSIVE', None)
    if flag is None or not hasattr(connection, 'getconfig'):
        result['defensive'] = 'UNAVAILABLE'
    else:
        result['defensive'] = 'ON' if connection.getconfig(flag) else 'OFF'
    return result


def protect_readonly(connection):
    """No persistent database setting or write-connection behavior is changed."""
    connection.execute('PRAGMA query_only=ON')
    connection.execute('PRAGMA trusted_schema=OFF')
    connection.execute('PRAGMA cell_size_check=ON')
    flag = getattr(sqlite3, 'SQLITE_DBCONFIG_DEFENSIVE', None)
    if flag is not None and hasattr(connection, 'setconfig'):
        connection.setconfig(flag, True)
    status = safety_status(connection)
    if status['trusted_schema'] == 'ON' or status['cell_size_check'] == 'OFF' or status['defensive'] == 'OFF':
        raise sqlite3.DatabaseError('read-only SQLite protections could not be enabled')
    return status
