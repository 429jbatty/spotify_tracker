"""Frozen initial Albumary SQLite schema."""

from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names()) - {"alembic_version"}
    if existing_tables or inspector.get_view_names():
        raise CommandError(
            "This SQLite database contains an unversioned schema. "
            "Back it up and verify it against revision 0001 before stamping it. "
            "See docs/deployment.md under 'Adopt an existing SQLite database'."
        )

    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('google_subject', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_accounts_created_at', 'accounts', ['created_at'], unique=False)
    op.create_index('ix_accounts_email', 'accounts', ['email'], unique=True)
    op.create_index('ix_accounts_google_subject', 'accounts', ['google_subject'], unique=True)

    op.create_table(
        'album_metadata_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cache_key', sa.String(), nullable=False),
        sa.Column('artist', sa.String(), nullable=False),
        sa.Column('album', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_album_metadata_cache_cache_key', 'album_metadata_cache', ['cache_key'], unique=True)
    op.create_index('ix_album_metadata_cache_status', 'album_metadata_cache', ['status'], unique=False)
    op.create_index(
        'ix_album_metadata_cache_updated_at', 'album_metadata_cache', ['updated_at'], unique=False,
    )

    op.create_table(
        'albums',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('album_key', sa.String(), nullable=False),
        sa.Column('artist', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('normalized_identity', sa.String(), nullable=True),
        sa.Column('artist_mbid', sa.String(), nullable=True),
        sa.Column('release_group_mbid', sa.String(), nullable=True),
        sa.Column('release_mbid', sa.String(), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('release_year', sa.Integer(), nullable=True),
        sa.Column('release_month', sa.Integer(), nullable=True),
        sa.Column('release_day', sa.Integer(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('remote_image_url', sa.Text(), nullable=True),
        sa.Column('local_image_path', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('entry_source', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_albums_album_key', 'albums', ['album_key'], unique=True)
    op.create_index('ix_albums_entry_source', 'albums', ['entry_source'], unique=False)
    op.create_index('ix_albums_normalized_identity', 'albums', ['normalized_identity'], unique=False)
    op.create_index('ix_albums_release_group_mbid', 'albums', ['release_group_mbid'], unique=False)
    op.create_index(
        'uq_albums_release_group_mbid',
        'albums',
        ['release_group_mbid'],
        unique=True,
        sqlite_where=sa.text("release_group_mbid IS NOT NULL AND release_group_mbid != ''"),
    )

    op.create_table(
        'google_oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_google_oauth_states_created_at', 'google_oauth_states', ['created_at'], unique=False)
    op.create_index('ix_google_oauth_states_state_hash', 'google_oauth_states', ['state_hash'], unique=True)

    op.create_table(
        'account_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_account_sessions_account_id', 'account_sessions', ['account_id'], unique=False)
    op.create_index('ix_account_sessions_created_at', 'account_sessions', ['created_at'], unique=False)
    op.create_index('ix_account_sessions_token_hash', 'account_sessions', ['token_hash'], unique=True)

    op.create_table(
        'album_credit_facts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('album_id', sa.Integer(), nullable=False),
        sa.Column('person_key', sa.String(), nullable=False),
        sa.Column('person_name', sa.String(), nullable=False),
        sa.Column('person_mbid', sa.String(), nullable=True),
        sa.Column('identity_resolution', sa.String(), nullable=False),
        sa.Column('ingestion_version', sa.String(), nullable=False),
        sa.Column('raw_role', sa.String(), nullable=False),
        sa.Column('role_bucket', sa.String(), nullable=False),
        sa.Column('source_scope', sa.String(), nullable=False),
        sa.Column('recording_mbid', sa.String(), nullable=True),
        sa.Column('track_count', sa.Integer(), nullable=False),
        sa.Column('album_track_count', sa.Integer(), nullable=False),
        sa.Column('track_share', sa.Float(), nullable=False),
        sa.Column('quality_flags_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['album_id'], ['albums.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'album_id', 'person_key', 'raw_role', 'source_scope', 'ingestion_version',
            name='uq_album_credit_fact_identity_role_scope',
        ),
    )
    op.create_index('ix_album_credit_facts_album_id', 'album_credit_facts', ['album_id'], unique=False)
    op.create_index('ix_album_credit_facts_created_at', 'album_credit_facts', ['created_at'], unique=False)
    op.create_index(
        'ix_album_credit_facts_identity_resolution', 'album_credit_facts', ['identity_resolution'], unique=False,
    )
    op.create_index(
        'ix_album_credit_facts_ingestion_version', 'album_credit_facts', ['ingestion_version'], unique=False,
    )
    op.create_index('ix_album_credit_facts_person_key', 'album_credit_facts', ['person_key'], unique=False)
    op.create_index('ix_album_credit_facts_person_mbid', 'album_credit_facts', ['person_mbid'], unique=False)
    op.create_index('ix_album_credit_facts_person_name', 'album_credit_facts', ['person_name'], unique=False)
    op.create_index('ix_album_credit_facts_raw_role', 'album_credit_facts', ['raw_role'], unique=False)
    op.create_index(
        'ix_album_credit_facts_recording_mbid', 'album_credit_facts', ['recording_mbid'], unique=False,
    )
    op.create_index('ix_album_credit_facts_role_bucket', 'album_credit_facts', ['role_bucket'], unique=False)
    op.create_index(
        'ix_album_credit_facts_source_scope', 'album_credit_facts', ['source_scope'], unique=False,
    )
    op.create_index('ix_album_credit_facts_updated_at', 'album_credit_facts', ['updated_at'], unique=False)

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('owner_account_id', sa.Integer(), nullable=True),
        sa.Column('spotify_sync_enabled', sa.Boolean(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['owner_account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_owner_account_id', 'users', ['owner_account_id'], unique=True)
    op.create_index('ix_users_slug', 'users', ['slug'], unique=True)
    op.create_index(
        'uq_users_owner_account_id',
        'users',
        ['owner_account_id'],
        unique=True,
        sqlite_where=sa.text('owner_account_id IS NOT NULL'),
    )

    op.create_table(
        'album_listens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('album_id', sa.Integer(), nullable=False),
        sa.Column('listened_at', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['album_id'], ['albums.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'album_id', 'listened_at', name='uq_user_album_listen_once'),
    )
    op.create_index('ix_album_listens_album_id', 'album_listens', ['album_id'], unique=False)
    op.create_index('ix_album_listens_listened_at', 'album_listens', ['listened_at'], unique=False)
    op.create_index('ix_album_listens_user_id', 'album_listens', ['user_id'], unique=False)

    op.create_table(
        'albums_in_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('spotify_album_id', sa.String(), nullable=False),
        sa.Column('album_name', sa.String(), nullable=False),
        sa.Column('artist', sa.String(), nullable=False),
        sa.Column('total_tracks', sa.Integer(), nullable=False),
        sa.Column('played_tracks', sa.JSON(), nullable=False),
        sa.Column('first_played', sa.String(), nullable=False),
        sa.Column('last_played', sa.String(), nullable=False),
        sa.Column('completion_logged', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'spotify_album_id', name='uq_user_album_in_progress'),
    )
    op.create_index(
        'ix_albums_in_progress_spotify_album_id', 'albums_in_progress', ['spotify_album_id'], unique=False,
    )
    op.create_index('ix_albums_in_progress_user_id', 'albums_in_progress', ['user_id'], unique=False)

    op.create_table(
        'import_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_user_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('session_name', sa.String(), nullable=True),
        sa.Column('started_at', sa.String(), nullable=False),
        sa.Column('completed_at', sa.String(), nullable=True),
        sa.Column('artifact_path', sa.Text(), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('file_sha256', sa.String(), nullable=True),
        sa.Column('zip_member_count', sa.Integer(), nullable=True),
        sa.Column('duplicate_of_import_session_id', sa.Integer(), nullable=True),
        sa.Column('summary_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_import_sessions_file_sha256', 'import_sessions', ['file_sha256'], unique=False)
    op.create_index('ix_import_sessions_source', 'import_sessions', ['source'], unique=False)
    op.create_index('ix_import_sessions_source_user_id', 'import_sessions', ['source_user_id'], unique=False)
    op.create_index('ix_import_sessions_started_at', 'import_sessions', ['started_at'], unique=False)
    op.create_index('ix_import_sessions_status', 'import_sessions', ['status'], unique=False)
    op.create_index('ix_import_sessions_user_id', 'import_sessions', ['user_id'], unique=False)

    op.create_table(
        'profile_ownership_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.String(), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_profile_ownership_assignments_account_id', 'profile_ownership_assignments', ['account_id'], unique=False,
    )
    op.create_index(
        'ix_profile_ownership_assignments_assigned_at', 'profile_ownership_assignments', ['assigned_at'], unique=False,
    )
    op.create_index(
        'ix_profile_ownership_assignments_user_id', 'profile_ownership_assignments', ['user_id'], unique=False,
    )

    op.create_table(
        'spotify_oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('state_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_spotify_oauth_states_account_id', 'spotify_oauth_states', ['account_id'], unique=False,
    )
    op.create_index(
        'ix_spotify_oauth_states_created_at', 'spotify_oauth_states', ['created_at'], unique=False,
    )
    op.create_index('ix_spotify_oauth_states_state_hash', 'spotify_oauth_states', ['state_hash'], unique=True)
    op.create_index('ix_spotify_oauth_states_user_id', 'spotify_oauth_states', ['user_id'], unique=False)

    op.create_table(
        'user_albums',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('album_id', sa.Integer(), nullable=False),
        sa.Column('your_tags', sa.JSON(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['album_id'], ['albums.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'album_id', name='uq_user_album'),
    )
    op.create_index('ix_user_albums_album_id', 'user_albums', ['album_id'], unique=False)
    op.create_index('ix_user_albums_user_id', 'user_albums', ['user_id'], unique=False)

    op.create_table(
        'user_app_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_app_state_key'),
    )
    op.create_index('ix_user_app_state_key', 'user_app_state', ['key'], unique=False)
    op.create_index('ix_user_app_state_user_id', 'user_app_state', ['user_id'], unique=False)

    op.create_table(
        'user_spotify_credentials',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('spotify_user_id', sa.String(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=False),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('connected_at', sa.String(), nullable=True),
        sa.Column('last_successful_sync_at', sa.String(), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_index(
        'ix_user_spotify_credentials_spotify_user_id', 'user_spotify_credentials', ['spotify_user_id'], unique=False,
    )

    op.create_table(
        'import_session_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_session_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('level', sa.String(), nullable=False),
        sa.Column('stage', sa.String(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('artist', sa.String(), nullable=True),
        sa.Column('album', sa.String(), nullable=True),
        sa.Column('current', sa.Integer(), nullable=True),
        sa.Column('total', sa.Integer(), nullable=True),
        sa.Column('elapsed_seconds', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['import_session_id'], ['import_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_import_session_logs_created_at', 'import_session_logs', ['created_at'], unique=False)
    op.create_index(
        'ix_import_session_logs_import_session_id', 'import_session_logs', ['import_session_id'], unique=False,
    )
    op.create_index('ix_import_session_logs_level', 'import_session_logs', ['level'], unique=False)
    op.create_index('ix_import_session_logs_stage', 'import_session_logs', ['stage'], unique=False)

    op.create_table(
        'imported_listening_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('import_session_id', sa.Integer(), nullable=True),
        sa.Column('album_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_user_id', sa.String(), nullable=True),
        sa.Column('source_event_id', sa.String(), nullable=True),
        sa.Column('event_fingerprint', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=True),
        sa.Column('listened_at', sa.String(), nullable=False),
        sa.Column('artist', sa.String(), nullable=False),
        sa.Column('album', sa.String(), nullable=True),
        sa.Column('track', sa.String(), nullable=True),
        sa.Column('source_label', sa.String(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('match_status', sa.String(), nullable=False),
        sa.Column('match_confidence', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['album_id'], ['albums.id']),
        sa.ForeignKeyConstraint(['import_session_id'], ['import_sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'event_fingerprint', name='uq_imported_event_fingerprint'),
    )
    op.create_index(
        'ix_imported_listening_events_candidate_key', 'imported_listening_events', ['candidate_key'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_event_fingerprint', 'imported_listening_events', ['event_fingerprint'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_import_session_id', 'imported_listening_events', ['import_session_id'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_listened_at', 'imported_listening_events', ['listened_at'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_match_status', 'imported_listening_events', ['match_status'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_source', 'imported_listening_events', ['source'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_source_user_id', 'imported_listening_events', ['source_user_id'], unique=False,
    )
    op.create_index(
        'ix_imported_listening_events_user_id', 'imported_listening_events', ['user_id'], unique=False,
    )

    op.create_table(
        'spotify_streaming_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('import_session_id', sa.Integer(), nullable=True),
        sa.Column('event_fingerprint', sa.String(), nullable=False),
        sa.Column('source_file', sa.String(), nullable=True),
        sa.Column('source_index', sa.Integer(), nullable=True),
        sa.Column('played_at', sa.String(), nullable=False),
        sa.Column('ms_played', sa.Integer(), nullable=False),
        sa.Column('spotify_track_uri', sa.String(), nullable=True),
        sa.Column('spotify_track_id', sa.String(), nullable=True),
        sa.Column('spotify_album_id', sa.String(), nullable=True),
        sa.Column('spotify_album_name', sa.String(), nullable=True),
        sa.Column('spotify_album_artist_name', sa.String(), nullable=True),
        sa.Column('spotify_album_total_tracks', sa.Integer(), nullable=True),
        sa.Column('spotify_album_type', sa.String(), nullable=True),
        sa.Column('spotify_disc_number', sa.Integer(), nullable=True),
        sa.Column('spotify_track_number', sa.Integer(), nullable=True),
        sa.Column('spotify_catalog_status', sa.String(), nullable=True),
        sa.Column('track_name', sa.String(), nullable=True),
        sa.Column('artist_name', sa.String(), nullable=True),
        sa.Column('album_name', sa.String(), nullable=True),
        sa.Column('platform', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('reason_start', sa.String(), nullable=True),
        sa.Column('reason_end', sa.String(), nullable=True),
        sa.Column('skipped', sa.Boolean(), nullable=True),
        sa.Column('offline', sa.Boolean(), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['import_session_id'], ['import_sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'event_fingerprint', name='uq_spotify_streaming_event_fingerprint'),
    )
    op.create_index(
        'ix_spotify_streaming_events_event_fingerprint', 'spotify_streaming_events', ['event_fingerprint'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_import_session_id', 'spotify_streaming_events', ['import_session_id'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_played_at', 'spotify_streaming_events', ['played_at'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_spotify_album_id', 'spotify_streaming_events', ['spotify_album_id'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_spotify_album_type', 'spotify_streaming_events', ['spotify_album_type'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_spotify_catalog_status', 'spotify_streaming_events', ['spotify_catalog_status'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_spotify_track_id', 'spotify_streaming_events', ['spotify_track_id'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_spotify_track_uri', 'spotify_streaming_events', ['spotify_track_uri'], unique=False,
    )
    op.create_index(
        'ix_spotify_streaming_events_user_id', 'spotify_streaming_events', ['user_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_table('spotify_streaming_events')
    op.drop_table('imported_listening_events')
    op.drop_table('import_session_logs')
    op.drop_table('user_spotify_credentials')
    op.drop_table('user_app_state')
    op.drop_table('user_albums')
    op.drop_table('spotify_oauth_states')
    op.drop_table('profile_ownership_assignments')
    op.drop_table('import_sessions')
    op.drop_table('albums_in_progress')
    op.drop_table('album_listens')
    op.drop_table('users')
    op.drop_table('album_credit_facts')
    op.drop_table('account_sessions')
    op.drop_table('google_oauth_states')
    op.drop_table('albums')
    op.drop_table('album_metadata_cache')
    op.drop_table('accounts')
