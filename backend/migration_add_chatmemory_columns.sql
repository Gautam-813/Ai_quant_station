-- Migration: Add reasoning, provider, model, tokens_used, latency_ms to chat_memories
-- Run: psql -U admin_user -d finance_engine -f migration_add_chatmemory_columns.sql

ALTER TABLE chat_memories ADD COLUMN IF NOT EXISTS reasoning TEXT;
ALTER TABLE chat_memories ADD COLUMN IF NOT EXISTS provider VARCHAR;
ALTER TABLE chat_memories ADD COLUMN IF NOT EXISTS model VARCHAR;
ALTER TABLE chat_memories ADD COLUMN IF NOT EXISTS tokens_used INTEGER;
ALTER TABLE chat_memories ADD COLUMN IF NOT EXISTS latency_ms INTEGER;
