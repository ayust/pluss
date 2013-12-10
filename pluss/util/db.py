import sqlite3

global_db_path = None

# Note that EVERY function that does database operations
# should include at least one call to either conn.commit()
# or conn.rollback() - and there shouldn't be any DB access
# after the last such call in a given function. (IOW, don't
# leave uncommitted changes around.)

class Table(object):

	@classmethod
	def create(cls):
		"""Creates the table in the database if it doesn't already exist."""
		raise NotImplementedError

def init(db_path):
        global global_db_path
        global_db_path = db_path

	# Create tables
	TokenIdMapping.create()

class TokenIdMapping(Table):

	@classmethod
	def create(cls):
                conn = sqlite3.connect(global_db_path)
		conn.execute("""
			CREATE TABLE IF NOT EXISTS token_id_mapping (
				person_id TEXT,
				refresh_token TEXT,
				PRIMARY KEY(person_id)
			)""")
		conn.commit()

	@classmethod
	def update_refresh_token(cls, id, token):
                conn = sqlite3.connect(global_db_path)
		conn.execute("""
			INSERT OR REPLACE INTO token_id_mapping
			(person_id, refresh_token) VALUES (?, ?)
		""", (id, token))
		conn.commit()

	@classmethod
	def lookup_refresh_token(cls, id):
                conn = sqlite3.connect(global_db_path)
		cursor = conn.execute("""
			SELECT refresh_token
			FROM token_id_mapping
			WHERE person_id = ?
			LIMIT 1
		""", (id,))
		if not cursor:
			return None
		row = cursor.fetchone()
		conn.rollback()
		return row[0] if row else None

	@classmethod
	def remove_id(cls, id):
                conn = sqlite3.connect(global_db_path)
		cursor = conn.execute("""
			DELETE FROM token_id_mapping
			WHERE person_id = ?
		""", (id,))
		conn.commit()
