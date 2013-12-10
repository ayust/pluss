import sqlite3

# This is really hacky. At some point it should really get replaced with a proper
# database system that can share connections between threads, et cetera - but for
# now, this works.

global_db_path = None

def init(db_path):
        global global_db_path
        global_db_path = db_path

	# Create tables
	TokenIdMapping.create()

class TokenIdMapping(object):

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
