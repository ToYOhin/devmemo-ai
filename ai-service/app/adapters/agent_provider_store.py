"""Encrypted SQLite persistence for the single-host Agent provider setting."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.domain.agent_provider import (
    AGENT_PROVIDER_CONFIG_VERSION,
    AgentProviderConfig,
    AgentProviderConfigError,
)


_ROW_ID = 1


class AgentProviderStoreError(RuntimeError):
    """Raised without exposing credentials when encrypted storage is unavailable."""


class SQLiteAgentProviderStore:
    def __init__(self, database: str | Path, internal_secret: str) -> None:
        if not internal_secret.strip():
            raise AgentProviderStoreError("Agent provider credential store is unavailable")
        self._database = Path(database)
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"devmemo-agent-provider-store-v1",
        ).derive(internal_secret.encode("utf-8"))

    def load(self) -> AgentProviderConfig | None:
        try:
            with closing(sqlite3.connect(self._database)) as connection, connection:
                self._ensure_schema(connection)
                row = connection.execute(
                    """
                    SELECT provider, model, base_url, api_key_nonce, api_key_ciphertext,
                           enabled, allow_real_memo_data, config_version
                    FROM agent_provider_config WHERE id = ?
                    """,
                    (_ROW_ID,),
                ).fetchone()
        except sqlite3.Error as error:
            raise AgentProviderStoreError("Agent provider credential store is unavailable") from error
        if row is None:
            return None
        try:
            api_key = self._decrypt(row[3], row[4], str(row[0]), str(row[1]), str(row[2]))
            return AgentProviderConfig(
                provider=str(row[0]),
                model=str(row[1]),
                base_url=str(row[2]),
                api_key=api_key,
                enabled=bool(row[5]),
                allow_real_memo_data=bool(row[6]),
                config_version=int(row[7]),
                source="stored",
            ).validated()
        except (AgentProviderConfigError, TypeError, ValueError) as error:
            raise AgentProviderStoreError("Agent provider credential store is unavailable") from error

    def save(self, config: AgentProviderConfig, *, preserve_api_key: bool = False) -> AgentProviderConfig:
        current = self.load()
        api_key = config.api_key
        if preserve_api_key:
            if current is None or current.provider != config.provider:
                raise AgentProviderConfigError("Agent provider credential is required")
            api_key = current.api_key
        next_version = (current.config_version if current is not None else 0) + 1
        normalized = replace(
            config,
            api_key=api_key,
            config_version=next_version,
            source="stored",
        ).validated()
        nonce, ciphertext = self._encrypt(
            normalized.api_key,
            normalized.provider,
            normalized.model,
            normalized.base_url,
        )
        try:
            with closing(sqlite3.connect(self._database)) as connection, connection:
                self._ensure_schema(connection)
                connection.execute(
                    """
                    INSERT INTO agent_provider_config (
                        id, schema_version, provider, model, base_url,
                        api_key_nonce, api_key_ciphertext, enabled,
                        allow_real_memo_data, config_version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        provider = excluded.provider,
                        model = excluded.model,
                        base_url = excluded.base_url,
                        api_key_nonce = excluded.api_key_nonce,
                        api_key_ciphertext = excluded.api_key_ciphertext,
                        enabled = excluded.enabled,
                        allow_real_memo_data = excluded.allow_real_memo_data,
                        config_version = excluded.config_version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        _ROW_ID,
                        AGENT_PROVIDER_CONFIG_VERSION,
                        normalized.provider,
                        normalized.model,
                        normalized.base_url,
                        nonce,
                        ciphertext,
                        int(normalized.enabled),
                        int(normalized.allow_real_memo_data),
                        normalized.config_version,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.Error as error:
            raise AgentProviderStoreError("Agent provider credential store is unavailable") from error
        return normalized

    def _encrypt(
        self,
        api_key: str | None,
        provider: str,
        model: str,
        base_url: str,
    ) -> tuple[bytes | None, bytes | None]:
        if api_key is None:
            return None, None
        nonce = os.urandom(12)
        return nonce, AESGCM(self._key).encrypt(
            nonce,
            api_key.encode("utf-8"),
            _aad(provider, model, base_url),
        )

    def _decrypt(
        self,
        nonce: object,
        ciphertext: object,
        provider: str,
        model: str,
        base_url: str,
    ) -> str | None:
        if nonce is None and ciphertext is None:
            return None
        if not isinstance(nonce, bytes) or not isinstance(ciphertext, bytes):
            raise AgentProviderStoreError("Agent provider credential store is unavailable")
        try:
            return (
                AESGCM(self._key)
                .decrypt(
                    nonce,
                    ciphertext,
                    _aad(provider, model, base_url),
                )
                .decode("utf-8")
            )
        except Exception as error:
            raise AgentProviderStoreError("Agent provider credential store is unavailable") from error

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_provider_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                base_url TEXT NOT NULL,
                api_key_nonce BLOB,
                api_key_ciphertext BLOB,
                enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                allow_real_memo_data INTEGER NOT NULL CHECK (allow_real_memo_data IN (0, 1)),
                config_version INTEGER NOT NULL CHECK (config_version > 0),
                updated_at TEXT NOT NULL
            )
            """
        )


def _aad(provider: str, model: str, base_url: str) -> bytes:
    return json.dumps(
        {
            "version": AGENT_PROVIDER_CONFIG_VERSION,
            "provider": provider,
            "model": model,
            "base_url": base_url,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
