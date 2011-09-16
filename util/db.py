import sqlite3

conn = None

# Note that EVERY function that does database operations
# should include at least one call to either cls.conn.commit()
# or cls.conn.rollback() - and there shouldn't be any DB access
# after the last such call in a given function. (IOW, don't
# leave uncommitted changes around.)

class Table(object):

	# Everything except init() assumes that this is a valid
	# sqlite3 connection object. Thus, you need to call init()
	# before anything else here will work.
	conn = None

	@classmethod
	def create(cls):
		"""Creates the table in the database if it doesn't already exist."""
		raise NotImplementedError
		
def init(db_path):	
	if Table.conn is None:
		Table.conn = sqlite3.connect(db_path)

	# Create tables
	TokenIdMapping.create()

class TokenIdMapping(Table):

	@classmethod
	def create(cls):
		cls.conn.execute("""
			CREATE TABLE IF NOT EXISTS token_id_mapping (
				person_id INTEGER,
				refresh_token TEXT,
				PRIMARY KEY(person_id)
			)""")
		cls.conn.commit()

	@classmethod
	def update_refresh_token(cls, id, token):
		cls.conn.execute("""
			INSERT OR REPLACE INTO token_id_mapping
			(person_id, refresh_token) VALUES (?, ?)
		""", id, token)
		cls.conn.commit()

	@classmethod
	def lookup_refresh_token(cls, id):
		cursor = cls.conn.execute("""
			SELECT refresh_token
			FROM token_id_mapping
			WHERE person_id = ?
			LIMIT 1
		""", id)
		if not cursor:
			return None
		row = cursor.fetchone()
		cls.conn.rollback()
		return row[0] if row else None
